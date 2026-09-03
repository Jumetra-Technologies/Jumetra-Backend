"""Sprint 14 — sync engine integration, storage, recovery, audit tests."""

import json

import pytest

from engine.events import EventBus
from engine.main import HHIPEngine
from engine.communication.memory_adapter import make_adapter_pair
from engine.synchronization import (
    ClockCalibrationReport,
    CorrectionPolicy,
    FixedIntervalStrategy,
    SyncSession,
    SyncState,
    SynchronizationCoordinator,
    SynchronizationManager,
    SynchronizationStorage,
)
from engine.synchronization.strategy import AdaptiveStrategy
from engine.time import ClockModel, SimulationClock, TimestampService, set_timestamp_service


class TestSynchronizationStorage:
    def test_save_and_load_sessions(self, tmp_path):
        storage = SynchronizationStorage(tmp_path / "sync")
        session = SyncSession(device_id="esp32_01", state=SyncState.MONITORING)
        session.last_sync_time = 12345
        storage.save_session(session)

        loaded = storage.load_sessions()
        assert "esp32_01" in loaded
        assert loaded["esp32_01"].state == SyncState.MONITORING
        assert loaded["esp32_01"].last_sync_time == 12345

    def test_clock_model_and_calibration_persistence(self, tmp_path):
        storage = SynchronizationStorage(tmp_path / "sync")
        model = ClockModel(clock_id="esp32_01")
        model.update_measurement(42.0, 1000)
        storage.save_clock_model(model)
        storage.save_calibration(
            "esp32_01",
            ClockCalibrationReport(
                device_id="esp32_01",
                initial_offset=40.0,
                final_offset=42.0,
                drift_rate=0.001,
                sample_count=5,
                confidence=0.9,
            ),
        )

        models = storage.load_clock_models()
        cals = storage.load_calibrations()
        assert models["esp32_01"].current_offset == 42.0
        assert cals["esp32_01"]["drift_rate"] == 0.001

    def test_audit_log_jsonl(self, tmp_path):
        storage = SynchronizationStorage(tmp_path / "sync")
        storage.append_audit(
            timestamp=5000,
            device_id="esp32_01",
            decision="ready",
            offset=45.0,
            drift=0.0005,
            confidence=0.88,
        )
        lines = storage.decisions_path.read_text(encoding="utf-8").strip().splitlines()
        record = json.loads(lines[0])
        assert record["device_id"] == "esp32_01"
        assert record["decision"] == "ready"
        assert record["offset"] == 45.0
        assert record["drift"] == 0.0005
        assert record["confidence"] == 0.88


class TestSyncIntervalStrategy:
    def test_fixed_interval(self):
        strategy = FixedIntervalStrategy(interval_ms=3000)
        assert strategy.calculate_next_interval("d1", last_interval_ms=5000) == 3000

    def test_adaptive_interval(self):
        strategy = AdaptiveStrategy()
        interval = strategy.calculate_next_interval(
            "d1",
            last_interval_ms=5000,
            drift=0.002,
            confidence=0.75,
            quality={"jitter": 3.0, "average_rtt": 25.0, "confidence_score": 0.75},
        )
        assert isinstance(interval, int)
        assert interval >= 1000


class TestSynchronizationRecovery:
    def setup_method(self):
        self.clock = SimulationClock(start_ms=100_000)
        set_timestamp_service(TimestampService(clock=self.clock))

    def teardown_method(self):
        set_timestamp_service(None)

    def _coordinator(self, tmp_path) -> SynchronizationCoordinator:
        bus = EventBus()
        manager = SynchronizationManager(
            bus,
            timestamp_service=TimestampService(clock=self.clock),
        )
        bus.register_subscriber(manager)
        storage = SynchronizationStorage(tmp_path / "sync")
        return SynchronizationCoordinator(
            manager,
            storage,
            strategy=FixedIntervalStrategy(1000),
            default_interval_ms=1000,
            timestamp_service=TimestampService(clock=self.clock),
        )

    def test_recovery_restores_session_and_model(self, tmp_path):
        coord = self._coordinator(tmp_path)
        coord.schedule_device("virtual_led_01")
        coord.scheduler.schedule("virtual_led_01", interval_ms=1000, start_at=100_000)

        session = coord.get_or_create_session("virtual_led_01")
        session.begin()
        session.record_calibration(
            ClockCalibrationReport(
                device_id="virtual_led_01",
                initial_offset=50.0,
                final_offset=55.0,
                drift_rate=0.0001,
                sample_count=3,
                confidence=0.8,
            )
        )
        session.enter_monitoring()
        model = coord.get_or_create_clock_model("virtual_led_01")
        model.update_measurement(55.0, 100_500)
        coord.storage.save_all(
            sessions=coord.sessions,
            clock_models=coord.clock_models,
            schedules=coord.scheduler.all_schedules(),
        )
        coord.shutdown()

        coord2 = self._coordinator(tmp_path)
        coord2.startup()
        assert "virtual_led_01" in coord2.sessions
        assert coord2.clock_models["virtual_led_01"].current_offset == 55.0
        assert coord2.scheduler.get_schedule("virtual_led_01") is not None


class TestHHIPEngineSyncIntegration:
    def setup_method(self):
        self.clock = SimulationClock(start_ms=50_000)
        set_timestamp_service(TimestampService(clock=self.clock))

    def teardown_method(self):
        set_timestamp_service(None)

    def _engine(self, tmp_path, interval_ms: int = 500) -> HHIPEngine:
        engine_adapter, _ = make_adapter_pair(timeout=0.01)
        engine_adapter.connect()
        return HHIPEngine(
            adapter=engine_adapter,
            storage_dir=str(tmp_path / "data"),
            persist_events=False,
            sync_enabled=True,
            sync_interval_ms=interval_ms,
        )

    def test_startup_shutdown_persistence(self, tmp_path):
        engine = self._engine(tmp_path)
        engine.sync_startup()
        engine.sync_coordinator.schedule_device("virtual_led_01")
        engine.sync_shutdown()

        assert (tmp_path / "data" / "synchronization" / "state.json").exists()

        engine2 = self._engine(tmp_path)
        engine2.sync_startup()
        assert "virtual_led_01" in engine2.sync_coordinator.sessions

    def test_runtime_poll_triggers_measurement_and_audit(self, tmp_path):
        engine = self._engine(tmp_path, interval_ms=100)
        engine.sync_startup()
        engine.sync_coordinator.schedule_device(
            "virtual_led_01", interval_ms=100
        )
        # Make device due immediately
        schedule = engine.sync_coordinator.scheduler.get_schedule("virtual_led_01")
        assert schedule is not None
        schedule.next_sync_time = self.clock.now()

        triggered = engine.sync_poll()
        assert triggered == ["virtual_led_01"]
        assert len(engine.sync_manager.get_measurements()) >= 1

        engine.sync_shutdown()
        audit_path = tmp_path / "data" / "synchronization" / "sync_decisions.jsonl"
        assert audit_path.exists()
        record = json.loads(audit_path.read_text(encoding="utf-8").strip().splitlines()[0])
        assert record["device_id"] == "virtual_led_01"
        assert "decision" in record
        assert "offset" in record

    def test_sample_recovered_session(self, tmp_path):
        engine = self._engine(tmp_path)
        engine.sync_startup()
        session = engine.sync_coordinator.get_or_create_session("virtual_led_01")
        if session.state == SyncState.UNKNOWN:
            session.begin()
        session.record_calibration(
            ClockCalibrationReport(
                device_id="virtual_led_01",
                initial_offset=10.0,
                final_offset=12.0,
                drift_rate=0.0002,
                sample_count=8,
                confidence=0.87,
            )
        )
        session.enter_monitoring()
        engine.sync_coordinator.clock_models["virtual_led_01"] = ClockModel(
            clock_id="virtual_led_01"
        )
        engine.sync_coordinator.clock_models["virtual_led_01"].update_measurement(
            12.0, self.clock.now()
        )
        engine.sync_shutdown()

        state = json.loads(
            (tmp_path / "data" / "synchronization" / "state.json").read_text(encoding="utf-8")
        )
        recovered = state["sessions"]["virtual_led_01"]
        assert recovered["state"] == "MONITORING"
        assert recovered["calibration"]["drift_rate"] == 0.0002
        assert state["clock_models"]["virtual_led_01"]["current_offset"] == 12.0
