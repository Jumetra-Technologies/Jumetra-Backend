"""OffsetFilter — median / moving-average filtering (Kalman hook later)."""

from __future__ import annotations

from collections import deque
from enum import Enum
from typing import Deque, Optional, Sequence


class FilterMode(str, Enum):
    """Supported offset filter modes."""

    MEDIAN = "median"
    MOVING_AVERAGE = "moving_average"
    # Reserved for a future sprint — not implemented yet.
    KALMAN = "kalman"


class OffsetFilter:
    """Filter a stream or batch of offset estimates.

    Interface is intentionally open for a future Kalman filter; requesting
    ``FilterMode.KALMAN`` raises ``NotImplementedError``.
    """

    def __init__(
        self,
        mode: FilterMode | str = FilterMode.MEDIAN,
        *,
        window: int = 5,
    ) -> None:
        if window < 1:
            raise ValueError("window must be >= 1")
        self.mode = FilterMode(mode)
        self.window = window
        self._history: Deque[float] = deque(maxlen=window)

    def reset(self) -> None:
        """Clear the moving window history."""
        self._history.clear()

    def push(self, value: float) -> float:
        """Push one offset and return the filtered value over the window."""
        if self.mode == FilterMode.KALMAN:
            raise NotImplementedError("Kalman filter is reserved for a future sprint")
        self._history.append(float(value))
        return self._filter_values(list(self._history))

    def filter(self, values: Sequence[float]) -> float:
        """Filter a batch of offsets (does not mutate stream history)."""
        if self.mode == FilterMode.KALMAN:
            raise NotImplementedError("Kalman filter is reserved for a future sprint")
        if not values:
            raise ValueError("values must be non-empty")
        windowed = list(values[-self.window :])
        return self._filter_values(windowed)

    def filter_series(self, values: Sequence[float]) -> list[float]:
        """Return a filtered series by scanning with the configured window."""
        if self.mode == FilterMode.KALMAN:
            raise NotImplementedError("Kalman filter is reserved for a future sprint")
        out: list[float] = []
        buf: list[float] = []
        for value in values:
            buf.append(float(value))
            if len(buf) > self.window:
                buf = buf[-self.window :]
            out.append(self._filter_values(buf))
        return out

    def _filter_values(self, values: Sequence[float]) -> float:
        if not values:
            raise ValueError("cannot filter empty window")
        if self.mode == FilterMode.MEDIAN:
            return self._median(values)
        if self.mode == FilterMode.MOVING_AVERAGE:
            return sum(values) / len(values)
        raise NotImplementedError(f"unsupported filter mode: {self.mode}")

    @staticmethod
    def _median(values: Sequence[float]) -> float:
        ordered = sorted(float(v) for v in values)
        n = len(ordered)
        mid = n // 2
        if n % 2 == 1:
            return ordered[mid]
        return (ordered[mid - 1] + ordered[mid]) / 2.0
