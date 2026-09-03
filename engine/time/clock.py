"""Clock abstraction for HHIP timing and synchronization research.

Sprint 7 provides the measurement interface and SystemClock only.
DeviceClock / SimulationClock are stubs for later sync work.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Optional


class Clock(ABC):
    """Abstract clock used by TimestampService and future sync engines."""

    @abstractmethod
    def now(self) -> int:
        """Return the current time in epoch milliseconds."""

    def timestamp(self) -> int:
        """Alias for :meth:`now` (explicit naming for experiment code)."""
        return self.now()

    @abstractmethod
    def offset(self) -> int:
        """Return clock offset vs. a reference clock, in milliseconds.

        Positive means this clock is ahead of the reference.
        Correction is not applied in Sprint 7 — measurement only.
        """

    @abstractmethod
    def synchronize(self, reference_time_ms: int) -> int:
        """Record a sync observation against ``reference_time_ms``.

        Returns the computed offset (this.now - reference). Does **not**
        apply correction yet — that belongs to the sync algorithm sprint.
        """


class SystemClock(Clock):
    """Host wall-clock based on ``time.time()``."""

    def __init__(self) -> None:
        self._offset_ms: int = 0
        self._last_sync_time: Optional[int] = None

    def now(self) -> int:
        return int(time.time() * 1000) + self._offset_ms

    def offset(self) -> int:
        return self._offset_ms

    def synchronize(self, reference_time_ms: int) -> int:
        local = int(time.time() * 1000)
        computed = local - int(reference_time_ms)
        # Measurement only: store observation, do not rewrite the clock.
        self._last_sync_time = local
        # Keep _offset_ms unchanged until a future correction algorithm runs.
        self._last_observed_offset = computed
        return computed

    @property
    def last_sync_time(self) -> Optional[int]:
        return self._last_sync_time


class DeviceClock(Clock):
    """Placeholder for a remote device clock (ESP32 millis / RTC).

    Not implemented in Sprint 7 — raises until a device sync adapter exists.
    """

    def __init__(self, device_id: str, *, initial_offset_ms: int = 0) -> None:
        self.device_id = device_id
        self._offset_ms = initial_offset_ms
        self._last_sync_time: Optional[int] = None

    def now(self) -> int:
        raise NotImplementedError(
            "DeviceClock.now() requires a device time source (future sync sprint)"
        )

    def offset(self) -> int:
        return self._offset_ms

    def synchronize(self, reference_time_ms: int) -> int:
        raise NotImplementedError(
            "DeviceClock.synchronize() is reserved for the synchronization algorithm"
        )


class SimulationClock(Clock):
    """Placeholder for simulator / Wokwi virtual time.

    Supports manual time advancement for tests; full sim binding is later.
    """

    def __init__(self, *, start_ms: int = 0) -> None:
        self._sim_time_ms = int(start_ms)
        self._offset_ms = 0
        self._last_sync_time: Optional[int] = None

    def now(self) -> int:
        return self._sim_time_ms + self._offset_ms

    def offset(self) -> int:
        return self._offset_ms

    def synchronize(self, reference_time_ms: int) -> int:
        computed = self.now() - int(reference_time_ms)
        self._last_sync_time = self.now()
        return computed

    def advance(self, delta_ms: int) -> int:
        """Advance simulated time by ``delta_ms`` (test / future Wokwi hook)."""
        if delta_ms < 0:
            raise ValueError("delta_ms must be non-negative")
        self._sim_time_ms += int(delta_ms)
        return self.now()

    def set_time(self, time_ms: int) -> None:
        """Jump simulated time to an absolute value."""
        self._sim_time_ms = int(time_ms)
