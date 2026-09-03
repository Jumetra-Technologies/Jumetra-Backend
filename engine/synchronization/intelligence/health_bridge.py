"""Health feedback bridge — CorrectionHealthMonitor → DeviceSyncProfile."""

from __future__ import annotations

from ..health_monitor import CorrectionHealthReport
from ..intelligence.profile import DeviceSyncProfile


class HealthProfileBridge:
    """Apply correction health metrics to device synchronization profiles."""

    @staticmethod
    def apply(profile: DeviceSyncProfile, health: CorrectionHealthReport) -> None:
        """Merge health monitor stats into a device profile."""
        profile.success_rate = health.reliability_score
        profile.reliability_score = health.reliability_score
        profile.rollback_count = health.rollback_count
        profile.correction_count = max(profile.correction_count, health.total_attempts)
        profile.correction_success_count = health.successful_corrections

        if health.total_attempts > 0:
            stability_blend = min(profile.stability_score, health.reliability_score)
            profile.stability_score = stability_blend

        profile.metadata["failed_corrections"] = health.failed_corrections
        profile.metadata["average_improvement"] = health.average_improvement
        profile.metadata["health_total_attempts"] = health.total_attempts
