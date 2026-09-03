"""SyncIntervalStrategy — fixed and adaptive scheduling hooks."""

from __future__ import annotations

from typing import Any, Mapping, Optional

from .strategy_base import SyncIntervalStrategy


class FixedIntervalStrategy(SyncIntervalStrategy):
    """Constant interval regardless of measurement quality."""

    def __init__(self, interval_ms: int = 5_000) -> None:
        if interval_ms < 1:
            raise ValueError("interval_ms must be >= 1")
        self.interval_ms = interval_ms

    def calculate_next_interval(
        self,
        device_id: str,
        *,
        last_interval_ms: int,
        quality: Optional[Mapping[str, Any]] = None,
        drift: Optional[float] = None,
        confidence: Optional[float] = None,
    ) -> int:
        return self.interval_ms


class AdaptiveStrategy(SyncIntervalStrategy):
    """Deterministic adaptive interval tuning (delegates to intelligence layer)."""

    def __init__(self, config: Optional[Any] = None) -> None:
        from .intelligence.interval_strategy import (
            AdaptiveIntervalConfig,
            AdaptiveIntervalStrategy,
        )

        self._inner = AdaptiveIntervalStrategy(config or AdaptiveIntervalConfig())

    def calculate_next_interval(
        self,
        device_id: str,
        *,
        last_interval_ms: int,
        quality: Optional[Mapping[str, Any]] = None,
        drift: Optional[float] = None,
        confidence: Optional[float] = None,
        **kwargs: Any,
    ) -> int:
        return self._inner.calculate_next_interval(
            device_id,
            last_interval_ms=last_interval_ms,
            quality=quality,
            drift=drift,
            confidence=confidence,
            **kwargs,
        )

    @property
    def inner(self) -> Any:
        return self._inner
