"""CorrectionHealthMonitor — track correction reliability metrics."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Optional


@dataclass
class CorrectionHealthReport:
    """Aggregated correction health snapshot."""

    successful_corrections: int = 0
    failed_corrections: int = 0
    rollback_count: int = 0
    average_improvement: float = 0.0
    reliability_score: float = 0.0
    total_attempts: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CorrectionHealthMonitor:
    """Track correction outcomes and compute a reliability score."""

    def __init__(self) -> None:
        self.successful_corrections = 0
        self.failed_corrections = 0
        self.rollback_count = 0
        self._improvement_total = 0.0
        self._improvement_count = 0

    @property
    def total_attempts(self) -> int:
        return self.successful_corrections + self.failed_corrections

    def record_success(self, *, improvement: float = 0.0) -> None:
        self.successful_corrections += 1
        if improvement > 0:
            self._improvement_total += improvement
            self._improvement_count += 1

    def record_failure(self) -> None:
        self.failed_corrections += 1

    def record_rollback(self) -> None:
        self.rollback_count += 1

    @property
    def average_improvement(self) -> float:
        if self._improvement_count == 0:
            return 0.0
        return self._improvement_total / self._improvement_count

    @property
    def reliability_score(self) -> float:
        total = self.total_attempts
        if total == 0:
            return 1.0
        return self.successful_corrections / total

    def report(self) -> CorrectionHealthReport:
        return CorrectionHealthReport(
            successful_corrections=self.successful_corrections,
            failed_corrections=self.failed_corrections,
            rollback_count=self.rollback_count,
            average_improvement=self.average_improvement,
            reliability_score=self.reliability_score,
            total_attempts=self.total_attempts,
        )

    def merge(self, other: "CorrectionHealthMonitor") -> None:
        self.successful_corrections += other.successful_corrections
        self.failed_corrections += other.failed_corrections
        self.rollback_count += other.rollback_count
        self._improvement_total += other._improvement_total
        self._improvement_count += other._improvement_count
