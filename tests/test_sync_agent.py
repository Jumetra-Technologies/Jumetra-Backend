"""Sprint 9 — Sync agent, protocol, sample collection, quality tests."""

import json

from engine.devices.base import DeviceMode, PhysicalDevice, SimulatorDevice
from engine.devices.device_manager import DeviceManager
from engine.devices.virtual import VirtualLED
from engine.events import Event, EventBus
from engine.experiments import ExperimentSession
from engine.synchronization import (
    PhysicalSyncAgent,
    SimulatorSyncAgent,
    SyncEventType,
    SyncQuality,
    SyncRequest,
    SyncResponse,
    SynchronizationManager,
    VirtualSyncAgent,
    create_sync_agent,
)
from engine.time import SimulationClock, TimestampService, set_timestamp_service


class TestSyncProtocol:
    def test_request_round_trip_serialize(self):
        req = SyncRequest(
            sequence_number=3,
            device_id="esp32_01",
            server_timestamp=12_345,
            correlation_id="corr-1",
            request_id="sync_abc",
        )
        restored = SyncRequest.from_json(req.to_json())
        assert restored.sequence_number == 3
        assert restored.device_id == "esp32_01"
        assert restored.server_timestamp == 12_345
        assert restored.correlation_id == "corr-1"
        assert restored.request_id == "sync_abc"

    def test_response_round_trip_serialize(self):
        resp = SyncResponse(
            sequence_number=3,
            device_id="esp32_01",
            server_timestamp=12_345,
            device_timestamp=99,
            correlation_id="corr-1",
            request_id="sync_abc",
        )
        restored = SyncResponse.from_dict(resp.to_dict())
        assert restored.to_dict() == resp.to_dict()

    def test_event_payload_fields(self):
        req = SyncRequest(
            sequence_number=1,
            device_id="virtual_led_01",
            server_timestamp=1000,
            correlation_id="c1",
            request_id="sync_1",
        )
        payload = req.to_event_payload()
        for key in (
            "sequence_number",
            "device_id",
            "server_timestamp",
            "device_timestamp",
            "correlation_id",
        ):
            assert key in payload


class TestSyncAgents:
    def setup_method(self):
        self.clock = SimulationClock(start_ms=10_000)
        set_timestamp_service(TimestampService(clock=self.clock))
        self.ts = TimestampService(clock=self.clock)

    def teardown_method(self):
        set_timestamp_service(None)

    def test_virtual_agent_echo_and_measurement(self):
        led = VirtualLED("virtual_led_01")
        agent = VirtualSyncAgent(led, timestamp_service=self.ts)
        req = agent.send_sync_request()
        assert req.device_id == "virtual_led_01"
        assert req.sequence_number == 1

        self.clock.advance(5)
        resp = agent.echo_response(req)
        resp = agent.receive_sync_response(resp)
        self.clock.advance(2)
        obs = agent.create_measurement(req, resp)
        assert obs.round_trip_time == 7
        assert obs.device_id == "virtual_led_01"

    def test_simulator_and_physical_factory(self):
        sim = SimulatorDevice(device_id="sim_01", device_type="esp32")
        phys = PhysicalDevice("esp32_01", "esp32")
        assert isinstance(create_sync_agent(sim, timestamp_service=self.ts), SimulatorSyncAgent)
        assert isinstance(create_sync_agent(phys, timestamp_service=self.ts), PhysicalSyncAgent)
        assert sim.device_mode == DeviceMode.SIMULATED
        assert phys.device_mode == DeviceMode.PHYSICAL

    def test_physical_agent_no_auto_echo_wire_shape(self):
        phys = PhysicalDevice(device_id="esp32_01", device_type="esp32")
        agent = PhysicalSyncAgent(phys, timestamp_service=self.ts)
        req = agent.send_sync_request()
        wire = agent.to_wire_request(req)
        assert wire["type"] == "SYNC_REQUEST"
        assert wire["target"] == "esp32_01"
        assert "server_timestamp" in wire["payload"]


class TestSampleCollectionAndQuality:
    def setup_method(self):
        self.clock = SimulationClock(start_ms=2000)
        set_timestamp_service(TimestampService(clock=self.clock))
        self.bus = EventBus()
        self.devices = DeviceManager()
        self.led = VirtualLED("virtual_led_01")
        self.devices.register_device(self.led)
        self.sync = SynchronizationManager(
            self.bus,
            timestamp_service=TimestampService(clock=self.clock),
            device_manager=self.devices,
            echo_virtual=True,
            default_window_size=50,
        )
        self.bus.register_subscriber(self.sync)

    def teardown_method(self):
        set_timestamp_service(None)

    def test_collect_multiple_samples_and_history(self):
        samples = self.sync.collect_samples(self.led, count=10, advance_clock_ms=1)
        assert len(samples) == 10
        history = self.sync.get_sample_history("virtual_led_01")
        assert len(history) == 10
        window = self.sync.get_measurement_window("virtual_led_01", window_size=5)
        assert len(window) == 5

    def test_rtt_stats_include_jitter(self):
        self.sync.collect_samples(self.led, count=5, advance_clock_ms=2)
        stats = self.sync.compute_rtt_stats("virtual_led_01")
        assert stats["sample_count"] == 5
        assert stats["average_rtt"] is not None
        assert stats["min_rtt"] is not None
        assert stats["max_rtt"] is not None
        assert stats["jitter"] is not None
        summary = self.sync.measurement_summary()
        assert "jitter" in summary

    def test_quality_calculation(self):
        self.sync.collect_samples(self.led, count=20, advance_clock_ms=1)
        quality = self.sync.get_quality("virtual_led_01", target_samples=20)
        assert isinstance(quality, SyncQuality)
        assert quality.device_id == "virtual_led_01"
        assert quality.sample_count == 20
        assert quality.average_rtt is not None
        assert quality.jitter is not None
        assert quality.offset_variance is not None
        assert 0.0 <= quality.confidence_score <= 1.0

    def test_quality_empty(self):
        q = SyncQuality.from_samples("x", [], [])
        assert q.sample_count == 0
        assert q.confidence_score == 0.0


class TestExperimentSyncExports:
    def setup_method(self):
        self.clock = SimulationClock(start_ms=8000)
        set_timestamp_service(TimestampService(clock=self.clock))

    def teardown_method(self):
        set_timestamp_service(None)

    def test_exports_sync_samples_and_quality_summary(self, tmp_path):
        bus = EventBus()
        devices = DeviceManager()
        led = VirtualLED("virtual_led_01")
        devices.register_device(led)

        session = ExperimentSession(name="sync_validation", experiment_id="EXP9A1")
        session.start(devices=["virtual_led_01"])

        sync = SynchronizationManager(
            bus,
            timestamp_service=TimestampService(clock=self.clock),
            device_manager=devices,
            echo_virtual=True,
        )
        sync.bind_experiment(session)
        bus.register_subscriber(sync)

        sync.collect_samples(led, count=100, advance_clock_ms=1)
        assert len(session.sync_measurements) == 100

        session.finish()
        root = session.export(base_dir=tmp_path / "experiments")

        samples_path = root / "sync_samples.jsonl"
        quality_path = root / "quality_summary.json"
        assert samples_path.exists()
        assert quality_path.exists()

        lines = samples_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 100

        quality = json.loads(quality_path.read_text(encoding="utf-8"))
        assert quality["total_samples"] == 100
        assert quality["device_count"] == 1
        device_q = quality["devices"][0]
        assert device_q["sample_count"] == 100
        assert device_q["average_rtt"] is not None
        assert "confidence_score" in device_q
        assert 0.0 <= device_q["confidence_score"] <= 1.0

        summary = json.loads((root / "summary.json").read_text(encoding="utf-8"))
        assert summary["jitter"] is not None
        assert summary["quality"]["total_samples"] == 100


class TestPhysicalMeasurementPath:
    """Physical devices publish requests but wait for wire responses."""

    def setup_method(self):
        self.clock = SimulationClock(start_ms=3000)
        set_timestamp_service(TimestampService(clock=self.clock))
        self.bus = EventBus()
        self.devices = DeviceManager()
        self.phys = PhysicalDevice("esp32_01", "esp32")
        self.devices.register_device(self.phys)
        self.sync = SynchronizationManager(
            self.bus,
            timestamp_service=TimestampService(clock=self.clock),
            device_manager=self.devices,
            echo_virtual=True,
        )
        self.bus.register_subscriber(self.sync)

    def teardown_method(self):
        set_timestamp_service(None)

    def test_physical_waits_for_manual_response(self):
        request = self.sync.request_sync(self.phys)
        assert len(self.sync.get_measurements()) == 0

        self.clock.advance(8)
        response = Event.create(
            event_type=SyncEventType.SYNC_RESPONSE,
            source="esp32_01",
            target="hhip",
            payload={
                "request_id": request.payload["request_id"],
                "request_time": request.payload["server_timestamp"],
                "server_timestamp": self.clock.now() + 1,
                "device_timestamp": self.clock.now() + 1,
                "sequence_number": request.payload["sequence_number"],
                "device_id": "esp32_01",
                "correlation_id": request.correlation_id,
            },
            correlation_id=request.correlation_id,
        )
        obs = self.sync.process_response(response)
        assert obs is not None
        assert obs.round_trip_time == 8
        assert obs.device_id == "esp32_01"
