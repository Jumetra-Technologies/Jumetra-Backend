"""AdaptiveCorrectionPolicy — deterministic correction step sizing."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Optional

from ..policy import CorrectionAction, CorrectionDecision, CorrectionPolicy, SynchronizationSafetyConfig


@dataclass
class CorrectionStepRecommendation:
    """Recommended bounded correction step."""

    device_id: str
    step_ms: float
    offset: float
    confidence: float
    health_score: float
    previous_corrections: int
    allowed: bool
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AdaptiveCorrectionConfig:
    """Bounds for adaptive correction step calculation."""

    max_step_ms: float = 10.0
    min_step_ms: float = 0.5
    confidence_floor: float = 0.3
    health_floor: float = 0.5
    previous_correction_dampening: float = 0.85

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AdaptiveCorrectionPolicy(CorrectionPolicy):
    """Deterministic correction step from offset, confidence, history, and health.

    Extends base safety checks with adaptive step sizing — still decision-only.
    """

    def __init__(
        self,
        safety: Optional[SynchronizationSafetyConfig] = None,
        config: Optional[AdaptiveCorrectionConfig] = None,
    ) -> None:
        super().__init__(safety=safety)
        self.config = config or AdaptiveCorrectionConfig()

    def recommend_step(
        self,
        device_id: str,
        offset: float,
        *,
        confidence: float,
        previous_corrections: int = 0,
        health_score: float = 1.0,
        drift: float = 0.0,
        uncertainty: float = 0.0,
    ) -> CorrectionStepRecommendation:
        decision = self.evaluate(offset, drift, confidence, uncertainty=uncertainty)
        if not decision.allowed:
            return CorrectionStepRecommendation(
                device_id=device_id,
                step_ms=0.0,
                offset=offset,
                confidence=confidence,
                health_score=health_score,
                previous_corrections=previous_corrections,
                allowed=False,
                reason=decision.reason,
            )

        cfg = self.config
        magnitude = min(abs(offset), cfg.max_step_ms)
        step = magnitude if offset >= 0 else -magnitude

        conf_scale = max(cfg.confidence_floor, min(1.0, confidence))
        health_scale = max(cfg.health_floor, min(1.0, health_score))
        step *= conf_scale * health_scale

        if previous_corrections > 0:
            step *= cfg.previous_correction_dampening ** previous_corrections

        if abs(step) < cfg.min_step_ms:
            step = cfg.min_step_ms if step >= 0 else -cfg.min_step_ms
        if abs(step) > abs(offset):
            step = offset

        return CorrectionStepRecommendation(
            device_id=device_id,
            step_ms=float(step),
            offset=offset,
            confidence=confidence,
            health_score=health_score,
            previous_corrections=previous_corrections,
            allowed=True,
            reason="adaptive bounded step",
        )

    def evaluate_with_step(
        self,
        device_id: str,
        offset: float,
        drift: float,
        confidence: float,
        *,
        previous_corrections: int = 0,
        health_score: float = 1.0,
        uncertainty: float = 0.0,
    ) -> tuple[CorrectionDecision, CorrectionStepRecommendation]:
        decision = self.evaluate(offset, drift, confidence, uncertainty=uncertainty)
        step_rec = self.recommend_step(
            device_id,
            offset,
            confidence=confidence,
            previous_corrections=previous_corrections,
            health_score=health_score,
            drift=drift,
            uncertainty=uncertainty,
        )
        if not decision.allowed:
            step_rec.allowed = False
            step_rec.reason = decision.reason
            step_rec.step_ms = 0.0
        return decision, step_rec
