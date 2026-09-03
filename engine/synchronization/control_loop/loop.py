"""SynchronizationControlLoop — closed-loop autonomous synchronization."""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional, Union

from ...time.clock_model import ClockModel
from ...time.timestamp_service import TimestampService, get_timestamp_service
from ..intelligence.decision_engine import SynchronizationDecisionEngine, SynchronizationPlan
from ..intelligence.health_bridge import HealthProfileBridge
from ..manager import SynchronizationManager
from ..physical_bridge import PhysicalCorrectionBridge
from ..policy import CorrectionAction, CorrectionPolicy
from ..scheduler import SynchronizationScheduler
from ..state import SyncState
from ..strategy import FixedIntervalStrategy
from ..sync_session import SyncSession
from ..transactions.state import TransactionState
from .result import ControlLoopCycleResult

logger = logging.getLogger("hhip.synchronization.control_loop")

AdvanceFn = Callable[[int], None]
SimulateResponse = Union[Any, Callable[[Any], Any]]
SessionProvider = Callable[[str], SyncSession]
ClockModelProvider = Callable[[str], ClockModel]


class SynchronizationControlLoop:
    """Closed-loop: observe → plan → schedule → correct → verify → profile update.

    Never bypasses PhysicalCorrectionBridge safety (SafetyGate, TransactionManager,
    VerificationLoop, Rollback).
    """

    def __init__(
        self,
        sync_manager: SynchronizationManager,
        scheduler: SynchronizationScheduler,
        decision_engine: SynchronizationDecisionEngine,
        *,
        physical_bridge: Optional[PhysicalCorrectionBridge] = None,
        policy: Optional[CorrectionPolicy] = None,
        get_session: Optional[SessionProvider] = None,
        get_clock_model: Optional[ClockModelProvider] = None,
        adaptive: bool = True,
        fixed_interval_ms: int = 5_000,
        timestamp_service: Optional[TimestampService] = None,
    ) -> None:
        self.sync_manager = sync_manager
        self.scheduler = scheduler
        self.decision_engine = decision_engine
        self.physical_bridge = physical_bridge
        self.policy = policy or CorrectionPolicy()
        self._get_session = get_session
        self._get_clock_model = get_clock_model
        self.adaptive = adaptive
        self.fixed_strategy = FixedIntervalStrategy(fixed_interval_ms)
        self._ts = timestamp_service or get_timestamp_service()
        self._sessions: dict[str, SyncSession] = {}
        self._clock_models: dict[str, ClockModel] = {}

    def bind_providers(
        self,
        *,
        get_session: SessionProvider,
        get_clock_model: ClockModelProvider,
    ) -> None:
        self._get_session = get_session
        self._get_clock_model = get_clock_model

    def handle_scheduled_trigger(self, device_id: str) -> ControlLoopCycleResult:
        """Scheduler callback — run one full control cycle."""
        return self.run_cycle(device_id)

    def poll(self) -> list[ControlLoopCycleResult]:
        """Poll scheduler and run cycles for all due devices."""
        results: list[ControlLoopCycleResult] = []
        due_before = set(self.scheduler.due_devices(at_time_ms=self._ts.now()))
        for device_id in due_before:
            results.append(self.run_cycle(device_id))
        return results

    def run_cycle(
        self,
        device_id: str,
        *,
        simulate_response: Optional[SimulateResponse] = None,
        advance_clock: Optional[AdvanceFn] = None,
    ) -> ControlLoopCycleResult:
        """Execute one observe → plan → schedule → correct → verify → profile cycle."""
        result = ControlLoopCycleResult(device_id=device_id)
        session = self._session(device_id)
        model = self._clock_model(device_id)

        if session.state == SyncState.UNKNOWN:
            session.begin()
        elif session.state in (SyncState.MONITORING, SyncState.CALIBRATED):
            if session._state_machine.can_transition(SyncState.MEASURING):
                session.transition_to(SyncState.MEASURING)

        # --- observe & collect measurements ---
        self.sync_manager.request_sync(device_id)
        history = self.sync_manager.get_sample_history(device_id, limit=1)
        if not history:
            result.rejection_reason = "no measurement"
            logger.warning("[CONTROL LOOP] no measurement for %s", device_id)
            return result

        result.observed = True
        observation = history[-1]
        model.update_measurement(observation.estimated_offset, observation.measurement_time)
        quality = self.sync_manager.get_quality(device_id)
        session.record_sync_result(
            {
                "device_id": device_id,
                "estimated_offset": observation.estimated_offset,
                "timestamp": observation.measurement_time,
                "sample_count": quality.sample_count,
                "confidence": quality.confidence_score,
            }
        )
        session.record_quality(quality)

        drift = model.drift_rate
        session.evaluate_policy(
            self.policy,
            offset=observation.estimated_offset,
            drift=drift,
            confidence=quality.confidence_score,
            uncertainty=model.uncertainty,
        )

        # --- create synchronization plan ---
        health_score = self._health_score(device_id)
        schedule = self.scheduler.get_schedule(device_id)
        last_interval = schedule.interval_ms if schedule else self.fixed_strategy.interval_ms

        if self.adaptive:
            plan = self.decision_engine.decide(
                device_id,
                offset=observation.estimated_offset,
                drift=drift,
                confidence=quality.confidence_score,
                quality=quality.to_dict(),
                health_score=health_score,
                uncertainty=model.uncertainty,
                last_interval_ms=last_interval,
                timestamp=self._ts.now(),
            )
            result.plan = plan
            session.metadata["last_sync_plan"] = plan.to_dict()
        else:
            fixed_interval = self.fixed_strategy.calculate_next_interval(
                device_id,
                last_interval_ms=last_interval,
                quality=session.quality,
                drift=drift,
                confidence=quality.confidence_score,
            )
            plan = None
            if schedule is not None:
                schedule.interval_ms = fixed_interval

        # --- update schedule ---
        if schedule is not None:
            if self.adaptive and plan is not None:
                self.scheduler.apply_adaptive_interval(
                    device_id,
                    plan.recommended_interval_ms,
                    from_time_ms=self._ts.now(),
                )
            elif not self.adaptive:
                self.scheduler.set_interval(device_id, schedule.interval_ms, adaptive=False)
            now = self._ts.now()
            schedule.last_sync_time = now
            if self.adaptive and plan is not None:
                schedule.next_sync_time = now + plan.recommended_interval_ms
            else:
                schedule.next_sync_time = now + schedule.interval_ms
            result.schedule_updated = True

        # --- execute correction if allowed (via physical bridge — safety enforced) ---
        if (
            self.physical_bridge is not None
            and session.state == SyncState.CORRECTION_READY
        ):
            if plan is not None and plan.correction_action == CorrectionAction.REJECT:
                result.rejected = True
                result.rejection_reason = f"plan action {plan.correction_action.value}"
            else:
                try:
                    txn = self.physical_bridge.execute_correction(
                        session,
                        offset=observation.estimated_offset,
                        drift=drift,
                        confidence=quality.confidence_score,
                        simulate_response=simulate_response,
                        advance_clock=advance_clock,
                    )
                    result.correction_attempted = True
                    result.transaction_state = txn.state.value
                    result.correction_applied = txn.state in {
                        TransactionState.APPLIED,
                        TransactionState.VERIFYING,
                        TransactionState.COMPLETED,
                    }
                    result.correction_verified = txn.state == TransactionState.COMPLETED
                    if txn.state == TransactionState.ROLLED_BACK:
                        result.rejected = True
                        result.rejection_reason = txn.failure_reason or "rolled back"
                    self._sync_health_to_profile(device_id)
                    result.profile_updated = True
                    if txn.state in {TransactionState.FAILED, TransactionState.ROLLED_BACK}:
                        session.mark_failed(txn.failure_reason or txn.state.value)
                except (ValueError, KeyError) as exc:
                    result.rejected = True
                    result.rejection_reason = str(exc)
                    logger.info("[CONTROL LOOP] correction rejected for %s: %s", device_id, exc)

        elif self.adaptive and plan is not None:
            result.profile_updated = True

        # poll pending wire recovery
        if self.physical_bridge is not None:
            recovery = self.physical_bridge.poll_pending_wire()
            result.recovery_events = len(recovery)

        self.scheduler.mark_synced(device_id, at_time_ms=self._ts.now())
        return result

    def _health_score(self, device_id: str) -> float:
        profile = self.decision_engine.profiles.get(device_id)
        if self.physical_bridge is not None:
            report = self.physical_bridge.health_report()
            HealthProfileBridge.apply(profile, report)
            return report.reliability_score
        return profile.reliability_score

    def _sync_health_to_profile(self, device_id: str) -> None:
        if self.physical_bridge is None:
            return
        report = self.physical_bridge.health_report()
        profile = self.decision_engine.profiles.get(device_id)
        HealthProfileBridge.apply(profile, report)
        profile.apply_health_feedback(
            reliability_score=report.reliability_score,
            rollback_count=report.rollback_count,
            successful=report.successful_corrections,
            failed=report.failed_corrections,
            average_improvement=report.average_improvement,
            timestamp=self._ts.now(),
        )
        self.decision_engine.record_correction_outcome(
            device_id,
            success=report.successful_corrections > 0 and report.failed_corrections == 0,
            timestamp=self._ts.now(),
        )

    def _session(self, device_id: str) -> SyncSession:
        if self._get_session is not None:
            return self._get_session(device_id)
        if device_id not in self._sessions:
            self._sessions[device_id] = SyncSession(device_id=device_id)
        return self._sessions[device_id]

    def _clock_model(self, device_id: str) -> ClockModel:
        if self._get_clock_model is not None:
            return self._get_clock_model(device_id)
        if device_id not in self._clock_models:
            self._clock_models[device_id] = ClockModel(clock_id=device_id)
        return self._clock_models[device_id]
