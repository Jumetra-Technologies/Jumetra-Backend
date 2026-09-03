"""Sprint 7 — synchronization measurement foundation tests."""

import json

from engine.devices.virtual import VirtualLED
from engine.events import Event, EventStatus
from engine.experiments import ExperimentSession
from engine.metrics import MetricsCollector
from engine.storage import StorageManager
from engine.time import (
    SimulationClock,
    SystemClock,
    TimestampService,
    get_timestamp_service,
    set_timestamp_service,
)


class TestSystemClockStandalone:
    def test_system_clock_now_and_offset(self):
        clock = SystemClock()
        assert clock.offset() == 0
        assert isinstance(clock.now(), int)
        n1 = clock.now()
        n2 = clock.timestamp()
        assert abs(n1 - n2) < 50

    def test_system_clock_synchronize_measures_without_correcting(self):
        clock = SystemClock()
        before_offset = clock.offset()
        observed = clock.synchronize(clock.now() - 50)
        assert isinstance(observed, int)
        assert clock.offset() == before_offset  # no correction applied
        assert clock.last_sync_time is not None


class TestClock:
    def test_simulation_clock_advance(self):
        clock = SimulationClock(start_ms=1000)
        assert clock.now() == 1000
        clock.advance(25)
        assert clock.now() == 1025


class TestTimestampService:
    def setup_method(self):
        self.clock = SimulationClock(start_ms=100)
        self.service = TimestampService(clock=self.clock)
        set_timestamp_service(self.service)

    def teardown_method(self):
        set_timestamp_service(None)

    def test_stamps_lifecycle_fields(self):
        event = Event.create(event_type="STATE_UPDATE", source="esp32_01", target="virtual_led_01")
        assert event.created_time == 100

        self.clock.advance(5)
        event.set_status(EventStatus.QUEUED)
        assert event.queued_time == 105

        self.clock.advance(3)
        event.set_status(EventStatus.DISPATCHED)
        assert event.dispatched_time == 108

        self.clock.advance(2)
        event.set_status(EventStatus.HANDLED)
        assert event.processed_time == 110

        self.clock.advance(8)
        event.set_status(EventStatus.COMPLETED)
        assert event.completed_time == 118

    def test_compute_latencies(self):
        event = Event.create(event_type="HELLO", source="esp32_01")
        self.clock.advance(5)
        event.set_status(EventStatus.QUEUED)
        self.clock.advance(3)
        event.set_status(EventStatus.DISPATCHED)
        self.clock.advance(2)
        event.set_status(EventStatus.HANDLED)
        self.clock.advance(8)
        event.set_status(EventStatus.COMPLETED)

        latencies = self.service.compute_latencies(event)
        assert latencies["queue_latency"] == 5.0
        assert latencies["dispatch_latency"] == 3.0
        assert latencies["processing_latency"] == 2.0
        assert latencies["total_latency"] == 18.0


class TestLatencyMetrics:
    def setup_method(self):
        self.clock = SimulationClock(start_ms=100)
        set_timestamp_service(TimestampService(clock=self.clock))

    def teardown_method(self):
        set_timestamp_service(None)

    def test_record_event_latencies(self):
        metrics = MetricsCollector()
        event = Event.create(event_type="STATE_UPDATE", source="a", target="b")
        self.clock.advance(10)
        event.set_status(EventStatus.QUEUED)
        self.clock.advance(4)
        event.set_status(EventStatus.DISPATCHED)
        self.clock.advance(1)
        event.set_status(EventStatus.HANDLED)
        self.clock.advance(3)
        event.set_status(EventStatus.COMPLETED)

        latencies = metrics.record_event_latencies(event)
        assert latencies["total_latency"] == 18.0
        snapshot = metrics.get_metrics()
        assert snapshot["total_latency"] == [18.0]
        assert snapshot["queue_latency"] == [10.0]
        assert snapshot["total_latency_avg_ms"] == 18.0


class TestDeviceClockMetadata:
    def test_virtual_device_has_clock_fields(self):
        led = VirtualLED("virtual_led_01")
        meta = led.get_metadata()
        assert meta["clock_id"] == "clock_virtual_led_01"
        assert meta["clock_type"] == "system"
        assert meta["clock_offset"] == 0
        assert meta["clock_drift"] == 0.0
        assert meta["last_sync_time"] is None
        assert meta["clock_offset_estimate"] == 0.0
        assert meta["clock_drift_estimate"] == 0.0
        assert meta["last_sync_measurement"] is None


class TestExperimentSession:
    def setup_method(self):
        self.clock = SimulationClock(start_ms=1000)
        set_timestamp_service(TimestampService(clock=self.clock))

    def teardown_method(self):
        set_timestamp_service(None)

    def test_start_record_finish_export(self, tmp_path):
        session = ExperimentSession(name="latency_smoke", experiment_id="EXP001")
        session.start(devices=["esp32_01", "virtual_led_01"])

        event = Event.create(
            event_type="STATE_UPDATE",
            source="esp32_01",
            target="virtual_led_01",
            payload={"state": "ON"},
        )
        self.clock.advance(5)
        event.set_status(EventStatus.QUEUED)
        self.clock.advance(5)
        event.set_status(EventStatus.DISPATCHED)
        self.clock.advance(2)
        event.set_status(EventStatus.HANDLED)
        self.clock.advance(6)
        event.set_status(EventStatus.COMPLETED)

        session.record_event(event)
        session.record_metric({"total_latency": 18.0})
        self.clock.advance(1)
        session.finish()

        export_root = session.export(base_dir=tmp_path / "experiments")
        assert export_root.name == "EXP001"
        assert (export_root / "events.jsonl").exists()
        assert (export_root / "metrics.jsonl").exists()
        assert (export_root / "summary.json").exists()

        summary = json.loads((export_root / "summary.json").read_text(encoding="utf-8"))
        assert summary["experiment_id"] == "EXP001"
        assert summary["event_count"] == 1
        assert summary["total_latency_avg_ms"] == 18.0

        line = (export_root / "events.jsonl").read_text(encoding="utf-8").strip()
        record = json.loads(line)
        assert record["latencies"]["total_latency"] == 18.0
        assert record["timing"]["created_time"] == 1000

    def test_storage_manager_export_experiment(self, tmp_path):
        storage = StorageManager(base_dir=tmp_path)
        session = ExperimentSession(name="via_storage", experiment_id="EXP002")
        session.start(devices=["esp32_01"])
        event = Event.create(event_type="HELLO", source="esp32_01")
        event.set_status(EventStatus.QUEUED)
        event.set_status(EventStatus.DISPATCHED)
        event.set_status(EventStatus.HANDLED)
        event.set_status(EventStatus.COMPLETED)
        session.record_event(event)
        session.finish()
        path = storage.export_experiment(session)
        assert path == tmp_path / "experiments" / "EXP002"
        assert (path / "summary.json").exists()
