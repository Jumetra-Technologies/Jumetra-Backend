"""Clock adjustment package — bounded safe correction v1."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional

from .mode import CorrectionMode
from .models import (
    CorrectionEstimate,
    CorrectionResult,
    RollbackResult,
    SafetyGateResult,
    VerificationResult,
)
from .safe_adjuster import SafeClockAdjuster
from .safety_gate import CorrectionSafetyGate


class ClockAdjuster(ABC):
    """Abstract clock adjuster interface."""

    @abstractmethod
    def estimate_correction(self, *args: Any, **kwargs: Any) -> CorrectionEstimate:
        """Estimate a bounded correction step."""

    @abstractmethod
    def apply_correction(self, *args: Any, **kwargs: Any) -> CorrectionResult:
        """Apply or simulate a correction."""

    @abstractmethod
    def rollback(self, *args: Any, **kwargs: Any) -> RollbackResult:
        """Reverse the last applied correction."""

    @abstractmethod
    def verify(self, *args: Any, **kwargs: Any) -> VerificationResult:
        """Verify correction via re-measurement."""

    def reset(self, device_id: Optional[str] = None) -> None:
        """Clear adjuster state."""


class NullClockAdjuster(ClockAdjuster):
    """No-op adjuster for estimation-only paths (Sprint 11 compat)."""

    def __init__(self) -> None:
        self.pending: list[dict[str, Any]] = []

    def estimate_correction(self, device_id: str, offset: float, session: Any, **kwargs: Any) -> CorrectionEstimate:
        return CorrectionEstimate(
            device_id=str(device_id),
            total_offset=float(offset),
            step_size=0.0,
            remaining_offset=float(offset),
            mode=CorrectionMode.DISABLED,
            allowed=False,
            rejected=True,
            reason="NullClockAdjuster",
        )

    def apply_correction(self, device_id: str, estimate: CorrectionEstimate, **kwargs: Any) -> CorrectionResult:
        self.pending.append(
            {
                "device_id": str(device_id),
                "offset_ms": estimate.total_offset,
                "applied": False,
            }
        )
        return CorrectionResult(
            device_id=str(device_id),
            applied=False,
            dry_run=True,
            step_applied=0.0,
            remaining_offset=estimate.total_offset,
            cumulative_applied=0.0,
            timestamp=0,
            mode=CorrectionMode.DISABLED,
            reason="NullClockAdjuster",
        )

    def rollback(self, device_id: str, **kwargs: Any) -> RollbackResult:
        return RollbackResult(
            device_id=str(device_id),
            rolled_back=0.0,
            cumulative_applied=0.0,
            success=False,
            timestamp=0,
            reason="NullClockAdjuster",
        )

    def verify(self, device_id: str, offset_before: float, measure_fn: Any, **kwargs: Any) -> VerificationResult:
        return VerificationResult(
            device_id=str(device_id),
            offset_before=float(offset_before),
            offset_after=float(offset_before),
            improvement=0.0,
            verified=False,
            timestamp=0,
        )

    def reset(self, device_id: Optional[str] = None) -> None:
        if device_id is None:
            self.pending.clear()


__all__ = [
    "ClockAdjuster",
    "CorrectionEstimate",
    "CorrectionMode",
    "CorrectionResult",
    "CorrectionSafetyGate",
    "NullClockAdjuster",
    "RollbackResult",
    "SafeClockAdjuster",
    "SafetyGateResult",
    "VerificationResult",
]
