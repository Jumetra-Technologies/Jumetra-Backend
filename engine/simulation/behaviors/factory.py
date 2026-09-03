"""Behavior factory for virtual components."""

from __future__ import annotations

from typing import Optional

from engine.events.event_bus import EventBus

from .actuators import ACTUATOR_BEHAVIORS
from .base import VirtualComponentBehavior
from .sensors import SENSOR_BEHAVIORS


def create_behavior(
    component_id: str,
    instance_id: str,
    *,
    pin_map: Optional[dict[str, str]] = None,
    event_bus: Optional[EventBus] = None,
    laboratory_id: str = "",
) -> Optional[VirtualComponentBehavior]:
    """Instantiate a virtual behavior for a catalog component id."""
    cls = SENSOR_BEHAVIORS.get(component_id) or ACTUATOR_BEHAVIORS.get(component_id)
    if cls is None:
        return None
    return cls(
        instance_id,
        pin_map=pin_map,
        event_bus=event_bus,
        laboratory_id=laboratory_id,
    )


def list_supported_behaviors() -> list[str]:
    return sorted(set(SENSOR_BEHAVIORS) | set(ACTUATOR_BEHAVIORS))
