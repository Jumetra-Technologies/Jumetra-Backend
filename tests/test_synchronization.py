"""Sprint 8 — synchronization protocol measurement foundation tests."""

import json

from engine.devices.device_manager import DeviceManager
from engine.devices.virtual import VirtualLED
from engine.events import EventBus
from engine.experiments import ExperimentSession
from engine.synchronization import (
    ClockObservation,
    SyncEventType,
    SynchronizationManager,
)
from engine.time import SimulationClock, TimestampService, set_timestamp_service


class TestClockObservation:
    def test_round_trip_serialize(self):
        obs = ClockObservation(
            device_id="esp32_01",
            local_timestamp=100,
            server_timestamp=105,
            round_trip_time=10,
            estimated_offset=0.0,
            measurement_time=110,
            request_time=100,
            response_time=110,
            request_id="sync_abc",
        )
        restored = ClockObservation.from_dict(obs.to_dict())
        assert restored.to_dict() == obs.to_dict()


class TestSynchronizationManager:
    def setup_method(self):
        self.clock = SimulationClock(start_ms=1000)
        set_timestamp_service(TimestampService(clock=self.clock))
        self.bus = EventBus()
        self.manager_devices = DeviceManager()
        self.led = VirtualLED("virtual_led_01")
        self.manager_devices.register_device(self.led)
        self.sync = SynchronizationManager(
            self.bus,
            timestamp_service=TimestampService(clock=self.clock),
            device_manager=self.manager_devices,
            echo_virtual=True,
        )
        self.bus.register_subscriber(self.sync)

    def teardown_method(self):
        set_timestamp_service(None)

    def test_request_sync_publishes_and_records_measurement(self):
        event = self.sync.request_sync(self.led)
        assert event.event_type == SyncEventType.SYNC_REQUEST
        assert event.target == "virtual_led_01"

        measurements = self.sync.get_measurements()
        assert len(measurements) == 1
        obs = measurements[0]
        assert obs.device_id == "virtual_led_01"
        assert obs.request_time is not None
        assert obs.response_time is not None
        assert obs.round_trip_time == obs.response_time - obs.request_time
        assert obs.round_trip_time >= 0

    def test_rtt_calculation_with_manual_response(self):
        sync = SynchronizationManager(
            self.bus,
            timestamp_service=TimestampService(clock=self.clock),
            device_manager=self.manager_devices,
            echo_virtual=False,
        )
        self.bus.register_subscriber(sync)

        request = sync.request_sync("virtual_sensor_01")
        request_id = request.payload["request_id"]
        request_time = request.payload["request_time"]

        self.clock.advance(12)
        from engine.events import Event

        response = Event.create(
            event_type=SyncEventType.SYNC_RESPONSE,
            source="virtual_sensor_01",
            target="hhip",
            payload={
                "request_id": request_id,
                "request_time": request_time,
                "server_timestamp": self.clock.now() + 5,
            },
            correlation_id=request.correlation_id,
        )
        self.clock.advance(3)
        obs = sync.process_response(response)
        assert obs is not None
        assert obs.round_trip_time == 15  # 12 + 3
        assert obs.request_time == request_time
        assert obs.response_time == request_time + 15

    def test_device_metadata_updated_with_estimates(self):
        self.sync.request_sync(self.led)
        meta = self.led.get_metadata()
        assert meta["last_sync_measurement"] is not None
        assert "clock_offset_estimate" in meta
        assert meta["last_sync_time"] is not None

    def test_export_results(self, tmp_path):
        self.sync.request_sync(self.led)
        path = self.sync.export_results(tmp_path / "sync_out")
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["measurement_count"] == 1
        assert data["summary"]["min_rtt"] is not None
        assert data["summary"]["max_rtt"] is not None
        assert data["summary"]["average_rtt"] is not None
        assert len(data["summary"]["offset_samples"]) == 1


class TestSyncExperimentIntegration:
    def setup_method(self):
        self.clock = SimulationClock(start_ms=5000)
        set_timestamp_service(TimestampService(clock=self.clock))

    def teardown_method(self):
        set_timestamp_service(None)

    def test_experiment_records_sync_and_exports(self, tmp_path):
        bus = EventBus()
        devices = DeviceManager()
        sensor = VirtualLED("virtual_sensor_01")  # stand-in virtual device
        devices.register_device(sensor)

        session = ExperimentSession(name="sync_rtt_probe", experiment_id="EXP001")
        session.start(devices=["esp32_01", "virtual_sensor_01"])

        sync = SynchronizationManager(
            bus,
            timestamp_service=TimestampService(clock=self.clock),
            device_manager=devices,
            echo_virtual=True,
        )
        sync.bind_experiment(session)
        bus.register_subscriber(sync)

        sync.request_sync(sensor)
        sync.request_sync(sensor)

        assert len(session.sync_measurements) == 2
        session.finish()
        root = session.export(base_dir=tmp_path / "experiments")

        summary = json.loads((root / "summary.json").read_text(encoding="utf-8"))
        assert summary["sync_measurement_count"] == 2
        assert summary["average_rtt"] is not None
        assert summary["min_rtt"] is not None
        assert summary["max_rtt"] is not None
        assert len(summary["offset_samples"]) == 2

        sync_lines = (root / "sync_measurements.jsonl").read_text(encoding="utf-8").strip().splitlines()
        assert len(sync_lines) == 2
