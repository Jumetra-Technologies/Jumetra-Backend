"""SynchronizationScheduler — interval scheduling for sync measurements."""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from typing import Any, Callable, Mapping, Optional

from ..time.timestamp_service import TimestampService, get_timestamp_service

logger = logging.getLogger("hhip.synchronization.scheduler")

MeasurementTrigger = Callable[[str], None]


@dataclass
class ScheduledDevice:
    """Per-device sync schedule entry."""

    device_id: str
    interval_ms: int
    last_sync_time: int = 0
    next_sync_time: int = 0
    adaptive: bool = False
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ScheduledDevice":
        return cls(
            device_id=str(data["device_id"]),
            interval_ms=int(data["interval_ms"]),
            last_sync_time=int(data.get("last_sync_time", 0)),
            next_sync_time=int(data.get("next_sync_time", 0)),
            adaptive=bool(data.get("adaptive", False)),
            enabled=bool(data.get("enabled", True)),
        )


class SynchronizationScheduler:
    """Schedule periodic synchronization measurements per device.

    Triggers measurement callbacks only — never applies clock correction.
    Supports adaptive interval updates via :meth:`apply_adaptive_interval`.
    """

    def __init__(
        self,
        *,
        default_interval_ms: int = 5_000,
        timestamp_service: Optional[TimestampService] = None,
        on_trigger: Optional[MeasurementTrigger] = None,
    ) -> None:
        if default_interval_ms < 1:
            raise ValueError("default_interval_ms must be >= 1")
        self._default_interval_ms = default_interval_ms
        self._ts = timestamp_service or get_timestamp_service()
        self._schedules: dict[str, ScheduledDevice] = {}
        self._on_trigger = on_trigger

    def schedule(
        self,
        device: str,
        *,
        interval_ms: Optional[int] = None,
        adaptive: bool = False,
        start_at: Optional[int] = None,
    ) -> ScheduledDevice:
        """Register or update a sync schedule for ``device``."""
        device_id = str(device)
        interval = int(interval_ms if interval_ms is not None else self._default_interval_ms)
        if interval < 1:
            raise ValueError("interval_ms must be >= 1")

        now = int(start_at if start_at is not None else self._ts.now())
        entry = ScheduledDevice(
            device_id=device_id,
            interval_ms=interval,
            last_sync_time=0,
            next_sync_time=now + interval,
            adaptive=adaptive,
            enabled=True,
        )
        existing = self._schedules.get(device_id)
        if existing is not None:
            entry.last_sync_time = existing.last_sync_time
            if existing.enabled and existing.next_sync_time > now:
                entry.next_sync_time = existing.next_sync_time
        self._schedules[device_id] = entry
        logger.info(
            "[SYNC SCHEDULER] scheduled %s interval=%sms next=%s adaptive=%s",
            device_id,
            interval,
            entry.next_sync_time,
            adaptive,
        )
        return entry

    def cancel(self, device: str) -> bool:
        """Disable scheduling for ``device``."""
        device_id = str(device)
        entry = self._schedules.get(device_id)
        if entry is None:
            return False
        entry.enabled = False
        logger.info("[SYNC SCHEDULER] cancelled %s", device_id)
        return True

    def remove(self, device: str) -> bool:
        """Remove schedule entry entirely."""
        return self._schedules.pop(str(device), None) is not None

    def next_sync_time(self, device: str) -> Optional[int]:
        """Return the next scheduled sync time for ``device``, or None."""
        entry = self._schedules.get(str(device))
        if entry is None or not entry.enabled:
            return None
        return entry.next_sync_time

    def get_schedule(self, device: str) -> Optional[ScheduledDevice]:
        return self._schedules.get(str(device))

    def all_schedules(self) -> dict[str, ScheduledDevice]:
        """Return a copy of all schedule entries."""
        return dict(self._schedules)

    def mark_synced(self, device: str, *, at_time_ms: Optional[int] = None) -> None:
        """Record that a sync measurement completed and advance the schedule."""
        device_id = str(device)
        entry = self._schedules.get(device_id)
        if entry is None or not entry.enabled:
            return
        now = int(at_time_ms if at_time_ms is not None else self._ts.now())
        entry.last_sync_time = now
        entry.next_sync_time = now + entry.interval_ms

    def due_devices(self, *, at_time_ms: Optional[int] = None) -> list[str]:
        """Return device ids whose next sync time has elapsed."""
        now = int(at_time_ms if at_time_ms is not None else self._ts.now())
        due = []
        for device_id, entry in sorted(self._schedules.items()):
            if entry.enabled and entry.next_sync_time <= now:
                due.append(device_id)
        return due

    def poll(self, *, at_time_ms: Optional[int] = None) -> list[str]:
        """Trigger measurements for all due devices; return triggered ids."""
        triggered: list[str] = []
        for device_id in self.due_devices(at_time_ms=at_time_ms):
            self._fire(device_id)
            triggered.append(device_id)
        return triggered

    def set_interval(self, device: str, interval_ms: int, *, adaptive: bool = False) -> None:
        """Update interval (fixed or adaptive mode flag)."""
        device_id = str(device)
        entry = self._schedules.get(device_id)
        if entry is None:
            self.schedule(device_id, interval_ms=interval_ms, adaptive=adaptive)
            return
        entry.interval_ms = int(interval_ms)
        entry.adaptive = adaptive
        if entry.last_sync_time > 0:
            entry.next_sync_time = entry.last_sync_time + entry.interval_ms

    def apply_adaptive_interval(
        self,
        device: str,
        interval_ms: int,
        *,
        from_time_ms: Optional[int] = None,
    ) -> Optional[ScheduledDevice]:
        """Apply an adaptive strategy interval decision to future scheduling."""
        device_id = str(device)
        interval = max(1, int(interval_ms))
        entry = self._schedules.get(device_id)
        if entry is None:
            return self.schedule(device_id, interval_ms=interval, adaptive=True)

        entry.interval_ms = interval
        entry.adaptive = True
        anchor = int(from_time_ms if from_time_ms is not None else self._ts.now())
        if entry.last_sync_time > 0:
            entry.next_sync_time = entry.last_sync_time + interval
        else:
            entry.next_sync_time = anchor + interval
        logger.info(
            "[SYNC SCHEDULER] adaptive interval %s → %sms next=%s",
            device_id,
            interval,
            entry.next_sync_time,
        )
        return entry

    def _fire(self, device_id: str) -> None:
        logger.info("[SYNC SCHEDULER] trigger %s", device_id)
        if self._on_trigger is not None:
            self._on_trigger(device_id)
        self.mark_synced(device_id)
