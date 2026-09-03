"""Physical correction safety limits."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Optional


@dataclass
class PhysicalCorrectionLimits:
    """Safety limits for physical device correction."""

    max_step_ms: float = 10.0
    max_accumulated_correction_ms: float = 500.0
    cooldown_period_ms: int = 1_000
    stabilization_period_ms: int = 100

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PhysicalCorrectionLimits":
        return cls(
            max_step_ms=float(data.get("max_step_ms", 10.0)),
            max_accumulated_correction_ms=float(
                data.get("max_accumulated_correction_ms", 500.0)
            ),
            cooldown_period_ms=int(data.get("cooldown_period_ms", 1_000)),
            stabilization_period_ms=int(data.get("stabilization_period_ms", 100)),
        )

    def check_step(self, step_ms: float) -> Optional[str]:
        if abs(step_ms) > self.max_step_ms:
            return f"step {step_ms:.2f} exceeds max_step_ms {self.max_step_ms}"
        return None

    def check_accumulated(self, accumulated_ms: float) -> Optional[str]:
        if abs(accumulated_ms) > self.max_accumulated_correction_ms:
            return (
                f"accumulated {accumulated_ms:.2f} exceeds limit "
                f"{self.max_accumulated_correction_ms}"
            )
        return None

    def check_cooldown(self, last_correction_time: int, now_ms: int) -> Optional[str]:
        if last_correction_time <= 0:
            return None
        elapsed = now_ms - last_correction_time
        if elapsed < self.cooldown_period_ms:
            return (
                f"cooldown active: {elapsed}ms < {self.cooldown_period_ms}ms required"
            )
        return None
