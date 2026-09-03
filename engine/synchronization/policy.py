"""Synchronization safety configuration and correction policy (decision only)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Mapping, Optional


class CorrectionAction(str, Enum):
    """Policy outcome — does not modify any clock."""

    DEFER = "defer"
    REJECT = "reject"
    MONITOR = "monitor"
    READY = "ready"


@dataclass
class SynchronizationSafetyConfig:
    """Safety boundaries used for correction *decisions* only."""

    maximum_offset: float = 10_000.0  # ms
    maximum_drift: float = 0.01  # offset change per ms host time
    minimum_confidence: float = 0.5
    maximum_uncertainty: float = 1_000.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SynchronizationSafetyConfig":
        return cls(
            maximum_offset=float(data.get("maximum_offset", 10_000.0)),
            maximum_drift=float(data.get("maximum_drift", 0.01)),
            minimum_confidence=float(data.get("minimum_confidence", 0.5)),
            maximum_uncertainty=float(data.get("maximum_uncertainty", 1_000.0)),
        )


@dataclass
class CorrectionDecision:
    """Result of policy evaluation — records intent, never applies correction."""

    action: CorrectionAction
    allowed: bool
    reason: str
    offset: float
    drift: float
    confidence: float
    uncertainty: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["action"] = self.action.value
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CorrectionDecision":
        return cls(
            action=CorrectionAction(str(data["action"])),
            allowed=bool(data.get("allowed", False)),
            reason=str(data.get("reason", "")),
            offset=float(data.get("offset", 0.0)),
            drift=float(data.get("drift", 0.0)),
            confidence=float(data.get("confidence", 0.0)),
            uncertainty=float(data.get("uncertainty", 0.0)),
        )


class CorrectionPolicy:
    """Evaluate whether a device is eligible for future correction.

    Sprint 13: decision making only — no clock modification.
    """

    def __init__(self, safety: Optional[SynchronizationSafetyConfig] = None) -> None:
        self.safety = safety or SynchronizationSafetyConfig()

    def evaluate(
        self,
        offset: float,
        drift: float,
        confidence: float,
        *,
        uncertainty: float = 0.0,
    ) -> CorrectionDecision:
        """Return a CorrectionDecision based on safety boundaries."""
        offset = float(offset)
        drift = float(drift)
        confidence = float(confidence)
        uncertainty = float(uncertainty)
        safety = self.safety

        if abs(offset) > safety.maximum_offset:
            return CorrectionDecision(
                action=CorrectionAction.REJECT,
                allowed=False,
                reason=f"offset {offset:.2f} exceeds maximum {safety.maximum_offset}",
                offset=offset,
                drift=drift,
                confidence=confidence,
                uncertainty=uncertainty,
            )

        if abs(drift) > safety.maximum_drift:
            return CorrectionDecision(
                action=CorrectionAction.REJECT,
                allowed=False,
                reason=f"drift {drift:.6f} exceeds maximum {safety.maximum_drift}",
                offset=offset,
                drift=drift,
                confidence=confidence,
                uncertainty=uncertainty,
            )

        if uncertainty > safety.maximum_uncertainty:
            return CorrectionDecision(
                action=CorrectionAction.DEFER,
                allowed=False,
                reason=(
                    f"uncertainty {uncertainty:.2f} exceeds maximum "
                    f"{safety.maximum_uncertainty}"
                ),
                offset=offset,
                drift=drift,
                confidence=confidence,
                uncertainty=uncertainty,
            )

        if confidence < safety.minimum_confidence:
            return CorrectionDecision(
                action=CorrectionAction.DEFER,
                allowed=False,
                reason=(
                    f"confidence {confidence:.3f} below minimum "
                    f"{safety.minimum_confidence}"
                ),
                offset=offset,
                drift=drift,
                confidence=confidence,
                uncertainty=uncertainty,
            )

        return CorrectionDecision(
            action=CorrectionAction.READY,
            allowed=True,
            reason="within safety bounds; correction may proceed in a future sprint",
            offset=offset,
            drift=drift,
            confidence=confidence,
            uncertainty=uncertainty,
        )
