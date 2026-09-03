"""ClockModel — behavioral clock model for calibration (no correction)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Optional


@dataclass
class ClockModel:
    """Model of a remote clock's offset behavior over host time.

    Tracks offset and drift as **observations only**. ``predict`` and
    ``update_measurement`` never rewrite any underlying Clock implementation.
    """

    clock_id: str
    initial_offset: float = 0.0
    current_offset: float = 0.0
    drift_rate: float = 0.0  # offset change per millisecond of host time
    uncertainty: float = 0.0
    last_update: int = 0
    applied_correction: float = 0.0
    _initialized: bool = False

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("_initialized", None)
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ClockModel":
        return cls(
            clock_id=str(data["clock_id"]),
            initial_offset=float(data.get("initial_offset", 0.0)),
            current_offset=float(data.get("current_offset", 0.0)),
            drift_rate=float(data.get("drift_rate", 0.0)),
            uncertainty=float(data.get("uncertainty", 0.0)),
            last_update=int(data.get("last_update", 0)),
            applied_correction=float(data.get("applied_correction", 0.0)),
            _initialized=bool(data.get("last_update", 0)),
        )

    @property
    def remaining_correction(self) -> float:
        """Uncorrected offset magnitude remaining after applied steps."""
        if self.current_offset >= 0:
            return self.current_offset - self.applied_correction
        return self.current_offset - self.applied_correction

    @property
    def effective_offset(self) -> float:
        """Estimated offset after applied bounded corrections."""
        return self.current_offset - self.applied_correction

    def predict(self, at_time_ms: int) -> float:
        """Predict offset at ``at_time_ms`` using the current drift model.

        Does not modify any clock — extrapolation for analysis only.
        """
        if not self._initialized or at_time_ms <= self.last_update:
            return self.current_offset
        dt = at_time_ms - self.last_update
        return self.current_offset + self.drift_rate * dt

    def update_measurement(
        self,
        offset: float,
        at_time_ms: int,
        *,
        uncertainty: Optional[float] = None,
    ) -> None:
        """Incorporate a new offset measurement into the model."""
        offset = float(offset)
        at_time_ms = int(at_time_ms)

        if not self._initialized:
            self.initial_offset = offset
            self.current_offset = offset
            self.last_update = at_time_ms
            self._initialized = True
            if uncertainty is not None:
                self.uncertainty = float(uncertainty)
            return

        if at_time_ms > self.last_update:
            dt = at_time_ms - self.last_update
            self.drift_rate = (offset - self.current_offset) / dt

        self.current_offset = offset
        self.last_update = at_time_ms
        if uncertainty is not None:
            self.uncertainty = float(uncertainty)

    def reset(self) -> None:
        """Clear model state (does not affect real clocks)."""
        self.initial_offset = 0.0
        self.current_offset = 0.0
        self.drift_rate = 0.0
        self.uncertainty = 0.0
        self.last_update = 0
        self.applied_correction = 0.0
        self._initialized = False

    def apply_bounded_correction(self, step: float) -> float:
        """Apply one bounded correction step toward zero offset."""
        step = float(step)
        self.applied_correction += step
        return step

    def rollback_correction(self, step: float) -> float:
        """Reverse one previously applied correction step."""
        step = float(step)
        self.applied_correction -= step
        return step
