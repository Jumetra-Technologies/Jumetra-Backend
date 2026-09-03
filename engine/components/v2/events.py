"""Component signal events published via existing EventBus (extend-only)."""

from __future__ import annotations

from typing import Any, Optional

from engine.events.event import Event, EventPriority
from engine.events.event_bus import EventBus

COMPONENT_SIGNAL_CHANGED = "COMPONENT_SIGNAL_CHANGED"


def publish_component_signal(
    event_bus: EventBus,
    *,
    component_id: str,
    instance_id: str = "",
    signal: Optional[dict[str, Any]] = None,
    source: str = "component-engine-v2",
) -> Event:
    """Publish COMPONENT_SIGNAL_CHANGED without modifying EventBus core."""
    event = Event.create(
        event_type=COMPONENT_SIGNAL_CHANGED,
        source=source,
        target=instance_id or component_id,
        payload={
            "component_id": instance_id or component_id,
            "definition_id": component_id,
            "signal": dict(signal or {}),
        },
        priority=EventPriority.NORMAL,
    )
    event_bus.publish(event)
    return event
