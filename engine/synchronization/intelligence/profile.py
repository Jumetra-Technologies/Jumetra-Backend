"""DeviceSyncProfile — per-device adaptive synchronization profile."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Optional


@dataclass
class DeviceSyncProfile:
    """Aggregated device synchronization characteristics."""

    device_id: str
    stability_score: float = 1.0
    recommended_interval: int = 5_000
    success_rate: float = 1.0
    average_drift: float = 0.0
    sync_event_count: int = 0
    correction_count: int = 0
    correction_success_count: int = 0
    rollback_count: int = 0
    reliability_score: float = 1.0
    last_updated: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "DeviceSyncProfile":
        meta = data.get("metadata") or {}
        return cls(
            device_id=str(data["device_id"]),
            stability_score=float(data.get("stability_score", 1.0)),
            recommended_interval=int(data.get("recommended_interval", 5_000)),
            success_rate=float(data.get("success_rate", 1.0)),
            average_drift=float(data.get("average_drift", 0.0)),
            sync_event_count=int(data.get("sync_event_count", 0)),
            correction_count=int(data.get("correction_count", 0)),
            correction_success_count=int(data.get("correction_success_count", 0)),
            rollback_count=int(data.get("rollback_count", 0)),
            reliability_score=float(data.get("reliability_score", 1.0)),
            last_updated=int(data.get("last_updated", 0)),
            metadata=dict(meta) if isinstance(meta, Mapping) else {},
        )

    @property
    def failure_rate(self) -> float:
        if self.correction_count == 0:
            return 0.0
        failures = self.correction_count - self.correction_success_count
        return max(0.0, failures / self.correction_count)

    def record_sync(self, *, drift: float, confidence: float, rtt_stability: float, timestamp: int) -> None:
        """Update profile after a sync measurement."""
        self.sync_event_count += 1
        alpha = 0.2
        self.average_drift = (1 - alpha) * self.average_drift + alpha * drift
        stability = min(1.0, confidence * rtt_stability)
        self.stability_score = (1 - alpha) * self.stability_score + alpha * stability
        self.last_updated = timestamp

    def record_correction(self, *, success: bool, timestamp: int) -> None:
        self.correction_count += 1
        if success:
            self.correction_success_count += 1
        total = self.correction_count
        self.success_rate = self.correction_success_count / total if total else 1.0
        self.last_updated = timestamp

    def apply_health_feedback(
        self,
        *,
        reliability_score: float,
        rollback_count: int,
        successful: int,
        failed: int,
        average_improvement: float = 0.0,
        timestamp: int = 0,
    ) -> None:
        """Update profile from CorrectionHealthMonitor after correction."""
        self.reliability_score = float(reliability_score)
        self.rollback_count = int(rollback_count)
        total = successful + failed
        if total > 0:
            self.success_rate = successful / total
            self.correction_count = max(self.correction_count, total)
            self.correction_success_count = successful
        self.stability_score = min(self.stability_score, self.reliability_score)
        if timestamp:
            self.last_updated = timestamp
        self.metadata["average_improvement"] = average_improvement
        self.metadata["failed_corrections"] = failed


class DeviceSyncProfileStore:
    """In-memory profile registry with optional persistence hook."""

    def __init__(self) -> None:
        self._profiles: dict[str, DeviceSyncProfile] = {}

    def get(self, device_id: str) -> DeviceSyncProfile:
        if device_id not in self._profiles:
            self._profiles[device_id] = DeviceSyncProfile(device_id=device_id)
        return self._profiles[device_id]

    def all_profiles(self) -> dict[str, DeviceSyncProfile]:
        return dict(self._profiles)

    def load(self, profiles: Mapping[str, Mapping[str, Any]]) -> None:
        self._profiles = {
            str(did): DeviceSyncProfile.from_dict(raw) for did, raw in profiles.items()
        }

    def to_dict(self) -> dict[str, dict[str, Any]]:
        return {did: p.to_dict() for did, p in self._profiles.items()}
