"""Correction data models."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

from .mode import CorrectionMode


@dataclass
class CorrectionEstimate:
    """Bounded correction estimate before apply."""

    device_id: str
    total_offset: float
    step_size: float
    remaining_offset: float
    mode: CorrectionMode
    allowed: bool
    reason: str = ""
    rejected: bool = False
    drift: float = 0.0
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["mode"] = self.mode.value
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CorrectionEstimate":
        return cls(
            device_id=str(data["device_id"]),
            total_offset=float(data.get("total_offset", 0.0)),
            step_size=float(data.get("step_size", 0.0)),
            remaining_offset=float(data.get("remaining_offset", 0.0)),
            mode=CorrectionMode(str(data.get("mode", CorrectionMode.DRY_RUN.value))),
            allowed=bool(data.get("allowed", False)),
            reason=str(data.get("reason", "")),
            rejected=bool(data.get("rejected", False)),
            drift=float(data.get("drift", 0.0)),
            confidence=float(data.get("confidence", 0.0)),
        )


@dataclass
class CorrectionResult:
    """Outcome of apply_correction (including dry run)."""

    device_id: str
    applied: bool
    dry_run: bool
    step_applied: float
    remaining_offset: float
    cumulative_applied: float
    timestamp: int
    mode: CorrectionMode
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["mode"] = self.mode.value
        return data


@dataclass
class VerificationResult:
    """Post-correction measurement comparison."""

    device_id: str
    offset_before: float
    offset_after: float
    improvement: float
    verified: bool
    timestamp: int
    step_applied: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RollbackResult:
    """Outcome of rolling back the last applied correction."""

    device_id: str
    rolled_back: float
    cumulative_applied: float
    success: bool
    timestamp: int
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SafetyGateResult:
    """Safety gate check outcome."""

    passed: bool
    reason: str = ""
