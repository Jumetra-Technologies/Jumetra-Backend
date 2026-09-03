"""Control loop cycle result models."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from ..intelligence.decision_engine import SynchronizationPlan


@dataclass
class ControlLoopCycleResult:
    """Outcome of one autonomous synchronization control cycle."""

    device_id: str
    observed: bool = False
    plan: Optional[SynchronizationPlan] = None
    schedule_updated: bool = False
    correction_attempted: bool = False
    correction_applied: bool = False
    correction_verified: bool = False
    rejected: bool = False
    rejection_reason: str = ""
    transaction_state: Optional[str] = None
    profile_updated: bool = False
    recovery_events: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if self.plan is not None:
            data["plan"] = self.plan.to_dict()
        return data
