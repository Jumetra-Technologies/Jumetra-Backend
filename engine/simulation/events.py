"""Simulation event types and EventBus integration."""

from __future__ import annotations

from typing import Any, Optional

from engine.events.event import Event
from engine.events.event_bus import EventBus


class SimulationEventType:
    SENSOR_DATA = "SENSOR_DATA"
    GPIO_CHANGE = "GPIO_CHANGE"
    ACTUATOR_UPDATE = "ACTUATOR_UPDATE"
    SIMULATION_TICK = "SIMULATION_TICK"
    SIMULATION_STARTED = "SIMULATION_STARTED"
    SIMULATION_STOPPED = "SIMULATION_STOPPED"


def publish_simulation_event(
    bus: EventBus,
    event_type: str,
    *,
    source: str,
    target: str = "",
    payload: Optional[dict[str, Any]] = None,
    laboratory_id: str = "",
    timestamp: Optional[int] = None,
) -> Event:
    """Publish a simulation event through the HHIP Event Bus."""
    meta = {"laboratory_id": laboratory_id} if laboratory_id else {}
    event = Event.create(
        event_type=event_type,
        source=source,
        target=target,
        payload=dict(payload or {}),
        metadata=meta,
        timestamp=timestamp,
    )
    bus.publish(event)
    return event
