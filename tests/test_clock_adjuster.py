"""Sprint 15 — safe bounded clock adjustment tests."""

import json

import pytest

from engine.synchronization import (
    CorrectionMode,
    CorrectionPolicy,
    SafeClockAdjuster,
    SyncSession,
    SyncState,
    SynchronizationSafetyConfig,
    SynchronizationStorage,
)
from engine.synchronization.adjuster.safety_gate import CorrectionSafetyGate
from engine.time import ClockModel, SimulationClock, TimestampService, set_timestamp_service


def _ready_session(device_id: str = "esp32_01") -> SyncSession:
    session = SyncSession(device_id=device_id)
    session.begin()
    session.transition_to(SyncState.CALIBRATED)
    session.enter_monitoring()
    session.transition_to(SyncState.CORRECTION_READY)
    return session


class TestCorrectionSafetyGate:
    def test_rejects_non_ready_state(self):
        session = SyncSession(device_id="d1")
        session.begin()
        gate = CorrectionSafetyGate()
        result = gate.check(session, offset=10.0, drift=0.0, confidence=0.9)
        assert result.passed is False

    def test_passes_when_ready_and_within_bounds(self):
        session = _ready_session()
        gate = CorrectionSafetyGate()
        result = gate.check(session, offset=50.0, drift=0.001, confidence=0.85)
        assert result.passed is True


class TestSafeClockAdjuster:
    def setup_method(self):
        self.clock = SimulationClock(start_ms=100_000)
        set_timestamp_service(TimestampService(clock=self.clock))

    def teardown_method(self):
        set_timestamp_service(None)

    def test_dry_run_bounded_estimate(self, tmp_path):
        storage = SynchronizationStorage(tmp_path / "sync")
        adjuster = SafeClockAdjuster(
            mode=CorrectionMode.DRY_RUN,
            max_step_ms=10.0,
            storage=storage,
        )
        session = _ready_session()
        estimate = adjuster.estimate_correction(
            session.device_id, 100.0, session, confidence=0.9
        )
        assert estimate.allowed is True
        assert estimate.step_size == 10.0
        assert estimate.remaining_offset == 90.0

        result = adjuster.apply_correction(session.device_id, estimate)
        assert result.dry_run is True
        assert result.applied is False
        assert result.step_applied == 10.0

        events = [json.loads(l) for l in storage.decisions_path.read_text().strip().splitlines()]
        assert events[0]["event"] == "correction_attempt"
        assert events[1]["event"] == "correction_applied"

    def test_rejected_when_not_correction_ready(self, tmp_path):
        adjuster = SafeClockAdjuster(storage=SynchronizationStorage(tmp_path / "sync"))
        session = SyncSession(device_id="d1")
        session.begin()
        estimate = adjuster.estimate_correction("d1", 50.0, session, confidence=0.99)
        assert estimate.rejected is True
        result = adjuster.apply_correction("d1", estimate)
        assert result.applied is False

    def test_rejected_unsafe_offset(self, tmp_path):
        safety = SynchronizationSafetyConfig(maximum_offset=50.0)
        adjuster = SafeClockAdjuster(
            safety=safety,
            storage=SynchronizationStorage(tmp_path / "sync"),
        )
        session = _ready_session()
        estimate = adjuster.estimate_correction(
            session.device_id, 100.0, session, confidence=0.99
        )
        assert estimate.rejected is True

    def test_step_mode_applies_and_rollback(self, tmp_path):
        storage = SynchronizationStorage(tmp_path / "sync")
        adjuster = SafeClockAdjuster(
            mode=CorrectionMode.STEP,
            max_step_ms=10.0,
            storage=storage,
        )
        session = _ready_session()
        model = ClockModel(clock_id=session.device_id)
        model.update_measurement(100.0, 100_000)

        estimate = adjuster.estimate_correction(
            session.device_id, 100.0, session, confidence=0.9, clock_model=model
        )
        result = adjuster.apply_correction(
            session.device_id, estimate, clock_model=model
        )
        assert result.applied is True
        assert model.applied_correction == 10.0
        assert model.effective_offset == 90.0
        assert model.remaining_correction == 90.0

        rollback = adjuster.rollback(session.device_id, clock_model=model)
        assert rollback.success is True
        assert model.applied_correction == 0.0

        events = [json.loads(l)["event"] for l in storage.decisions_path.read_text().strip().splitlines()]
        assert "correction_attempt" in events
        assert "correction_applied" in events
        assert "rollback" in events

    def test_verify_improvement(self):
        adjuster = SafeClockAdjuster(mode=CorrectionMode.STEP, max_step_ms=10.0)
        model = ClockModel(clock_id="d1")
        model.update_measurement(100.0, 1000)
        model.apply_bounded_correction(10.0)

        verify = adjuster.verify(
            "d1",
            offset_before=100.0,
            measure_fn=lambda: model.effective_offset,
            step_applied=10.0,
        )
        assert verify.offset_before == 100.0
        assert verify.offset_after == 90.0
        assert verify.improvement == 10.0
        assert verify.verified is True

    def test_disabled_mode(self):
        adjuster = SafeClockAdjuster(mode=CorrectionMode.DISABLED)
        session = _ready_session()
        estimate = adjuster.estimate_correction(
            session.device_id, 20.0, session, confidence=0.99
        )
        assert estimate.rejected is True


class TestCoordinatorCorrection:
    def setup_method(self):
        self.clock = SimulationClock(start_ms=50_000)
        set_timestamp_service(TimestampService(clock=self.clock))

    def teardown_method(self):
        set_timestamp_service(None)

    def test_attempt_correction_dry_run(self, tmp_path):
        from engine.events import EventBus
        from engine.synchronization import SynchronizationCoordinator, SynchronizationManager

        bus = EventBus()
        manager = SynchronizationManager(
            bus, timestamp_service=TimestampService(clock=self.clock)
        )
        bus.register_subscriber(manager)
        storage = SynchronizationStorage(tmp_path / "sync")
        coord = SynchronizationCoordinator(
            manager, storage, timestamp_service=TimestampService(clock=self.clock)
        )
        adjuster = SafeClockAdjuster(
            mode=CorrectionMode.DRY_RUN, max_step_ms=10.0, storage=storage
        )

        session = coord.get_or_create_session("virtual_led_01")
        session.begin()
        session.transition_to(SyncState.CALIBRATED)
        session.enter_monitoring()
        session.transition_to(SyncState.CORRECTION_READY)

        model = coord.get_or_create_clock_model("virtual_led_01")
        model.update_measurement(100.0, self.clock.now())

        result = coord.attempt_correction(
            "virtual_led_01", adjuster, confidence=0.9
        )
        assert result.dry_run is True
        assert result.step_applied == 10.0

        audit = storage.load_decisions()
        assert any(r.get("event") == "correction_attempt" for r in audit)
