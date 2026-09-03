"""SynchronizationDecisionEngine — combine signals into a SynchronizationPlan."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Optional

from ..policy import CorrectionAction
from .correction_policy import AdaptiveCorrectionPolicy
from .interval_strategy import AdaptiveIntervalStrategy
from .profile import DeviceSyncProfile, DeviceSyncProfileStore


@dataclass
class SynchronizationPlan:
    """Combined adaptive synchronization decision for one device."""

    device_id: str
    recommended_interval_ms: int
    recommended_correction_step: float
    correction_action: CorrectionAction
    sync_now: bool
    stability_score: float
    success_rate: float
    reason: str
    profile: Optional[DeviceSyncProfile] = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["correction_action"] = self.correction_action.value
        if self.profile is not None:
            data["profile"] = self.profile.to_dict()
        return data


class SynchronizationDecisionEngine:
    """Combine measurement quality, device profile, and policy outputs."""

    def __init__(
        self,
        *,
        interval_strategy: Optional[AdaptiveIntervalStrategy] = None,
        correction_policy: Optional[AdaptiveCorrectionPolicy] = None,
        profile_store: Optional[DeviceSyncProfileStore] = None,
    ) -> None:
        self.interval_strategy = interval_strategy or AdaptiveIntervalStrategy()
        self.correction_policy = correction_policy or AdaptiveCorrectionPolicy()
        self.profiles = profile_store or DeviceSyncProfileStore()

    def decide(
        self,
        device_id: str,
        *,
        offset: float,
        drift: float,
        confidence: float,
        quality: Optional[Mapping[str, Any]] = None,
        health_score: float = 1.0,
        uncertainty: float = 0.0,
        last_interval_ms: int = 5_000,
        timestamp: int = 0,
    ) -> SynchronizationPlan:
        q = quality or {}
        profile = self.profiles.get(device_id)
        rtt_stability = AdaptiveIntervalStrategy.rtt_stability_from_quality(q)

        profile.record_sync(
            drift=drift,
            confidence=confidence,
            rtt_stability=rtt_stability,
            timestamp=timestamp,
        )

        interval_rec = self.interval_strategy.recommend(
            device_id,
            drift_rate=drift,
            confidence=confidence,
            rtt_stability=rtt_stability,
            device_health=health_score,
            failure_rate=profile.failure_rate,
            last_interval_ms=last_interval_ms,
        )
        profile.recommended_interval = interval_rec.interval_ms

        decision, step_rec = self.correction_policy.evaluate_with_step(
            device_id,
            offset,
            drift,
            confidence,
            previous_corrections=profile.correction_count,
            health_score=health_score,
            uncertainty=uncertainty,
        )

        sync_now = (
            abs(offset) > 50.0
            or confidence < 0.6
            or profile.stability_score < 0.5
            or interval_rec.interval_ms <= last_interval_ms * 0.8
        )

        reason = (
            f"interval={interval_rec.interval_ms}ms step={step_rec.step_ms:.2f} "
            f"action={decision.action.value}; {interval_rec.reason}"
        )

        return SynchronizationPlan(
            device_id=device_id,
            recommended_interval_ms=interval_rec.interval_ms,
            recommended_correction_step=step_rec.step_ms,
            correction_action=decision.action,
            sync_now=sync_now,
            stability_score=profile.stability_score,
            success_rate=profile.success_rate,
            reason=reason,
            profile=profile,
        )

    def record_correction_outcome(
        self, device_id: str, *, success: bool, timestamp: int
    ) -> DeviceSyncProfile:
        profile = self.profiles.get(device_id)
        profile.record_correction(success=success, timestamp=timestamp)
        return profile
