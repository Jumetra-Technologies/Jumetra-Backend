"""Thin EventSubscriber adapters used by HHIPEngine.

These bridge existing engine services (metrics, storage, protocol
handlers) onto the Event Bus without teaching the bus about devices.
Dashboard / AI subscribers are intentionally not implemented here.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from .event import Event
from .subscriber import EventSubscriber

logger = logging.getLogger("hhip.events.adapters")

ProtocolHandler = Callable[[Event, dict[str, Any]], None]


class LoggerSubscriber(EventSubscriber):
    """Logs lifecycle-oriented event summaries while DISPATCHED."""

    def handle_event(self, event: Event) -> None:
        logger.info(
            "[EVENT] id=%s type=%s source=%s target=%s corr=%s seq=%s "
            "priority=%s status=%s history=%s",
            event.event_id,
            event.event_type,
            event.source,
            event.target or "-",
            event.correlation_id,
            event.sequence_number,
            event.priority.value,
            event.current_status.value,
            " → ".join(event.history),
        )


class MetricsSubscriber(EventSubscriber):
    """Forwards received events into :class:`~engine.metrics.MetricsCollector`."""

    def __init__(self, metrics: Any) -> None:
        self._metrics = metrics

    def handle_event(self, event: Event) -> None:
        self._metrics.record_event()


class StorageSubscriber(EventSubscriber):
    """Persists events via StorageManager (append-only JSONL)."""

    def __init__(self, storage: Any, *, enabled: bool = True) -> None:
        self._storage = storage
        self._enabled = enabled

    def handle_event(self, event: Event) -> None:
        if not self._enabled:
            return
        self._storage.save_event(event)


class ProtocolSubscriber(EventSubscriber):
    """Invokes the engine's HELLO / HEARTBEAT / STATE_UPDATE handlers."""

    def __init__(self, handler: ProtocolHandler) -> None:
        self._handler = handler

    def handle_event(self, event: Event) -> None:
        message = event.protocol_message()
        if message is None:
            message = {
                "type": event.event_type,
                "source": event.source,
                "target": event.target,
                "payload": event.payload,
            }
        self._handler(event, message)
