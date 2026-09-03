"""Wiring event types and EventBus helpers (does not modify EventBus core)."""

from __future__ import annotations

from typing import Any, Optional

from engine.events.event import Event
from engine.events.event_bus import EventBus


class WiringEventType:
    PIN_CONNECTED = "PIN_CONNECTED"
    PIN_DISCONNECTED = "PIN_DISCONNECTED"
    PIN_UPDATED = "PIN_UPDATED"
    WIRE_CREATED = "WIRE_CREATED"
    WIRE_REMOVED = "WIRE_REMOVED"
    WIRE_UPDATED = "WIRE_UPDATED"
    SIGNAL_CHANGED = "SIGNAL_CHANGED"
    PIN_MODE_CHANGED = "PIN_MODE_CHANGED"


def publish_wiring_event(
    bus: Optional[EventBus],
    event_type: str,
    *,
    source: str = "wire-manager",
    payload: Optional[dict[str, Any]] = None,
    target: str = "",
) -> Optional[Event]:
    if bus is None:
        return None
    event = Event.create(
        event_type=event_type,
        source=source,
        target=target,
        payload=payload or {},
    )
    bus.publish(event)
    return event
