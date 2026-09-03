"""Hybrid bridge event types and Event Bus integration."""

from __future__ import annotations

from typing import Any, Optional

from engine.events.event import Event
from engine.events.event_bus import EventBus


class HybridEventType:
    HYBRID_BINDING_CREATED = "HYBRID_BINDING_CREATED"
    HYBRID_PHYSICAL_EVENT = "HYBRID_PHYSICAL_EVENT"
    HYBRID_VIRTUAL_EVENT = "HYBRID_VIRTUAL_EVENT"
    HYBRID_SIMULATION_EVENT = "HYBRID_SIMULATION_EVENT"
    HYBRID_PIN_MIRROR = "HYBRID_PIN_MIRROR"
    HYBRID_COMMAND_ROUTED = "HYBRID_COMMAND_ROUTED"
    HYBRID_EXPERIMENT_STARTED = "HYBRID_EXPERIMENT_STARTED"
    HYBRID_EXPERIMENT_STOPPED = "HYBRID_EXPERIMENT_STOPPED"
    # Sprint 27 — physical hybrid device layer
    PHYSICAL_DEVICE_CONNECTED = "PHYSICAL_DEVICE_CONNECTED"
    PHYSICAL_DEVICE_DISCONNECTED = "PHYSICAL_DEVICE_DISCONNECTED"
    GPIO_WRITE = "GPIO_WRITE"
    GPIO_STATE = "GPIO_STATE"


def publish_hybrid_event(
    bus: EventBus,
    event_type: str,
    *,
    source: str,
    payload: Optional[dict[str, Any]] = None,
    experiment_id: str = "",
    target: str = "",
    timestamp: Optional[int] = None,
) -> Event:
    meta = {"experiment_id": experiment_id} if experiment_id else {}
    event = Event.create(
        event_type=event_type,
        source=source,
        target=target,
        payload={**(payload or {}), **({"experiment_id": experiment_id} if experiment_id else {})},
        metadata=meta,
        timestamp=timestamp,
    )
    bus.publish(event)
    return event
