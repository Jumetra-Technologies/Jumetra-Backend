"""SyncIntervalStrategy ABC — shared by fixed and adaptive strategies."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Mapping, Optional


class SyncIntervalStrategy(ABC):
    """Calculate the next sync interval for a device (ms)."""

    @abstractmethod
    def calculate_next_interval(
        self,
        device_id: str,
        *,
        last_interval_ms: int,
        quality: Optional[Mapping[str, Any]] = None,
        drift: Optional[float] = None,
        confidence: Optional[float] = None,
    ) -> int:
        """Return the next interval in milliseconds."""
