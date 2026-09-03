"""Metrics collection for HHIP latency and synchronization research.

Sprint 7 adds segmented latency samples derived from TimestampService.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Mapping, Optional, TYPE_CHECKING

logger = logging.getLogger("hhip.metrics.collector")

if TYPE_CHECKING:
    from ..events.event import Event


class MetricsCollector:
    """In-memory metrics for the event backbone and latency experiments.

    Tracks:

    - ``events_received`` / ``events_processed`` / ``errors``
    - ``processing_time`` (legacy total samples)
    - segmented latencies: creation / queue / dispatch / processing / total
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._events_received: int = 0
        self._events_processed: int = 0
        self._errors: int = 0
        self._processing_times: list[float] = []
        self._event_creation_latencies: list[float] = []
        self._queue_latencies: list[float] = []
        self._dispatch_latencies: list[float] = []
        self._processing_latencies: list[float] = []
        self._total_latencies: list[float] = []

    def record_event(self, *, processed: bool = False, error: bool = False) -> None:
        """Record that an event was received (and optionally processed/errored)."""
        with self._lock:
            self._events_received += 1
            if processed:
                self._events_processed += 1
            if error:
                self._errors += 1

    def record_processing_time(self, duration_ms: float) -> None:
        """Record how long it took to process one event (milliseconds)."""
        if duration_ms < 0:
            raise ValueError("processing time must be non-negative")
        with self._lock:
            self._processing_times.append(float(duration_ms))
        logger.info("[METRIC] Processing time: %.0fms", duration_ms)

    def record_latencies(self, latencies: Mapping[str, Optional[float]]) -> None:
        """Record a latency breakdown (values in milliseconds)."""

        def _append(bucket: list[float], key: str) -> None:
            value = latencies.get(key)
            if value is None:
                return
            bucket.append(float(value))

        with self._lock:
            _append(self._event_creation_latencies, "event_creation_latency")
            _append(self._queue_latencies, "queue_latency")
            _append(self._dispatch_latencies, "dispatch_latency")
            _append(self._processing_latencies, "processing_latency")
            _append(self._total_latencies, "total_latency")

        total = latencies.get("total_latency")
        if total is not None:
            logger.info("[METRIC] Total latency: %.0fms", total)

    def record_event_latencies(self, event: "Event") -> dict[str, Optional[float]]:
        """Compute latencies for ``event`` via TimestampService and record them."""
        from engine.time.timestamp_service import get_timestamp_service

        latencies = get_timestamp_service().compute_latencies(event)
        self.record_latencies(latencies)
        return latencies

    def record_error(self) -> None:
        """Increment the error counter without counting a new received event."""
        with self._lock:
            self._errors += 1

    def mark_processed(self) -> None:
        """Increment ``events_processed`` without counting a new received event."""
        with self._lock:
            self._events_processed += 1

    @staticmethod
    def _avg(samples: list[float]) -> float:
        return (sum(samples) / len(samples)) if samples else 0.0

    def get_metrics(self) -> dict[str, Any]:
        """Return a snapshot of all collected metrics."""
        with self._lock:
            times = list(self._processing_times)
            creation = list(self._event_creation_latencies)
            queue = list(self._queue_latencies)
            dispatch = list(self._dispatch_latencies)
            processing = list(self._processing_latencies)
            total = list(self._total_latencies)
            return {
                "events_received": self._events_received,
                "events_processed": self._events_processed,
                "errors": self._errors,
                "processing_time": times,
                "processing_time_count": len(times),
                "processing_time_total_ms": sum(times) if times else 0.0,
                "processing_time_avg_ms": self._avg(times),
                "event_creation_latency": creation,
                "queue_latency": queue,
                "dispatch_latency": dispatch,
                "processing_latency": processing,
                "total_latency": total,
                "event_creation_latency_avg_ms": self._avg(creation),
                "queue_latency_avg_ms": self._avg(queue),
                "dispatch_latency_avg_ms": self._avg(dispatch),
                "processing_latency_avg_ms": self._avg(processing),
                "total_latency_avg_ms": self._avg(total),
            }

    def reset(self) -> None:
        """Clear all counters and samples."""
        with self._lock:
            self._events_received = 0
            self._events_processed = 0
            self._errors = 0
            self._processing_times.clear()
            self._event_creation_latencies.clear()
            self._queue_latencies.clear()
            self._dispatch_latencies.clear()
            self._processing_latencies.clear()
            self._total_latencies.clear()
