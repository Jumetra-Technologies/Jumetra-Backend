"""Autonomous synchronization experiment — fixed vs adaptive closed loop."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Optional

from ..physical_bridge import PhysicalCorrectionBridge
from ..scheduler import SynchronizationScheduler
from ..strategy import FixedIntervalStrategy
from ..sync_session import SyncSession
from ..state import SyncState
from ..intelligence.decision_engine import SynchronizationDecisionEngine
from ..manager import SynchronizationManager
from .loop import SynchronizationControlLoop
from .result import ControlLoopCycleResult

AdvanceFn = Callable[[int], None]
OffsetFn = Callable[[int], float]


@dataclass
class AutonomousRunMetrics:
    """Metrics collected during an autonomous synchronization run."""

    strategy_name: str
    sync_operations: int = 0
    communication_cost: int = 0
    correction_attempts: int = 0
    correction_successes: int = 0
    correction_failures: int = 0
    rollbacks: int = 0
    recovery_events: int = 0
    average_interval_ms: float = 0.0
    correction_accuracy: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AutonomousComparisonReport:
    """Fixed vs adaptive autonomous synchronization comparison."""

    fixed: AutonomousRunMetrics
    adaptive: AutonomousRunMetrics

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixed": self.fixed.to_dict(),
            "adaptive": self.adaptive.to_dict(),
            "delta_sync_operations": self.adaptive.sync_operations - self.fixed.sync_operations,
            "delta_communication_cost": (
                self.adaptive.communication_cost - self.fixed.communication_cost
            ),
            "accuracy_improvement": (
                self.adaptive.correction_accuracy - self.fixed.correction_accuracy
            ),
            "delta_failures": (
                self.adaptive.correction_failures - self.fixed.correction_failures
            ),
            "delta_recovery_events": (
                self.adaptive.recovery_events - self.fixed.recovery_events
            ),
        }


class AutonomousSyncExperiment:
    """Compare fixed-interval vs adaptive autonomous control loops."""

    def __init__(
        self,
        sync_manager: SynchronizationManager,
        *,
        physical_bridge: Optional[PhysicalCorrectionBridge] = None,
        fixed_interval_ms: int = 5_000,
        decision_engine: Optional[SynchronizationDecisionEngine] = None,
    ) -> None:
        self.sync_manager = sync_manager
        self.physical_bridge = physical_bridge
        self.fixed_interval_ms = fixed_interval_ms
        self.decision_engine = decision_engine or SynchronizationDecisionEngine()

    def run_fixed(
        self,
        device_id: str,
        *,
        cycles: int = 5,
        offset_fn: Optional[OffsetFn] = None,
        advance_clock: Optional[AdvanceFn] = None,
        simulate_correction: bool = True,
    ) -> AutonomousRunMetrics:
        return self._run(
            "fixed",
            device_id,
            cycles=cycles,
            adaptive=False,
            offset_fn=offset_fn,
            advance_clock=advance_clock,
            simulate_correction=simulate_correction,
        )

    def run_adaptive(
        self,
        device_id: str,
        *,
        cycles: int = 5,
        offset_fn: Optional[OffsetFn] = None,
        advance_clock: Optional[AdvanceFn] = None,
        simulate_correction: bool = True,
    ) -> AutonomousRunMetrics:
        return self._run(
            "adaptive",
            device_id,
            cycles=cycles,
            adaptive=True,
            offset_fn=offset_fn,
            advance_clock=advance_clock,
            simulate_correction=simulate_correction,
        )

    def compare(
        self,
        device_id: str,
        *,
        cycles: int = 5,
        offset_fn: Optional[OffsetFn] = None,
        advance_clock: Optional[AdvanceFn] = None,
    ) -> AutonomousComparisonReport:
        fixed = self.run_fixed(
            device_id, cycles=cycles, offset_fn=offset_fn, advance_clock=advance_clock
        )
        adaptive = self.run_adaptive(
            device_id, cycles=cycles, offset_fn=offset_fn, advance_clock=advance_clock
        )
        return AutonomousComparisonReport(fixed=fixed, adaptive=adaptive)

    def _run(
        self,
        name: str,
        device_id: str,
        *,
        cycles: int,
        adaptive: bool,
        offset_fn: Optional[OffsetFn],
        advance_clock: Optional[AdvanceFn],
        simulate_correction: bool,
    ) -> AutonomousRunMetrics:
        scheduler = SynchronizationScheduler(default_interval_ms=self.fixed_interval_ms)
        scheduler.schedule(device_id, interval_ms=self.fixed_interval_ms, adaptive=adaptive, start_at=0)

        loop = SynchronizationControlLoop(
            self.sync_manager,
            scheduler,
            self.decision_engine,
            physical_bridge=self.physical_bridge,
            adaptive=adaptive,
            fixed_interval_ms=self.fixed_interval_ms,
        )

        session = SyncSession(device_id=device_id)
        session.begin()
        session.transition_to(SyncState.CALIBRATED)
        session.enter_monitoring()
        session.transition_to(SyncState.CORRECTION_READY)
        loop._sessions[device_id] = session

        metrics = AutonomousRunMetrics(strategy_name=name)
        interval_total = 0

        for i in range(cycles):
            if offset_fn is not None and hasattr(self.sync_manager, "_device_manager"):
                dm = self.sync_manager._device_manager
                if dm is not None:
                    device = dm.get_device(device_id)
                    if device is not None:
                        device.metadata["clock_offset"] = offset_fn(i)

            simulate = None
            if simulate_correction and self.physical_bridge is not None:

                def simulate(txn, step=i):
                    from engine.protocol.correction import SyncCorrectionResponse

                    improved = max(5.0, 40.0 - (step + 1) * 5)
                    if offset_fn and hasattr(self.sync_manager, "_device_manager"):
                        dm = self.sync_manager._device_manager
                        if dm is not None:
                            dev = dm.get_device(device_id)
                            if dev is not None:
                                dev.metadata["clock_offset"] = improved
                    return SyncCorrectionResponse(
                        transaction_id=txn.transaction_id,
                        device_id=txn.device_id,
                        correction_step=txn.correction_step,
                        timestamp=0,
                    )

            result = loop.run_cycle(
                device_id,
                simulate_response=simulate if simulate_correction else None,
                advance_clock=advance_clock,
            )
            self._accumulate(metrics, result, scheduler, device_id)
            interval_total += scheduler.get_schedule(device_id).interval_ms if scheduler.get_schedule(device_id) else self.fixed_interval_ms

            if advance_clock is not None:
                schedule = scheduler.get_schedule(device_id)
                if schedule:
                    advance_clock(max(1, schedule.interval_ms))

        metrics.average_interval_ms = interval_total / cycles if cycles else 0.0
        if metrics.correction_attempts:
            metrics.correction_accuracy = (
                metrics.correction_successes / metrics.correction_attempts
            )
        else:
            metrics.correction_accuracy = 1.0
        return metrics

    def _accumulate(
        self,
        metrics: AutonomousRunMetrics,
        result: ControlLoopCycleResult,
        scheduler: SynchronizationScheduler,
        device_id: str,
    ) -> None:
        if result.observed:
            metrics.sync_operations += 1
            metrics.communication_cost += 1
        if result.correction_attempted:
            metrics.correction_attempts += 1
            metrics.communication_cost += 1
        if result.correction_verified:
            metrics.correction_successes += 1
        if result.rejected and result.correction_attempted:
            metrics.correction_failures += 1
        if result.transaction_state == "ROLLED_BACK":
            metrics.rollbacks += 1
        metrics.recovery_events += result.recovery_events
