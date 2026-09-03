"""SynchronizationCoordinator — integrates scheduler, sessions, manager, storage."""

from __future__ import annotations

import logging
from typing import Any, Optional

from ..time.clock_model import ClockModel
from ..time.timestamp_service import TimestampService, get_timestamp_service
from .intelligence import DeviceSyncProfileStore, SynchronizationDecisionEngine
from .control_loop import SynchronizationControlLoop
from .manager import SynchronizationManager
from .policy import CorrectionPolicy
from .scheduler import ScheduledDevice, SynchronizationScheduler
from .state import SyncState
from .storage import SynchronizationStorage
from .strategy import FixedIntervalStrategy, SyncIntervalStrategy
from .sync_session import SyncSession

logger = logging.getLogger("hhip.synchronization.coordinator")


class SynchronizationCoordinator:
    """Orchestrate sync control: schedule, measure, persist, audit — no correction."""

    def __init__(
        self,
        sync_manager: SynchronizationManager,
        storage: SynchronizationStorage,
        *,
        policy: Optional[CorrectionPolicy] = None,
        strategy: Optional[SyncIntervalStrategy] = None,
        default_interval_ms: int = 5_000,
        decision_engine: Optional[SynchronizationDecisionEngine] = None,
        control_loop: Optional[SynchronizationControlLoop] = None,
        physical_bridge: Optional[Any] = None,
        autonomous: bool = False,
        timestamp_service: Optional[TimestampService] = None,
    ) -> None:
        self.sync_manager = sync_manager
        storage = storage
        self.storage = storage
        self.policy = policy or CorrectionPolicy()
        self.strategy = strategy or FixedIntervalStrategy(default_interval_ms)
        self.decision_engine = decision_engine or SynchronizationDecisionEngine()
        self._default_interval_ms = default_interval_ms
        self._ts = timestamp_service or get_timestamp_service()
        self.autonomous = autonomous
        self.control_loop = control_loop
        self.sessions: dict[str, SyncSession] = {}
        self.clock_models: dict[str, ClockModel] = {}
        self._calibrations: dict[str, dict] = {}
        self.scheduler = SynchronizationScheduler(
            default_interval_ms=default_interval_ms,
            timestamp_service=self._ts,
            on_trigger=self._on_scheduled_sync,
        )
        self._started = False

        if self.control_loop is None and (autonomous or physical_bridge is not None):
            self.control_loop = SynchronizationControlLoop(
                sync_manager,
                self.scheduler,
                self.decision_engine,
                physical_bridge=physical_bridge,
                adaptive=autonomous,
                fixed_interval_ms=default_interval_ms,
                timestamp_service=self._ts,
            )
            self.control_loop.bind_providers(
                get_session=self.get_or_create_session,
                get_clock_model=self.get_or_create_clock_model,
            )
            self.scheduler._on_trigger = self.control_loop.handle_scheduled_trigger

    # --- Lifecycle -------------------------------------------------------

    def startup(self) -> None:
        """Load persisted state and restore sessions, models, schedules."""
        if self._started:
            return

        self.sessions = self.storage.load_sessions()
        self.clock_models = self.storage.load_clock_models()
        self._calibrations = self.storage.load_calibrations()

        for device_id, schedule in self.storage.load_schedules().items():
            self.scheduler.schedule(
                device_id,
                interval_ms=schedule.interval_ms,
                adaptive=schedule.adaptive,
                start_at=schedule.next_sync_time or self._ts.now(),
            )
            entry = self.scheduler.get_schedule(device_id)
            if entry is not None:
                entry.last_sync_time = schedule.last_sync_time
                entry.next_sync_time = schedule.next_sync_time
                entry.enabled = schedule.enabled

        for device_id, cal in self._calibrations.items():
            session = self.get_or_create_session(device_id)
            session.calibration = dict(cal)

        profiles = self.storage.load_sync_profiles()
        if profiles:
            self.decision_engine.profiles.load(profiles)

        self._started = True
        logger.info(
            "[SYNC COORDINATOR] startup sessions=%d models=%d schedules=%d",
            len(self.sessions),
            len(self.clock_models),
            len(self.scheduler.all_schedules()),
        )

    def shutdown(self) -> None:
        """Persist all synchronization state."""
        self.storage.save_sync_profiles(self.decision_engine.profiles.to_dict())
        self.storage.save_all(
            sessions=self.sessions,
            clock_models=self.clock_models,
            schedules=self.scheduler.all_schedules(),
            calibrations=self._calibrations,
        )
        self._started = False
        logger.info("[SYNC COORDINATOR] shutdown persisted state")

    def poll(self) -> list[str]:
        """Poll scheduler for due devices (runtime integration hook)."""
        if self.control_loop is not None and self.autonomous:
            results = self.control_loop.poll()
            return [r.device_id for r in results if r.observed]
        return self.scheduler.poll(at_time_ms=self._ts.now())

    # --- Session API -----------------------------------------------------

    def get_or_create_session(self, device_id: str) -> SyncSession:
        if device_id not in self.sessions:
            self.sessions[device_id] = SyncSession(device_id=device_id)
        return self.sessions[device_id]

    def get_or_create_clock_model(self, device_id: str) -> ClockModel:
        if device_id not in self.clock_models:
            self.clock_models[device_id] = ClockModel(clock_id=device_id)
        return self.clock_models[device_id]

    def schedule_device(
        self,
        device_id: str,
        *,
        interval_ms: Optional[int] = None,
        adaptive: bool = False,
    ) -> ScheduledDevice:
        """Schedule periodic sync for a device."""
        interval = interval_ms or self._default_interval_ms
        entry = self.scheduler.schedule(
            device_id, interval_ms=interval, adaptive=adaptive, start_at=self._ts.now()
        )
        session = self.get_or_create_session(device_id)
        if session.state == SyncState.UNKNOWN:
            session.begin()
        return entry

    # --- Internals -------------------------------------------------------

    def _on_scheduled_sync(self, device_id: str) -> None:
        """Scheduler callback: request measurement and update persisted state."""
        session = self.get_or_create_session(device_id)
        if session.state == SyncState.UNKNOWN:
            session.begin()
        elif session.state in (SyncState.MONITORING, SyncState.CALIBRATED):
            if session._state_machine.can_transition(SyncState.MEASURING):
                session.transition_to(SyncState.MEASURING)

        self.sync_manager.request_sync(device_id)
        history = self.sync_manager.get_sample_history(device_id, limit=1)
        if not history:
            logger.warning(
                "[SYNC COORDINATOR] no measurement for %s after trigger", device_id
            )
            return

        observation = history[-1]
        model = self.get_or_create_clock_model(device_id)
        model.update_measurement(
            observation.estimated_offset,
            observation.measurement_time,
        )

        quality = self.sync_manager.get_quality(device_id)
        session.record_sync_result(
            {
                "device_id": device_id,
                "estimated_offset": observation.estimated_offset,
                "timestamp": observation.measurement_time,
                "sample_count": quality.sample_count,
                "confidence": quality.confidence_score,
                "algorithm_used": "cristian",
            }
        )
        session.record_quality(quality)

        drift = model.drift_rate
        decision = session.evaluate_policy(
            self.policy,
            offset=observation.estimated_offset,
            drift=drift,
            confidence=quality.confidence_score,
            uncertainty=model.uncertainty,
        )

        self.storage.append_audit(
            timestamp=self._ts.now(),
            device_id=device_id,
            decision=decision.action.value,
            offset=observation.estimated_offset,
            drift=drift,
            confidence=quality.confidence_score,
        )

        schedule = self.scheduler.get_schedule(device_id)
        if schedule is not None:
            health_score = 1.0
            if schedule.adaptive:
                plan = self.decision_engine.decide(
                    device_id,
                    offset=observation.estimated_offset,
                    drift=drift,
                    confidence=quality.confidence_score,
                    quality=quality.to_dict(),
                    health_score=health_score,
                    uncertainty=model.uncertainty,
                    last_interval_ms=schedule.interval_ms,
                    timestamp=self._ts.now(),
                )
                next_interval = plan.recommended_interval_ms
                session.metadata["last_sync_plan"] = plan.to_dict()
                self.scheduler.apply_adaptive_interval(
                    device_id, next_interval, from_time_ms=self._ts.now()
                )
            else:
                next_interval = self.strategy.calculate_next_interval(
                    device_id,
                    last_interval_ms=schedule.interval_ms,
                    quality=session.quality,
                    drift=drift,
                    confidence=quality.confidence_score,
                )
                schedule.interval_ms = next_interval
            now = self._ts.now()
            schedule.last_sync_time = now
            if not schedule.adaptive:
                schedule.next_sync_time = now + schedule.interval_ms

        self.storage.save_session(session)
        self.storage.save_clock_model(model)
        if schedule is not None:
            self.storage.save_schedule(schedule)

        logger.info(
            "[SYNC COORDINATOR] measured %s offset=%.2f decision=%s",
            device_id,
            observation.estimated_offset,
            decision.action.value,
        )

    def attempt_correction(
        self,
        device_id: str,
        adjuster: Any,
        *,
        offset: Optional[float] = None,
        drift: Optional[float] = None,
        confidence: Optional[float] = None,
    ) -> Any:
        """Run bounded correction workflow when session is CORRECTION_READY."""
        session = self.get_or_create_session(device_id)
        model = self.get_or_create_clock_model(device_id)
        off = float(offset if offset is not None else model.current_offset)
        dr = float(drift if drift is not None else model.drift_rate)
        conf = float(
            confidence
            if confidence is not None
            else (session.quality or {}).get("confidence_score", 0.0)
        )

        estimate = adjuster.estimate_correction(
            device_id, off, session, drift=dr, confidence=conf, clock_model=model
        )
        result = adjuster.apply_correction(device_id, estimate, clock_model=model)

        if result.applied and not result.dry_run:
            verify = adjuster.verify(
                device_id,
                off,
                lambda: model.effective_offset,
                step_applied=result.step_applied,
            )
            session.metadata["last_verification"] = verify.to_dict()
            session.enter_monitoring()

        self.storage.save_session(session)
        self.storage.save_clock_model(model)
        return result
