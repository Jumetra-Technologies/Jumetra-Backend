"""AnalyticsEngine — load experiment data and generate research reports."""

from __future__ import annotations

import json
import logging
import statistics
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional, Union

from .models import (
    CorrectionMetrics,
    DeviceMetrics,
    ExperimentAnalytics,
    SynchronizationMetrics,
)
from .reliability import DeviceReliabilityScore

logger = logging.getLogger("hhip.analytics.engine")

PathLike = Union[str, Path]


@dataclass
class ResearchReport:
    """Aggregated research report from experiment analytics."""

    experiment_id: str
    name: str
    strategy: str
    device_count: int
    average_sync_error: float
    offset_stability: float
    drift_rate: float
    correction_success_rate: float
    rollback_frequency: float
    communication_cost: int
    latency_distribution: dict[str, float]
    device_rankings: list[dict[str, Any]]
    summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AnalyticsEngine:
    """Load experiment data, calculate metrics, and generate reports."""

    def __init__(self) -> None:
        self._analytics: Optional[ExperimentAnalytics] = None
        self._raw: dict[str, Any] = {}

    @property
    def analytics(self) -> Optional[ExperimentAnalytics]:
        return self._analytics

    def load_from_dict(self, data: Mapping[str, Any]) -> ExperimentAnalytics:
        """Load raw experiment payload and compute device metrics."""
        self._raw = dict(data)
        self._analytics = self._build_analytics(data)
        return self._analytics

    def load_from_experiment_session(self, session: Any) -> ExperimentAnalytics:
        """Load from an ExperimentSession instance."""
        summary = session.summary() if hasattr(session, "summary") else {}
        payload = {
            "experiment_id": getattr(session, "experiment_id", summary.get("experiment_id", "")),
            "name": getattr(session, "name", summary.get("name", "")),
            "strategy": getattr(session, "metadata", {}).get("strategy", "unknown"),
            "events": list(getattr(session, "events", [])),
            "sync_results": list(getattr(session, "sync_results", [])),
            "sync_measurements": list(getattr(session, "sync_measurements", [])),
            "transactions": list(getattr(session, "metadata", {}).get("transactions", [])),
            "health_reports": list(getattr(session, "metadata", {}).get("health_reports", [])),
            "metadata": dict(getattr(session, "metadata", {})),
            "summary": summary,
        }
        return self.load_from_dict(payload)

    def load_from_path(self, path: PathLike) -> ExperimentAnalytics:
        """Load experiment JSON from disk."""
        p = Path(path)
        with p.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            raise ValueError(f"expected JSON object in {p}")
        return self.load_from_dict(data)

    def load_from_autonomous_metrics(
        self,
        metrics: Mapping[str, Any],
        *,
        experiment_id: str = "autonomous",
        name: str = "autonomous_run",
        device_id: str = "device",
    ) -> ExperimentAnalytics:
        """Load from AutonomousRunMetrics.to_dict() output."""
        payload = {
            "experiment_id": experiment_id,
            "name": name,
            "strategy": str(metrics.get("strategy_name", "unknown")),
            "sync_measurements": [],
            "events": [],
            "metadata": {"autonomous_metrics": dict(metrics), "device_id": device_id},
            "correction_metrics": metrics,
            "communication_cost": int(metrics.get("communication_cost", 0)),
        }
        return self.load_from_dict(payload)

    def calculate_metrics(self) -> ExperimentAnalytics:
        """Recalculate metrics from loaded raw data."""
        if not self._raw:
            raise RuntimeError("no experiment data loaded")
        self._analytics = self._build_analytics(self._raw)
        return self._analytics

    def generate_report(self) -> ResearchReport:
        """Generate a research report from current analytics."""
        if self._analytics is None:
            raise RuntimeError("no analytics loaded")

        analytics = self._analytics
        n = len(analytics.devices) or 1

        avg_error = sum(d.synchronization.average_sync_error for d in analytics.devices) / n
        avg_stability = sum(d.synchronization.offset_stability for d in analytics.devices) / n
        avg_drift = sum(d.synchronization.drift_rate for d in analytics.devices) / n
        avg_success = sum(d.correction.correction_success_rate for d in analytics.devices) / n
        total_rollbacks = sum(d.correction.rollback_count for d in analytics.devices)
        total_attempts = sum(d.correction.correction_attempts for d in analytics.devices)
        rollback_freq = total_rollbacks / total_attempts if total_attempts else 0.0
        comm_cost = sum(d.synchronization.communication_cost for d in analytics.devices)

        latencies = []
        for d in analytics.devices:
            latencies.extend(d.metadata.get("latencies", []))

        latency_dist = self._latency_distribution(latencies)

        rankings = [
            DeviceReliabilityScore.from_device_metrics(d.to_dict()).to_dict()
            for d in analytics.devices
        ]
        rankings = sorted(rankings, key=lambda r: r["score"], reverse=True)

        return ResearchReport(
            experiment_id=analytics.experiment_id,
            name=analytics.name,
            strategy=analytics.strategy,
            device_count=len(analytics.devices),
            average_sync_error=avg_error,
            offset_stability=avg_stability,
            drift_rate=avg_drift,
            correction_success_rate=avg_success,
            rollback_frequency=rollback_freq,
            communication_cost=comm_cost,
            latency_distribution=latency_dist,
            device_rankings=rankings,
            summary={
                "total_events": len(analytics.events),
                "total_sync_results": len(analytics.sync_results),
                "total_transactions": len(analytics.transactions),
                "total_health_reports": len(analytics.health_reports),
            },
        )

    def rank_devices(self) -> list[DeviceReliabilityScore]:
        if self._analytics is None:
            raise RuntimeError("no analytics loaded")
        scores = [
            DeviceReliabilityScore.from_device_metrics(d.to_dict())
            for d in self._analytics.devices
        ]
        return DeviceReliabilityScore.rank_devices(scores)

    def _build_analytics(self, data: Mapping[str, Any]) -> ExperimentAnalytics:
        strategy = str(data.get("strategy", data.get("metadata", {}).get("strategy", "unknown")))
        experiment_id = str(data.get("experiment_id", ""))
        name = str(data.get("name", ""))

        by_device: dict[str, dict[str, list]] = defaultdict(
            lambda: {
                "offsets": [],
                "rtts": [],
                "latencies": [],
                "drifts": [],
                "events": [],
                "corrections": [],
                "transactions": [],
                "health": [],
            }
        )

        for sample in data.get("sync_measurements") or []:
            did = str(sample.get("device_id") or "unknown")
            if sample.get("estimated_offset") is not None:
                by_device[did]["offsets"].append(float(sample["estimated_offset"]))
            if sample.get("round_trip_time") is not None:
                by_device[did]["rtts"].append(float(sample["round_trip_time"]))

        for result in data.get("sync_results") or []:
            did = str(result.get("device_id") or "unknown")
            by_device[did]["drifts"].append(float(result.get("drift_rate", result.get("drift", 0.0))))
            by_device[did]["offsets"].append(float(result.get("estimated_offset", result.get("offset", 0.0))))

        for event in data.get("events") or []:
            did = str(event.get("device_id") or event.get("target") or "unknown")
            by_device[did]["events"].append(event)
            lat = (event.get("latencies") or {}).get("total_latency")
            if lat is not None:
                by_device[did]["latencies"].append(float(lat))

        for txn in data.get("transactions") or []:
            did = str(txn.get("device_id") or "unknown")
            by_device[did]["transactions"].append(txn)

        for health in data.get("health_reports") or []:
            did = str(health.get("device_id") or "unknown")
            by_device[did]["health"].append(health)

        # Autonomous metrics shortcut
        auto = data.get("correction_metrics") or data.get("metadata", {}).get("autonomous_metrics")
        if auto and isinstance(auto, dict):
            did = str(data.get("metadata", {}).get("device_id", "device"))
            by_device[did]["corrections"].append(auto)

        devices: list[DeviceMetrics] = []
        for device_id, buckets in sorted(by_device.items()):
            sync_m = self._sync_metrics(device_id, buckets, data)
            corr_m = self._correction_metrics(device_id, buckets, data)
            reliability = DeviceReliabilityScore.compute(
                device_id,
                success_rate=corr_m.correction_success_rate,
                failure_count=corr_m.failure_count,
                correction_attempts=corr_m.correction_attempts,
                rollback_count=corr_m.rollback_count,
                drift_stability=1.0 / (1.0 + abs(sync_m.drift_rate) * 1000),
                offset_stability=sync_m.offset_stability,
            )
            devices.append(
                DeviceMetrics(
                    device_id=device_id,
                    synchronization=sync_m,
                    correction=corr_m,
                    reliability_score=reliability.score,
                    metadata={"latencies": buckets["latencies"]},
                )
            )

        return ExperimentAnalytics(
            experiment_id=experiment_id,
            name=name,
            strategy=strategy,
            devices=devices,
            events=list(data.get("events") or []),
            sync_results=list(data.get("sync_results") or []),
            transactions=list(data.get("transactions") or []),
            health_reports=list(data.get("health_reports") or []),
            metadata=dict(data.get("metadata") or {}),
        )

    def _sync_metrics(
        self, device_id: str, buckets: dict[str, list], data: Mapping[str, Any]
    ) -> SynchronizationMetrics:
        offsets = buckets["offsets"]
        rtts = buckets["rtts"]
        latencies = buckets["latencies"]

        avg_error = sum(abs(o) for o in offsets) / len(offsets) if offsets else 0.0
        if offsets:
            mean = sum(offsets) / len(offsets)
            variance = sum((o - mean) ** 2 for o in offsets) / len(offsets)
            offset_stability = 1.0 / (1.0 + variance ** 0.5)
        else:
            offset_stability = 0.0

        drifts = buckets["drifts"]
        drift_rate = sum(drifts) / len(drifts) if drifts else 0.0
        avg_rtt = sum(rtts) / len(rtts) if rtts else 0.0
        jitter = 0.0
        if len(rtts) >= 2:
            diffs = [abs(rtts[i] - rtts[i - 1]) for i in range(1, len(rtts))]
            jitter = sum(diffs) / len(diffs)

        all_lat = latencies or rtts
        p50, p95 = self._percentiles(all_lat)

        comm = int(data.get("communication_cost", 0))
        if not comm:
            comm = len(buckets["events"]) + len(buckets["offsets"])
            auto = data.get("correction_metrics") or {}
            if isinstance(auto, dict):
                comm = int(auto.get("communication_cost", comm))

        return SynchronizationMetrics(
            device_id=device_id,
            sync_event_count=len(offsets) or len(buckets["events"]),
            average_sync_error=avg_error,
            offset_stability=offset_stability,
            drift_rate=drift_rate,
            average_rtt=avg_rtt,
            jitter=jitter,
            latency_min_ms=min(all_lat) if all_lat else 0.0,
            latency_max_ms=max(all_lat) if all_lat else 0.0,
            latency_p50_ms=p50,
            latency_p95_ms=p95,
            communication_cost=comm,
        )

    def _correction_metrics(
        self, device_id: str, buckets: dict[str, list], data: Mapping[str, Any]
    ) -> CorrectionMetrics:
        attempts = 0
        successes = 0
        failures = 0
        rollbacks = 0
        recoveries = 0
        improvements: list[float] = []

        for txn in buckets["transactions"]:
            state = str(txn.get("state", ""))
            attempts += 1
            if state == "COMPLETED":
                successes += 1
            elif state in {"FAILED", "ROLLED_BACK"}:
                failures += 1
            if state == "ROLLED_BACK":
                rollbacks += 1
            if txn.get("improvement") is not None:
                improvements.append(float(txn["improvement"]))

        for health in buckets["health"]:
            attempts = max(attempts, int(health.get("total_attempts", 0)))
            successes = max(successes, int(health.get("successful_corrections", 0)))
            failures = max(failures, int(health.get("failed_corrections", 0)))
            rollbacks = max(rollbacks, int(health.get("rollback_count", 0)))
            if health.get("average_improvement"):
                improvements.append(float(health["average_improvement"]))

        for auto in buckets["corrections"]:
            attempts = int(auto.get("correction_attempts", attempts))
            successes = int(auto.get("correction_successes", successes))
            failures = int(auto.get("correction_failures", failures))
            rollbacks = int(auto.get("rollbacks", rollbacks))
            recoveries = int(auto.get("recovery_events", recoveries))

        success_rate = successes / attempts if attempts else 1.0
        rollback_freq = rollbacks / attempts if attempts else 0.0
        avg_imp = sum(improvements) / len(improvements) if improvements else 0.0

        return CorrectionMetrics(
            device_id=device_id,
            correction_attempts=attempts,
            correction_successes=successes,
            correction_success_rate=success_rate,
            rollback_count=rollbacks,
            rollback_frequency=rollback_freq,
            failure_count=failures,
            average_improvement=avg_imp,
            recovery_events=recoveries,
        )

    @staticmethod
    def _percentiles(values: list[float]) -> tuple[float, float]:
        if not values:
            return 0.0, 0.0
        ordered = sorted(values)
        n = len(ordered)
        p50 = ordered[n // 2]
        p95_idx = min(n - 1, int(n * 0.95))
        return float(p50), float(ordered[p95_idx])

    @staticmethod
    def _latency_distribution(latencies: list[float]) -> dict[str, float]:
        if not latencies:
            return {"p50": 0.0, "p95": 0.0, "min": 0.0, "max": 0.0, "mean": 0.0}
        ordered = sorted(latencies)
        n = len(ordered)
        return {
            "min": ordered[0],
            "max": ordered[-1],
            "mean": statistics.mean(ordered),
            "p50": ordered[n // 2],
            "p95": ordered[min(n - 1, int(n * 0.95))],
        }
