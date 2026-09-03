"""SafeClockAdjuster — bounded, reversible, safety-checked correction."""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from ...time.clock_model import ClockModel
from ...time.timestamp_service import TimestampService, get_timestamp_service
from ..policy import CorrectionPolicy, SynchronizationSafetyConfig
from ..storage import SynchronizationStorage
from ..sync_session import SyncSession
from .mode import CorrectionMode
from .models import (
    CorrectionEstimate,
    CorrectionResult,
    RollbackResult,
    VerificationResult,
)
from .safety_gate import CorrectionSafetyGate

logger = logging.getLogger("hhip.synchronization.adjuster")

MeasureFn = Callable[[], float]


class SafeClockAdjuster:
    """Bounded, reversible clock correction (v1).

    Default mode is ``DRY_RUN`` — estimates and audits only.
    """

    def __init__(
        self,
        *,
        mode: CorrectionMode = CorrectionMode.DRY_RUN,
        max_step_ms: float = 10.0,
        safety: Optional[SynchronizationSafetyConfig] = None,
        storage: Optional[SynchronizationStorage] = None,
        timestamp_service: Optional[TimestampService] = None,
    ) -> None:
        if max_step_ms <= 0:
            raise ValueError("max_step_ms must be positive")
        self.mode = mode
        self.max_step_ms = float(max_step_ms)
        self.safety = safety or SynchronizationSafetyConfig()
        self.storage = storage
        self._ts = timestamp_service or get_timestamp_service()
        self._gate = CorrectionSafetyGate(safety=self.safety)
        self._cumulative: dict[str, float] = {}
        self._rollback_stack: dict[str, list[float]] = {}
        self._last_estimate: dict[str, CorrectionEstimate] = {}
        self._last_verification: dict[str, VerificationResult] = {}

    @property
    def cumulative_applied(self) -> dict[str, float]:
        return dict(self._cumulative)

    def estimate_correction(
        self,
        device_id: str,
        offset: float,
        session: SyncSession,
        *,
        drift: float = 0.0,
        confidence: float = 0.0,
        uncertainty: float = 0.0,
        clock_model: Optional[ClockModel] = None,
    ) -> CorrectionEstimate:
        """Compute a bounded correction step after safety checks."""
        device_id = str(device_id)
        offset = float(offset)

        if self.mode == CorrectionMode.DISABLED:
            estimate = CorrectionEstimate(
                device_id=device_id,
                total_offset=offset,
                step_size=0.0,
                remaining_offset=abs(offset),
                mode=self.mode,
                allowed=False,
                rejected=True,
                reason="correction mode DISABLED",
                drift=drift,
                confidence=confidence,
            )
            self._audit("correction_attempt", device_id, estimate=estimate, rejected=True)
            return estimate

        gate = self._gate.check(
            session, offset, drift, confidence, uncertainty=uncertainty
        )
        if not gate.passed:
            estimate = CorrectionEstimate(
                device_id=device_id,
                total_offset=offset,
                step_size=0.0,
                remaining_offset=abs(offset),
                mode=self.mode,
                allowed=False,
                rejected=True,
                reason=gate.reason,
                drift=drift,
                confidence=confidence,
            )
            self._audit("correction_attempt", device_id, estimate=estimate, rejected=True)
            return estimate

        # Bounded step toward zero offset.
        magnitude = min(abs(offset), self.max_step_ms)
        remaining = abs(offset) - magnitude
        step = magnitude if offset >= 0 else -magnitude

        estimate = CorrectionEstimate(
            device_id=device_id,
            total_offset=offset,
            step_size=step,
            remaining_offset=remaining if offset >= 0 else -remaining,
            mode=self.mode,
            allowed=True,
            reason="bounded step computed",
            drift=drift,
            confidence=confidence,
        )
        self._last_estimate[device_id] = estimate
        self._audit("correction_attempt", device_id, estimate=estimate, rejected=False)
        return estimate

    def apply_correction(
        self,
        device_id: str,
        estimate: CorrectionEstimate,
        *,
        clock_model: Optional[ClockModel] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> CorrectionResult:
        """Apply or simulate a bounded correction."""
        device_id = str(device_id)
        now = self._ts.now()

        if estimate.rejected or not estimate.allowed:
            result = CorrectionResult(
                device_id=device_id,
                applied=False,
                dry_run=False,
                step_applied=0.0,
                remaining_offset=estimate.total_offset,
                cumulative_applied=self._cumulative.get(device_id, 0.0),
                timestamp=now,
                mode=self.mode,
                reason=estimate.reason or "estimate rejected",
            )
            self._audit("correction_applied", device_id, result=result, rejected=True)
            return result

        if self.mode == CorrectionMode.DRY_RUN:
            result = CorrectionResult(
                device_id=device_id,
                applied=False,
                dry_run=True,
                step_applied=estimate.step_size,
                remaining_offset=estimate.remaining_offset,
                cumulative_applied=self._cumulative.get(device_id, 0.0),
                timestamp=now,
                mode=self.mode,
                reason="DRY_RUN — no clock modification",
            )
            self._audit("correction_applied", device_id, result=result, dry_run=True)
            return result

        if self.mode == CorrectionMode.DISABLED:
            result = CorrectionResult(
                device_id=device_id,
                applied=False,
                dry_run=False,
                step_applied=0.0,
                remaining_offset=estimate.total_offset,
                cumulative_applied=self._cumulative.get(device_id, 0.0),
                timestamp=now,
                mode=self.mode,
                reason="DISABLED",
            )
            self._audit("correction_applied", device_id, result=result, rejected=True)
            return result

        step = float(estimate.step_size)
        cumulative = self._cumulative.get(device_id, 0.0) + abs(step)
        self._cumulative[device_id] = cumulative
        self._rollback_stack.setdefault(device_id, []).append(step)

        if clock_model is not None:
            clock_model.apply_bounded_correction(step)

        result = CorrectionResult(
            device_id=device_id,
            applied=True,
            dry_run=False,
            step_applied=step,
            remaining_offset=estimate.remaining_offset,
            cumulative_applied=cumulative,
            timestamp=now,
            mode=self.mode,
            reason="correction applied",
        )
        self._audit(
            "correction_applied",
            device_id,
            result=result,
            metadata=metadata or {},
        )
        logger.info(
            "[ADJUSTER] applied %s step=%.2f remaining=%.2f cumulative=%.2f",
            device_id,
            step,
            estimate.remaining_offset,
            cumulative,
        )
        return result

    def rollback(
        self,
        device_id: str,
        *,
        clock_model: Optional[ClockModel] = None,
    ) -> RollbackResult:
        """Reverse the last applied correction step."""
        device_id = str(device_id)
        now = self._ts.now()
        stack = self._rollback_stack.get(device_id, [])

        if not stack:
            result = RollbackResult(
                device_id=device_id,
                rolled_back=0.0,
                cumulative_applied=self._cumulative.get(device_id, 0.0),
                success=False,
                timestamp=now,
                reason="nothing to rollback",
            )
            self._audit("rollback", device_id, result=result, success=False)
            return result

        step = stack.pop()
        cumulative = max(0.0, self._cumulative.get(device_id, 0.0) - abs(step))
        self._cumulative[device_id] = cumulative

        if clock_model is not None:
            clock_model.rollback_correction(step)

        result = RollbackResult(
            device_id=device_id,
            rolled_back=step,
            cumulative_applied=cumulative,
            success=True,
            timestamp=now,
            reason="last step rolled back",
        )
        self._audit("rollback", device_id, result=result, success=True)
        logger.info("[ADJUSTER] rollback %s step=%.2f", device_id, step)
        return result

    def verify(
        self,
        device_id: str,
        offset_before: float,
        measure_fn: MeasureFn,
        *,
        step_applied: float = 0.0,
        min_improvement: float = 0.0,
    ) -> VerificationResult:
        """Re-measure and compare offset before/after correction."""
        device_id = str(device_id)
        offset_after = float(measure_fn())
        improvement = abs(float(offset_before)) - abs(offset_after)
        verified = improvement >= min_improvement

        result = VerificationResult(
            device_id=device_id,
            offset_before=float(offset_before),
            offset_after=offset_after,
            improvement=improvement,
            verified=verified,
            timestamp=self._ts.now(),
            step_applied=step_applied,
        )
        self._last_verification[device_id] = result
        self._audit("correction_verified", device_id, verification=result)
        return result

    def reset(self, device_id: Optional[str] = None) -> None:
        """Clear adjuster state for one device or all."""
        if device_id is None:
            self._cumulative.clear()
            self._rollback_stack.clear()
            self._last_estimate.clear()
            self._last_verification.clear()
        else:
            did = str(device_id)
            self._cumulative.pop(did, None)
            self._rollback_stack.pop(did, None)
            self._last_estimate.pop(did, None)
            self._last_verification.pop(did, None)

    def _audit(self, event: str, device_id: str, **extra: Any) -> None:
        if self.storage is None:
            return
        record: dict[str, Any] = {
            "timestamp": self._ts.now(),
            "device_id": device_id,
        }
        for key, value in extra.items():
            if hasattr(value, "to_dict"):
                record[key] = value.to_dict()
            elif value is not None:
                record[key] = value
        self.storage.append_correction_event(event, **record)
