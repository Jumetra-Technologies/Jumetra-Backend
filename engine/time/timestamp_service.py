"""Centralized timestamp recording for HHIP Events.

All event lifecycle times should go through TimestampService so latency
math is not duplicated across Event, EventBus, and MetricsCollector.
"""

from __future__ import annotations

from typing import Any, Optional, TYPE_CHECKING

from .clock import Clock, SystemClock

if TYPE_CHECKING:
    from ..events.event import Event, EventStatus

# Timing field names (Sprint 7 measurement schema).
CREATED_TIME = "created_time"
QUEUED_TIME = "queued_time"
DISPATCHED_TIME = "dispatched_time"
PROCESSED_TIME = "processed_time"
COMPLETED_TIME = "completed_time"

TIMING_FIELDS = (
    CREATED_TIME,
    QUEUED_TIME,
    DISPATCHED_TIME,
    PROCESSED_TIME,
    COMPLETED_TIME,
)

_STATUS_TO_FIELD = {
    "CREATED": CREATED_TIME,
    "QUEUED": QUEUED_TIME,
    "DISPATCHED": DISPATCHED_TIME,
    "HANDLED": PROCESSED_TIME,
    "COMPLETED": COMPLETED_TIME,
}


class TimestampService:
    """Records lifecycle timestamps on Events using a shared Clock."""

    def __init__(self, clock: Optional[Clock] = None) -> None:
        self._clock: Clock = clock if clock is not None else SystemClock()

    @property
    def clock(self) -> Clock:
        return self._clock

    def now(self) -> int:
        """Return the current clock reading (epoch ms)."""
        return self._clock.now()

    def ensure_timing(self, event: "Event") -> dict[str, Any]:
        """Ensure ``event.timing`` exists and return it."""
        timing = getattr(event, "timing", None)
        if timing is None or not isinstance(timing, dict):
            event.timing = {}
            timing = event.timing
        return timing

    def stamp(self, event: "Event", field: str, *, time_ms: Optional[int] = None) -> int:
        """Record ``field`` on the event if not already set. Returns the value used."""
        timing = self.ensure_timing(event)
        ts = self.now() if time_ms is None else int(time_ms)
        if timing.get(field) is None:
            timing[field] = ts
        self._sync_legacy_fields(event, field, timing[field])
        return int(timing[field])

    def stamp_status(
        self,
        event: "Event",
        status: "EventStatus | str",
        *,
        time_ms: Optional[int] = None,
    ) -> Optional[int]:
        """Stamp the timing field that corresponds to an EventStatus."""
        name = status.value if hasattr(status, "value") else str(status)
        field = _STATUS_TO_FIELD.get(name)
        if field is None:
            return None
        return self.stamp(event, field, time_ms=time_ms)

    def stamp_created(self, event: "Event", *, time_ms: Optional[int] = None) -> int:
        return self.stamp(event, CREATED_TIME, time_ms=time_ms)

    def get_timing(self, event: "Event") -> dict[str, Optional[int]]:
        """Return a normalized timing snapshot for serialization / export."""
        timing = self.ensure_timing(event)
        return {key: timing.get(key) for key in TIMING_FIELDS}

    def compute_latencies(self, event: "Event") -> dict[str, Optional[float]]:
        """Compute latency segments in milliseconds.

        Definitions (Sprint 7)::

            event_creation_latency — created_time - wire/origin timestamp (0 if local)
            queue_latency          — queued_time - created_time
            dispatch_latency       — dispatched_time - queued_time
            processing_latency     — processed_time - dispatched_time
            total_latency          — completed_time - created_time
        """
        timing = self.ensure_timing(event)
        created = timing.get(CREATED_TIME) or getattr(event, "created_timestamp", None)
        queued = timing.get(QUEUED_TIME)
        dispatched = timing.get(DISPATCHED_TIME)
        processed = timing.get(PROCESSED_TIME)
        completed = timing.get(COMPLETED_TIME) or getattr(event, "completed_timestamp", None)

        origin_ts = None
        meta = getattr(event, "metadata", None) or {}
        if isinstance(meta, dict) and meta.get("origin") == "protocol":
            # Wire timestamp may differ from engine created_time.
            origin_ts = getattr(event, "timestamp", None)

        def _delta(later: Optional[int], earlier: Optional[int]) -> Optional[float]:
            if later is None or earlier is None:
                return None
            return float(later - earlier)

        creation = _delta(created, origin_ts) if origin_ts is not None else 0.0
        if creation is not None and creation < 0:
            creation = 0.0

        return {
            "event_creation_latency": creation,
            "queue_latency": _delta(queued, created),
            "dispatch_latency": _delta(dispatched, queued),
            "processing_latency": _delta(processed, dispatched),
            "total_latency": _delta(completed, created),
        }

    @staticmethod
    def _sync_legacy_fields(event: "Event", field: str, value: int) -> None:
        """Keep Phase 1.4.1A timestamp fields aligned with Sprint 7 timing."""
        if field == CREATED_TIME:
            if getattr(event, "created_timestamp", 0) in (0, None):
                event.created_timestamp = value
        elif field == DISPATCHED_TIME:
            if getattr(event, "processed_timestamp", None) is None:
                event.processed_timestamp = value
        elif field == COMPLETED_TIME:
            event.completed_timestamp = value


# Process-wide default service (tests may replace via set_timestamp_service).
_default_service: Optional[TimestampService] = None


def get_timestamp_service() -> TimestampService:
    """Return the process-wide TimestampService singleton."""
    global _default_service
    if _default_service is None:
        _default_service = TimestampService()
    return _default_service


def set_timestamp_service(service: Optional[TimestampService]) -> None:
    """Replace the process-wide TimestampService (primarily for tests)."""
    global _default_service
    _default_service = service
