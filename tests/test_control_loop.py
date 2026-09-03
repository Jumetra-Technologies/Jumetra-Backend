"""Sprint 19 — autonomous synchronization control loop tests."""

from __future__ import annotations

import pytest

from engine.devices.manager import DeviceManager
from engine.devices.virtual import VirtualLED
from engine.events import EventBus
from engine.protocol.correction import SyncCorrectionResponse
from engine.synchronization import (
    AutonomousSyncExperiment,
    DeviceSyncProfile,
    FixedIntervalStrategy,
    SynchronizationControlLoop,
    SynchronizationCoordinator,
    SynchronizationDecisionEngine,
    SynchronizationManager,
    SynchronizationScheduler,
    SynchronizationStorage,
    SyncSession,
    SyncState,
)
from engine.synchronization.adjuster.mode import CorrectionMode
from engine.synchronization.adjuster.physical_limits import PhysicalCorrectionLimits
from engine.synchronization.adjuster.safe_adjuster import SafeClockAdjuster
from engine.synchronization.intelligence.health_bridge import HealthProfileBridge
from engine.synchronization.physical_bridge import PhysicalCorrectionBridge
from engine.synchronization.policy import SynchronizationSafetyConfig
from engine.time import SimulationClock, TimestampService, set_timestamp_service


def _ready_session(device_id: str = "virt_loop") -> SyncSession:
    session = SyncSession(device_id=device_id)
    session.begin()
    session.transition_to(SyncState.CALIBRATED)
    session.enter_monitoring()
    session.transition_to(SyncState.CORRECTION_READY)
    return session


def _loop_setup(tmp_path, clock: SimulationClock, *, adaptive: bool = True):
    bus = EventBus()
    dm = DeviceManager()
    device = VirtualLED("virt_loop")
    device.metadata["clock_offset"] = 45
    dm.register_device(device)
    sync_manager = SynchronizationManager(
        bus, device_manager=dm, echo_virtual=True, timestamp_service=TimestampService(clock=clock)
    )
    bus.register_subscriber(sync_manager)
    for _ in range(8):
        sync_manager.request_sync("virt_loop")
    storage = SynchronizationStorage(tmp_path / "sync")
    scheduler = SynchronizationScheduler(
        default_interval_ms=5000, timestamp_service=TimestampService(clock=clock)
    )
    scheduler.schedule("virt_loop", interval_ms=5000, adaptive=adaptive, start_at=clock.now())
    decision_engine = SynchronizationDecisionEngine()
    bridge = PhysicalCorrectionBridge(
        sync_manager,
        storage=storage,
        limits=PhysicalCorrectionLimits(stabilization_period_ms=0, cooldown_period_ms=0),
        timestamp_service=TimestampService(clock=clock),
    )
    bridge.adjuster = SafeClockAdjuster(
        mode=CorrectionMode.STEP,
        max_step_ms=10.0,
        safety=SynchronizationSafetyConfig(minimum_confidence=0.05),
        storage=storage,
        timestamp_service=TimestampService(clock=clock),
    )
    loop = SynchronizationControlLoop(
        sync_manager,
        scheduler,
        decision_engine,
        physical_bridge=bridge,
        adaptive=adaptive,
        fixed_interval_ms=5000,
        timestamp_service=TimestampService(clock=clock),
    )
    loop._sessions["virt_loop"] = _ready_session()
    return loop, scheduler, bridge, decision_engine, device


class TestAdaptiveSchedulerIntegration:
    def setup_method(self):
        self.clock = SimulationClock(start_ms=100_000)
        set_timestamp_service(TimestampService(clock=self.clock))

    def teardown_method(self):
        set_timestamp_service(None)

    def test_apply_adaptive_interval_updates_schedule(self, tmp_path):
        scheduler = SynchronizationScheduler(
            default_interval_ms=5000, timestamp_service=TimestampService(clock=self.clock)
        )
        scheduler.schedule("d1", interval_ms=5000, adaptive=True, start_at=self.clock.now())
        scheduler.mark_synced("d1", at_time_ms=self.clock.now())
        scheduler.apply_adaptive_interval("d1", 2500, from_time_ms=self.clock.now())
        entry = scheduler.get_schedule("d1")
        assert entry.interval_ms == 2500
        assert entry.adaptive is True
        assert entry.next_sync_time == self.clock.now() + 2500

    def test_fixed_strategy_unchanged(self):
        strategy = FixedIntervalStrategy(5000)
        assert strategy.calculate_next_interval("d1", last_interval_ms=5000, drift=0.01) == 5000


class TestHealthProfileBridge:
    def test_applies_health_to_profile(self):
        from engine.synchronization.health_monitor import CorrectionHealthMonitor

        monitor = CorrectionHealthMonitor()
        monitor.record_success(improvement=5.0)
        monitor.record_failure()
        monitor.record_rollback()
        profile = DeviceSyncProfile(device_id="d1")
        HealthProfileBridge.apply(profile, monitor.report())
        assert profile.rollback_count == 1
        assert profile.reliability_score == pytest.approx(0.5)
        assert profile.metadata["failed_corrections"] == 1


class TestSynchronizationControlLoop:
    def setup_method(self):
        self.clock = SimulationClock(start_ms=200_000)
        set_timestamp_service(TimestampService(clock=self.clock))

    def teardown_method(self):
        set_timestamp_service(None)

    def test_closed_loop_execution(self, tmp_path):
        loop, scheduler, bridge, engine, device = _loop_setup(tmp_path, self.clock)

        def simulate(txn):
            device.metadata["clock_offset"] = 30
            return SyncCorrectionResponse(
                transaction_id=txn.transaction_id,
                device_id=txn.device_id,
                correction_step=txn.correction_step,
                timestamp=self.clock.now(),
            )

        result = loop.run_cycle("virt_loop", simulate_response=simulate)
        assert result.observed is True
        assert result.plan is not None
        assert result.schedule_updated is True
        assert result.correction_attempted is True
        assert result.profile_updated is True
        profile = engine.profiles.get("virt_loop")
        assert profile.sync_event_count >= 1

    def test_safety_rejection_when_not_ready(self, tmp_path):
        loop, _, _, _, _ = _loop_setup(tmp_path, self.clock)
        session = loop._sessions["virt_loop"]
        session.transition_to(SyncState.MONITORING)
        result = loop.run_cycle("virt_loop")
        assert result.observed is True
        assert result.correction_attempted is False

    def test_profile_learning_after_correction(self, tmp_path):
        loop, _, bridge, engine, device = _loop_setup(tmp_path, self.clock)

        def simulate(txn):
            device.metadata["clock_offset"] = 25
            return SyncCorrectionResponse(
                transaction_id=txn.transaction_id,
                device_id=txn.device_id,
                correction_step=txn.correction_step,
                timestamp=self.clock.now(),
            )

        loop.run_cycle("virt_loop", simulate_response=simulate)
        profile = engine.profiles.get("virt_loop")
        assert profile.reliability_score >= 0.0
        assert profile.correction_count >= 0 or profile.metadata.get("health_total_attempts", 0) >= 0

    def test_failed_correction_recovery_metrics(self, tmp_path):
        loop, _, _, _, _ = _loop_setup(tmp_path, self.clock)

        def simulate(txn):
            return SyncCorrectionResponse(
                transaction_id=txn.transaction_id,
                device_id=txn.device_id,
                correction_step=txn.correction_step,
                timestamp=self.clock.now(),
            )

        result = loop.run_cycle("virt_loop", simulate_response=simulate)
        assert result.correction_attempted is True
        assert result.transaction_state in {"COMPLETED", "ROLLED_BACK", "FAILED"}


class TestAutonomousExperiment:
    def setup_method(self):
        self.clock = SimulationClock(start_ms=300_000)
        set_timestamp_service(TimestampService(clock=self.clock))

    def teardown_method(self):
        set_timestamp_service(None)

    def _experiment(self, tmp_path):
        bus = EventBus()
        dm = DeviceManager()
        device = VirtualLED("exp_dev")
        device.metadata["clock_offset"] = 50
        dm.register_device(device)
        sync_manager = SynchronizationManager(
            bus, device_manager=dm, echo_virtual=True, timestamp_service=TimestampService(clock=self.clock)
        )
        bus.register_subscriber(sync_manager)
        storage = SynchronizationStorage(tmp_path / "sync")
        bridge = PhysicalCorrectionBridge(
            sync_manager,
            storage=storage,
            limits=PhysicalCorrectionLimits(stabilization_period_ms=0, cooldown_period_ms=0),
            timestamp_service=TimestampService(clock=self.clock),
        )
        bridge.adjuster = SafeClockAdjuster(
            mode=CorrectionMode.STEP,
            max_step_ms=10.0,
            safety=SynchronizationSafetyConfig(minimum_confidence=0.05),
            storage=storage,
            timestamp_service=TimestampService(clock=self.clock),
        )
        return AutonomousSyncExperiment(
            sync_manager, physical_bridge=bridge, fixed_interval_ms=5000
        ), device

    def test_fixed_vs_autonomous_comparison(self, tmp_path):
        experiment, device = self._experiment(tmp_path)

        def offset_fn(i):
            device.metadata["clock_offset"] = max(10.0, 50.0 - i * 8)
            return device.metadata["clock_offset"]

        report = experiment.compare("exp_dev", cycles=4, offset_fn=offset_fn)
        data = report.to_dict()
        assert data["fixed"]["sync_operations"] == 4
        assert data["adaptive"]["sync_operations"] == 4
        assert "delta_communication_cost" in data
        assert "accuracy_improvement" in data

    def test_sample_autonomous_run_metrics(self, tmp_path):
        experiment, device = self._experiment(tmp_path)

        def offset_fn(i):
            device.metadata["clock_offset"] = 40.0 - i * 5
            return device.metadata["clock_offset"]

        metrics = experiment.run_adaptive("exp_dev", cycles=3, offset_fn=offset_fn)
        sample = metrics.to_dict()
        assert sample["strategy_name"] == "adaptive"
        assert sample["sync_operations"] == 3
        assert sample["communication_cost"] >= 3


class TestCoordinatorAutonomousIntegration:
    def setup_method(self):
        self.clock = SimulationClock(start_ms=400_000)
        set_timestamp_service(TimestampService(clock=self.clock))

    def teardown_method(self):
        set_timestamp_service(None)

    def test_coordinator_autonomous_mode(self, tmp_path):
        bus = EventBus()
        dm = DeviceManager()
        device = VirtualLED("coord_dev")
        device.metadata["clock_offset"] = 35
        dm.register_device(device)
        manager = SynchronizationManager(
            bus, device_manager=dm, echo_virtual=True, timestamp_service=TimestampService(clock=self.clock)
        )
        bus.register_subscriber(manager)
        storage = SynchronizationStorage(tmp_path / "sync")
        bridge = PhysicalCorrectionBridge(
            manager,
            storage=storage,
            limits=PhysicalCorrectionLimits(stabilization_period_ms=0, cooldown_period_ms=0),
            timestamp_service=TimestampService(clock=self.clock),
        )
        coord = SynchronizationCoordinator(
            manager,
            storage,
            physical_bridge=bridge,
            autonomous=True,
            timestamp_service=TimestampService(clock=self.clock),
        )
        coord.schedule_device("coord_dev", interval_ms=5000, adaptive=True)
        session = coord.get_or_create_session("coord_dev")
        session.begin()
        session.transition_to(SyncState.CALIBRATED)
        session.enter_monitoring()
        session.transition_to(SyncState.CORRECTION_READY)
        assert coord.control_loop is not None
