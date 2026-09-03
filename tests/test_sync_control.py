"""Sprint 13 — synchronization control framework tests."""

import pytest

from engine.synchronization import (
    ClockCalibrationReport,
    CorrectionAction,
    CorrectionPolicy,
    InvalidSyncTransition,
    SyncQuality,
    SyncSession,
    SyncState,
    SynchronizationResult,
    SynchronizationSafetyConfig,
    SynchronizationScheduler,
)
from engine.time import SimulationClock, TimestampService, set_timestamp_service


class TestSynchronizationScheduler:
    def setup_method(self):
        self.clock = SimulationClock(start_ms=10_000)
        set_timestamp_service(TimestampService(clock=self.clock))
        self.triggered: list[str] = []
        self.scheduler = SynchronizationScheduler(
            default_interval_ms=1000,
            timestamp_service=TimestampService(clock=self.clock),
            on_trigger=self.triggered.append,
        )

    def teardown_method(self):
        set_timestamp_service(None)

    def test_schedule_and_next_sync_time(self):
        entry = self.scheduler.schedule("esp32_01", interval_ms=2000)
        assert entry.device_id == "esp32_01"
        assert self.scheduler.next_sync_time("esp32_01") == 12_000

    def test_poll_triggers_due_devices(self):
        self.scheduler.schedule("esp32_01", interval_ms=1000, start_at=10_000)
        self.scheduler.schedule("virtual_led_01", interval_ms=5000, start_at=10_000)
        assert self.scheduler.due_devices(at_time_ms=10_000) == []

        self.clock.advance(1000)
        triggered = self.scheduler.poll()
        assert triggered == ["esp32_01"]
        assert self.triggered == ["esp32_01"]
        assert self.scheduler.next_sync_time("esp32_01") == 12_000

    def test_cancel_stops_scheduling(self):
        self.scheduler.schedule("esp32_01")
        assert self.scheduler.cancel("esp32_01") is True
        assert self.scheduler.next_sync_time("esp32_01") is None
        self.clock.advance(10_000)
        assert self.scheduler.due_devices() == []


class TestSyncStateMachine:
    def test_valid_lifecycle_transitions(self):
        session = SyncSession(device_id="esp32_01")
        assert session.begin() == SyncState.MEASURING
        session.record_calibration(
            ClockCalibrationReport(
                device_id="esp32_01",
                initial_offset=10.0,
                final_offset=12.0,
                drift_rate=0.001,
                sample_count=5,
                confidence=0.9,
            )
        )
        assert session.state == SyncState.CALIBRATED
        assert session.enter_monitoring() == SyncState.MONITORING

    def test_invalid_transition_raises(self):
        session = SyncSession(device_id="d1")
        with pytest.raises(InvalidSyncTransition):
            session.transition_to(SyncState.CORRECTION_READY)

    def test_failed_recovery(self):
        session = SyncSession(device_id="d1")
        session.begin()
        session.mark_failed("test")
        assert session.state == SyncState.FAILED
        assert session.recover() == SyncState.MEASURING


class TestCorrectionPolicy:
    def test_ready_within_bounds(self):
        policy = CorrectionPolicy(
            SynchronizationSafetyConfig(
                maximum_offset=500.0,
                maximum_drift=0.01,
                minimum_confidence=0.6,
                maximum_uncertainty=100.0,
            )
        )
        decision = policy.evaluate(offset=50.0, drift=0.001, confidence=0.85, uncertainty=5.0)
        assert decision.action == CorrectionAction.READY
        assert decision.allowed is True

    def test_reject_excessive_offset(self):
        policy = CorrectionPolicy(SynchronizationSafetyConfig(maximum_offset=100.0))
        decision = policy.evaluate(offset=150.0, drift=0.0, confidence=0.9)
        assert decision.action == CorrectionAction.REJECT
        assert decision.allowed is False

    def test_defer_low_confidence(self):
        policy = CorrectionPolicy(SynchronizationSafetyConfig(minimum_confidence=0.8))
        decision = policy.evaluate(offset=10.0, drift=0.0, confidence=0.5)
        assert decision.action == CorrectionAction.DEFER
        assert decision.allowed is False


class TestSyncSessionLifecycle:
    def setup_method(self):
        self.clock = SimulationClock(start_ms=20_000)
        set_timestamp_service(TimestampService(clock=self.clock))

    def teardown_method(self):
        set_timestamp_service(None)

    def test_full_control_lifecycle(self):
        safety = SynchronizationSafetyConfig(
            maximum_offset=1000.0,
            maximum_drift=0.01,
            minimum_confidence=0.5,
            maximum_uncertainty=500.0,
        )
        policy = CorrectionPolicy(safety)
        scheduler = SynchronizationScheduler(
            default_interval_ms=2000,
            timestamp_service=TimestampService(clock=self.clock),
        )
        session = SyncSession(device_id="esp32_01")

        # 1. Schedule + begin measurement
        scheduler.schedule("esp32_01", interval_ms=2000)
        session.begin()
        assert session.state == SyncState.MEASURING

        # 2. Record sync result + quality
        result = SynchronizationResult(
            device_id="esp32_01",
            estimated_offset=45.0,
            sample_count=20,
            selected_samples=5,
            confidence=0.88,
            timestamp=self.clock.now(),
        )
        session.record_sync_result(result)
        session.record_quality(
            SyncQuality.from_samples("esp32_01", [8.0, 9.0, 10.0], [44.0, 45.0, 46.0])
        )
        scheduler.mark_synced("esp32_01")

        # 3. Calibration → MONITORING
        session.record_calibration(
            ClockCalibrationReport(
                device_id="esp32_01",
                initial_offset=40.0,
                final_offset=45.0,
                drift_rate=0.0005,
                sample_count=10,
                confidence=0.88,
            )
        )
        session.enter_monitoring()
        assert session.state == SyncState.MONITORING

        # 4. Policy evaluation → CORRECTION_READY (decision only)
        decision = session.evaluate_policy(
            policy,
            offset=45.0,
            drift=0.0005,
            confidence=0.88,
            uncertainty=10.0,
        )
        assert decision.action == CorrectionAction.READY
        assert session.state == SyncState.CORRECTION_READY
        assert session.last_decision["allowed"] is True

        # 5. Return to monitoring without applying correction
        session.enter_monitoring()
        assert session.state == SyncState.MONITORING
        assert session.to_dict()["state"] == "MONITORING"

        # 6. Next scheduled sync
        self.clock.advance(2000)
        assert scheduler.due_devices() == ["esp32_01"]

    def test_policy_failure_transitions_to_failed(self):
        session = SyncSession(device_id="esp32_01")
        session.begin()
        session.enter_monitoring()
        session.transition_to(SyncState.MONITORING)

        policy = CorrectionPolicy(SynchronizationSafetyConfig(maximum_offset=50.0))
        decision = session.evaluate_policy(
            policy, offset=200.0, drift=0.0, confidence=0.99
        )
        assert decision.action == CorrectionAction.REJECT
        assert session.state == SyncState.FAILED
