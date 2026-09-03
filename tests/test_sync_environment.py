"""Sprint 10 — sync environment, physical bridge, scenarios, reports."""

import json

from engine.communication.memory_adapter import make_adapter_pair
from engine.devices.base import PhysicalDevice
from engine.devices.device_manager import DeviceManager
from engine.devices.virtual import VirtualLED
from engine.events import Event, EventBus
from engine.events.sync_bridge import SyncTransportSubscriber
from engine.main import HHIPEngine
from engine.network import ConditionedTransport, NetworkConditionModel
from engine.protocol.messages import MessageType, create_message, validate_message
from engine.protocol.sync_wire import event_payload_from_wire_sync_response
from engine.synchronization import (
    SyncEventType,
    SynchronizationManager,
    SynchronizationReport,
)
from engine.synchronization.scenarios import (
    SyncScenario,
    baseline_scenario,
    get_scenario,
    high_latency_scenario,
    network_noise_scenario,
    serial_load_scenario,
)
from engine.time import (
    ClockDomain,
    ClockDomainRegistry,
    SimulationClock,
    TimestampService,
    set_timestamp_service,
)


class TestClockDomains:
    def test_domain_record_observation(self):
        domain = ClockDomain(clock_id="esp32_01", clock_type="device", precision=1.0)
        domain.record_observation(
            {
                "device_id": "esp32_01",
                "estimated_offset": 12.5,
                "round_trip_time": 8,
            }
        )
        assert domain.offset_estimate == 12.5
        assert domain.last_measurement["round_trip_time"] == 8
        restored = ClockDomain.from_dict(domain.to_dict())
        assert restored.clock_id == "esp32_01"

    def test_registry(self):
        reg = ClockDomainRegistry()
        reg.ensure("host", clock_type="host")
        reg.record_observation(
            "esp32_01",
            {"estimated_offset": 1.0, "round_trip_time": 2},
            clock_type="device",
        )
        assert reg.get("esp32_01").offset_estimate == 1.0
        assert "host" in reg.to_dict()


class TestNetworkModel:
    def test_delay_and_drop(self):
        model = NetworkConditionModel(latency_ms=40, jitter_ms=0, packet_loss=0.0, seed=1)
        clock = SimulationClock(start_ms=1000)
        delay = model.apply_delay(clock)
        assert delay == 40
        assert clock.now() == 1040

        lossy = NetworkConditionModel(latency_ms=0, jitter_ms=0, packet_loss=1.0, seed=2)
        assert lossy.should_drop() is True

    def test_conditioned_transport(self):
        sent = []
        clock = SimulationClock(start_ms=0)
        model = NetworkConditionModel(latency_ms=10, jitter_ms=0, packet_loss=0.0, seed=3)
        transport = ConditionedTransport(send_fn=sent.append, model=model, clock=clock)
        transport.send({"type": "SYNC_REQUEST"})
        assert len(sent) == 1
        assert clock.now() == 10


class TestPhysicalProtocolMapping:
    def setup_method(self):
        self.clock = SimulationClock(start_ms=5000)
        set_timestamp_service(TimestampService(clock=self.clock))

    def teardown_method(self):
        set_timestamp_service(None)

    def test_sync_message_types_validate(self):
        msg = create_message(
            type_=MessageType.SYNC_RESPONSE,
            source="esp32_01",
            target="hhip",
            sequence=1,
            payload={
                "request_id": "sync_abc",
                "request_time": 5000,
                "device_timestamp": 5010,
                "server_timestamp": 5010,
            },
        )
        assert validate_message(msg) == []
        assert MessageType.SYNC_REQUEST in {
            MessageType.SYNC_REQUEST,
            MessageType.SYNC_RESPONSE,
        }

    def test_wire_payload_normalization(self):
        wire = create_message(
            type_=MessageType.SYNC_RESPONSE,
            source="esp32_01",
            target="hhip",
            sequence=2,
            payload={
                "request_id": "sync_xyz",
                "server_timestamp_host": 5000,
                "device_timestamp": 5077,
                "correlation_id": "corr-1",
            },
        )
        payload = event_payload_from_wire_sync_response(wire)
        assert payload["request_time"] == 5000
        assert payload["device_timestamp"] == 5077
        assert payload["server_timestamp"] == 5077

    def test_bridge_sends_physical_sync_request(self):
        bus = EventBus()
        devices = DeviceManager()
        phys = PhysicalDevice("esp32_01", "esp32")
        devices.register_device(phys)
        sent = []

        bridge = SyncTransportSubscriber(devices, send_callback=sent.append)
        bus.register_subscriber(bridge)

        sync = SynchronizationManager(
            bus,
            timestamp_service=TimestampService(clock=self.clock),
            device_manager=devices,
            echo_virtual=True,
        )
        bus.register_subscriber(sync)

        sync.request_sync(phys)
        assert len(sent) == 1
        assert sent[0]["type"] == "SYNC_REQUEST"
        assert sent[0]["target"] == "esp32_01"
        assert len(sync.get_measurements()) == 0  # waits for wire response

    def test_engine_handle_message_maps_sync_response(self, tmp_path):
        engine_side, device_side = make_adapter_pair(timeout=0.05)
        engine_side.connect()
        device_side.connect()

        engine = HHIPEngine(
            adapter=engine_side,
            storage_dir=tmp_path / "data",
            persist_events=False,
        )
        engine.device_manager.register_device(PhysicalDevice("esp32_01", "esp32"))

        # Host probe
        request = engine.sync_manager.request_sync(
            engine.device_manager.get_device("esp32_01")
        )
        wire_req = device_side.receive()
        assert wire_req is not None
        assert wire_req["type"] == MessageType.SYNC_REQUEST

        self.clock.advance(9)
        # Device reply (as firmware sync_agent would)
        response = create_message(
            type_=MessageType.SYNC_RESPONSE,
            source="esp32_01",
            target="hhip",
            sequence=1,
            payload={
                "request_id": request.payload["request_id"],
                "request_time": request.payload["server_timestamp"],
                "server_timestamp_host": request.payload["server_timestamp"],
                "device_timestamp": self.clock.now() + 3,
                "server_timestamp": self.clock.now() + 3,
                "sequence_number": request.payload.get("sequence_number", 1),
                "device_id": "esp32_01",
                "correlation_id": request.correlation_id,
            },
        )
        assert validate_message(response) == []
        engine.handle_message(response)

        measurements = engine.sync_manager.get_measurements()
        assert len(measurements) == 1
        assert measurements[0].device_id == "esp32_01"
        assert measurements[0].round_trip_time == 9


class TestScenariosAndReport:
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
        )
        self.bus.register_subscriber(self.sync)

    def teardown_method(self):
        set_timestamp_service(None)

    def test_baseline_scenario(self, tmp_path):
        scenario = baseline_scenario(sample_count=20)
        domains = ClockDomainRegistry()
        session, report, samples = scenario.run(
            self.sync, self.led, clock_domains=domains, advance_clock_ms=1
        )
        assert session.is_active is False
        assert len(samples) == 20
        assert report.sample_count == 20
        assert report.scenario_name == "baseline"
        assert report.average_rtt is not None
        assert 0.0 <= report.confidence_score <= 1.0
        assert domains.get("virtual_led_01") is not None

        path = report.export_json(tmp_path / "validation_report.json")
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["sample_count"] == 20
        assert "minimum_rtt" in data
        assert "maximum_rtt" in data
        assert "jitter" in data

        root = session.export(base_dir=tmp_path / "experiments")
        assert (root / "quality_summary.json").exists()

    def test_high_latency_increases_rtt(self):
        base = baseline_scenario(sample_count=15)
        _, base_report, _ = base.run(self.sync, self.led)
        self.sync.clear_measurements()

        high = high_latency_scenario(sample_count=15, seed=42)
        _, high_report, _ = high.run(self.sync, self.led)
        assert high_report.average_rtt is not None
        assert base_report.average_rtt is not None
        assert high_report.average_rtt > base_report.average_rtt

    def test_named_scenarios_exist(self):
        for name in ("baseline", "high_latency", "network_noise", "serial_load"):
            scenario = get_scenario(name, sample_count=5)
            assert isinstance(scenario, SyncScenario)
            assert scenario.name == name

        noise = network_noise_scenario(sample_count=10, seed=7)
        serial = serial_load_scenario(sample_count=10, seed=8)
        _, noise_report, _ = noise.run(self.sync, self.led)
        self.sync.clear_measurements()
        _, serial_report, _ = serial.run(self.sync, self.led)
        assert noise_report.sample_count <= 10
        assert serial_report.sample_count <= 10

    def test_report_from_quality_round_trip(self):
        self.sync.collect_samples(self.led, count=8, advance_clock_ms=1)
        quality = self.sync.get_quality("virtual_led_01", target_samples=8)
        report = SynchronizationReport.from_quality(quality, scenario_name="manual")
        restored = SynchronizationReport.from_dict(report.to_dict())
        assert restored.sample_count == 8
        assert restored.scenario_name == "manual"
