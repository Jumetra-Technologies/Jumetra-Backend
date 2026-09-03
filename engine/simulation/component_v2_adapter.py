"""Simulation adapter for Component Engine v2 behaviors (extend-only)."""

from __future__ import annotations

from typing import Any, Optional

from engine.components.v2 import default_behavior_registry, default_registry_v2, publish_component_signal
from engine.events.event_bus import EventBus


class ComponentSimulationAdapter:
    """Run v2 package behaviors each tick without modifying core simulation runtime."""

    def __init__(self, event_bus: Optional[EventBus] = None) -> None:
        self.registry = default_registry_v2()
        self.behaviors = default_behavior_registry
        self.event_bus = event_bus or EventBus()
        self._instances: dict[str, Any] = {}

    def ensure_instance(self, component_id: str, instance_id: str) -> Any:
        if instance_id not in self._instances:
            comp = self.registry.get(component_id)
            behavior_name = (comp.simulation.behavior if comp else "") or component_id
            self._instances[instance_id] = self.behaviors.create(
                behavior_name,
                component_id=component_id,
                instance_id=instance_id,
            )
        return self._instances[instance_id]

    def tick(self, component_id: str, instance_id: str, t_s: float, inputs: Optional[dict] = None) -> dict[str, Any]:
        behavior = self.ensure_instance(component_id, instance_id)
        signal = behavior.tick(t_s, inputs)
        publish_component_signal(
            self.event_bus,
            component_id=component_id,
            instance_id=instance_id,
            signal=signal,
        )
        return signal
