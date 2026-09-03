"""ExperimentComparison — fixed vs adaptive analytics."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Optional

from .models import ExperimentAnalytics


@dataclass
class ExperimentComparisonResult:
    """Comparison between fixed and adaptive experiment analytics."""

    fixed_experiment_id: str
    adaptive_experiment_id: str
    accuracy_difference: float
    communication_savings: int
    correction_efficiency_difference: float
    failure_difference: int
    sync_error_improvement: float
    rollback_difference: int
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ExperimentComparison:
    """Compare fixed vs adaptive synchronization experiment analytics."""

    @staticmethod
    def _aggregate(analytics: ExperimentAnalytics) -> dict[str, float]:
        if not analytics.devices:
            return {
                "avg_sync_error": 0.0,
                "avg_success_rate": 0.0,
                "total_comm_cost": 0.0,
                "total_failures": 0.0,
                "total_rollbacks": 0.0,
                "avg_improvement": 0.0,
            }
        n = len(analytics.devices)
        return {
            "avg_sync_error": sum(d.synchronization.average_sync_error for d in analytics.devices) / n,
            "avg_success_rate": sum(d.correction.correction_success_rate for d in analytics.devices) / n,
            "total_comm_cost": sum(d.synchronization.communication_cost for d in analytics.devices),
            "total_failures": sum(d.correction.failure_count for d in analytics.devices),
            "total_rollbacks": sum(d.correction.rollback_count for d in analytics.devices),
            "avg_improvement": sum(d.correction.average_improvement for d in analytics.devices) / n,
        }

    @classmethod
    def compare(
        cls,
        fixed: ExperimentAnalytics,
        adaptive: ExperimentAnalytics,
    ) -> ExperimentComparisonResult:
        """Compare fixed and adaptive experiment analytics."""
        f = cls._aggregate(fixed)
        a = cls._aggregate(adaptive)

        fixed_eff = f["avg_success_rate"]
        adaptive_eff = a["avg_success_rate"]
        correction_efficiency_diff = adaptive_eff - fixed_eff

        return ExperimentComparisonResult(
            fixed_experiment_id=fixed.experiment_id,
            adaptive_experiment_id=adaptive.experiment_id,
            accuracy_difference=adaptive_eff - fixed_eff,
            communication_savings=int(f["total_comm_cost"] - a["total_comm_cost"]),
            correction_efficiency_difference=correction_efficiency_diff,
            failure_difference=int(a["total_failures"] - f["total_failures"]),
            sync_error_improvement=f["avg_sync_error"] - a["avg_sync_error"],
            rollback_difference=int(a["total_rollbacks"] - f["total_rollbacks"]),
            metadata={
                "fixed_strategy": fixed.strategy,
                "adaptive_strategy": adaptive.strategy,
                "fixed_avg_sync_error": f["avg_sync_error"],
                "adaptive_avg_sync_error": a["avg_sync_error"],
                "fixed_comm_cost": f["total_comm_cost"],
                "adaptive_comm_cost": a["total_comm_cost"],
            },
        )

    @classmethod
    def from_autonomous_reports(
        cls,
        report: Mapping[str, Any],
        *,
        fixed_id: str = "fixed",
        adaptive_id: str = "adaptive",
    ) -> ExperimentComparisonResult:
        """Build comparison from AutonomousComparisonReport.to_dict() output."""
        from .models import CorrectionMetrics, DeviceMetrics, SynchronizationMetrics

        def _device_from_metrics(metrics: Mapping[str, Any], device_id: str) -> DeviceMetrics:
            return DeviceMetrics(
                device_id=device_id,
                synchronization=SynchronizationMetrics(
                    device_id=device_id,
                    sync_event_count=int(metrics.get("sync_operations", 0)),
                    communication_cost=int(metrics.get("communication_cost", 0)),
                ),
                correction=CorrectionMetrics(
                    device_id=device_id,
                    correction_attempts=int(metrics.get("correction_attempts", 0)),
                    correction_successes=int(metrics.get("correction_successes", 0)),
                    correction_success_rate=float(metrics.get("correction_accuracy", 0.0)),
                    failure_count=int(metrics.get("correction_failures", 0)),
                    rollback_count=int(metrics.get("rollbacks", 0)),
                    recovery_events=int(metrics.get("recovery_events", 0)),
                ),
            )

        fixed_metrics = report.get("fixed") or {}
        adaptive_metrics = report.get("adaptive") or {}
        device_id = str(
            fixed_metrics.get("metadata", {}).get("device_id")
            or adaptive_metrics.get("metadata", {}).get("device_id")
            or "device"
        )

        fixed_analytics = ExperimentAnalytics(
            experiment_id=fixed_id,
            name="fixed",
            strategy="fixed",
            devices=[_device_from_metrics(fixed_metrics, device_id)],
            metadata={"report": dict(fixed_metrics)},
        )
        adaptive_analytics = ExperimentAnalytics(
            experiment_id=adaptive_id,
            name="adaptive",
            strategy="adaptive",
            devices=[_device_from_metrics(adaptive_metrics, device_id)],
            metadata={"report": dict(adaptive_metrics)},
        )
        return cls.compare(fixed_analytics, adaptive_analytics)
