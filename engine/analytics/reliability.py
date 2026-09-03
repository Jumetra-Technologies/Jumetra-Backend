"""DeviceReliabilityScore — deterministic device ranking."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Optional


@dataclass
class DeviceReliabilityScore:
    """Reliability ranking for one device."""

    device_id: str
    score: float
    success_rate: float
    failure_rate: float
    rollback_count: int
    drift_stability: float
    components: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def compute(
        cls,
        device_id: str,
        *,
        success_rate: float,
        failure_count: int = 0,
        correction_attempts: int = 0,
        rollback_count: int = 0,
        drift_stability: float = 1.0,
        offset_stability: float = 1.0,
    ) -> "DeviceReliabilityScore":
        """Compute a deterministic reliability score in [0, 1]."""
        attempts = max(correction_attempts, failure_count, 1)
        failure_rate = failure_count / attempts if attempts else 0.0
        rollback_penalty = min(1.0, rollback_count / max(attempts, 1))
        drift_factor = max(0.0, min(1.0, drift_stability))
        offset_factor = max(0.0, min(1.0, offset_stability))

        components = {
            "success_rate": float(success_rate),
            "failure_penalty": 1.0 - failure_rate,
            "rollback_penalty": 1.0 - rollback_penalty,
            "drift_stability": drift_factor,
            "offset_stability": offset_factor,
        }
        score = (
            components["success_rate"] * 0.35
            + components["failure_penalty"] * 0.25
            + components["rollback_penalty"] * 0.15
            + components["drift_stability"] * 0.15
            + components["offset_stability"] * 0.10
        )
        score = max(0.0, min(1.0, score))

        return cls(
            device_id=device_id,
            score=score,
            success_rate=float(success_rate),
            failure_rate=failure_rate,
            rollback_count=int(rollback_count),
            drift_stability=drift_factor,
            components=components,
        )

    @classmethod
    def from_device_metrics(cls, metrics: Mapping[str, Any]) -> "DeviceReliabilityScore":
        sync = metrics.get("synchronization") or {}
        corr = metrics.get("correction") or {}
        return cls.compute(
            str(metrics.get("device_id", "")),
            success_rate=float(corr.get("correction_success_rate", metrics.get("success_rate", 1.0))),
            failure_count=int(corr.get("failure_count", 0)),
            correction_attempts=int(corr.get("correction_attempts", 0)),
            rollback_count=int(corr.get("rollback_count", 0)),
            drift_stability=1.0 / (1.0 + abs(float(sync.get("drift_rate", 0.0))) * 1000),
            offset_stability=float(sync.get("offset_stability", 1.0)),
        )

    @classmethod
    def rank_devices(cls, scores: list["DeviceReliabilityScore"]) -> list["DeviceReliabilityScore"]:
        return sorted(scores, key=lambda s: s.score, reverse=True)
