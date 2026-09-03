"""Unified analytics data models."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Optional


@dataclass
class SynchronizationMetrics:
    """Synchronization measurement aggregates for one device."""

    device_id: str
    sync_event_count: int = 0
    average_sync_error: float = 0.0
    offset_stability: float = 0.0
    drift_rate: float = 0.0
    average_rtt: float = 0.0
    jitter: float = 0.0
    latency_min_ms: float = 0.0
    latency_max_ms: float = 0.0
    latency_p50_ms: float = 0.0
    latency_p95_ms: float = 0.0
    communication_cost: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SynchronizationMetrics":
        return cls(
            device_id=str(data["device_id"]),
            sync_event_count=int(data.get("sync_event_count", 0)),
            average_sync_error=float(data.get("average_sync_error", 0.0)),
            offset_stability=float(data.get("offset_stability", 0.0)),
            drift_rate=float(data.get("drift_rate", 0.0)),
            average_rtt=float(data.get("average_rtt", 0.0)),
            jitter=float(data.get("jitter", 0.0)),
            latency_min_ms=float(data.get("latency_min_ms", 0.0)),
            latency_max_ms=float(data.get("latency_max_ms", 0.0)),
            latency_p50_ms=float(data.get("latency_p50_ms", 0.0)),
            latency_p95_ms=float(data.get("latency_p95_ms", 0.0)),
            communication_cost=int(data.get("communication_cost", 0)),
        )


@dataclass
class CorrectionMetrics:
    """Correction outcome aggregates for one device."""

    device_id: str
    correction_attempts: int = 0
    correction_successes: int = 0
    correction_success_rate: float = 0.0
    rollback_count: int = 0
    rollback_frequency: float = 0.0
    failure_count: int = 0
    average_improvement: float = 0.0
    recovery_events: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CorrectionMetrics":
        return cls(
            device_id=str(data["device_id"]),
            correction_attempts=int(data.get("correction_attempts", 0)),
            correction_successes=int(data.get("correction_successes", 0)),
            correction_success_rate=float(data.get("correction_success_rate", 0.0)),
            rollback_count=int(data.get("rollback_count", 0)),
            rollback_frequency=float(data.get("rollback_frequency", 0.0)),
            failure_count=int(data.get("failure_count", 0)),
            average_improvement=float(data.get("average_improvement", 0.0)),
            recovery_events=int(data.get("recovery_events", 0)),
        )


@dataclass
class DeviceMetrics:
    """Combined per-device analytics."""

    device_id: str
    synchronization: SynchronizationMetrics
    correction: CorrectionMetrics
    reliability_score: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "device_id": self.device_id,
            "synchronization": self.synchronization.to_dict(),
            "correction": self.correction.to_dict(),
            "reliability_score": self.reliability_score,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "DeviceMetrics":
        return cls(
            device_id=str(data["device_id"]),
            synchronization=SynchronizationMetrics.from_dict(data.get("synchronization") or {"device_id": data["device_id"]}),
            correction=CorrectionMetrics.from_dict(data.get("correction") or {"device_id": data["device_id"]}),
            reliability_score=float(data.get("reliability_score", 0.0)),
            metadata=dict(data.get("metadata") or {}),
        )


@dataclass
class ExperimentAnalytics:
    """Full experiment analytics snapshot."""

    experiment_id: str
    name: str
    strategy: str = "unknown"
    devices: list[DeviceMetrics] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    sync_results: list[dict[str, Any]] = field(default_factory=list)
    transactions: list[dict[str, Any]] = field(default_factory=list)
    health_reports: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "name": self.name,
            "strategy": self.strategy,
            "devices": [d.to_dict() for d in self.devices],
            "events": list(self.events),
            "sync_results": list(self.sync_results),
            "transactions": list(self.transactions),
            "health_reports": list(self.health_reports),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ExperimentAnalytics":
        devices = [
            DeviceMetrics.from_dict(d) if isinstance(d, Mapping) else d
            for d in (data.get("devices") or [])
        ]
        return cls(
            experiment_id=str(data.get("experiment_id", "")),
            name=str(data.get("name", "")),
            strategy=str(data.get("strategy", "unknown")),
            devices=devices,
            events=list(data.get("events") or []),
            sync_results=list(data.get("sync_results") or []),
            transactions=list(data.get("transactions") or []),
            health_reports=list(data.get("health_reports") or []),
            metadata=dict(data.get("metadata") or {}),
        )

    def device(self, device_id: str) -> Optional[DeviceMetrics]:
        for d in self.devices:
            if d.device_id == device_id:
                return d
        return None
