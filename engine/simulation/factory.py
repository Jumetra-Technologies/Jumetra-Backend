"""Virtual component factory — instantiate simulated hardware."""

from __future__ import annotations

import uuid
from typing import Any

from engine.components.models import ComponentSpec
from engine.controllers.models import ControllerSpec


class VirtualComponentInstance:
    """Runtime virtual component bound to a simulation session."""

    def __init__(
        self,
        instance_id: str,
        component: ComponentSpec,
        controller: ControllerSpec,
        pin_map: dict[str, str],
    ) -> None:
        self.instance_id = instance_id
        self.component = component
        self.controller = controller
        self.pin_map = dict(pin_map)
        self.state: dict[str, Any] = {"active": True, "values": {}}

    def to_dict(self) -> dict[str, Any]:
        return {
            "instance_id": self.instance_id,
            "component_id": self.component.component_id,
            "component_name": self.component.name,
            "controller_id": self.controller.controller_id,
            "pin_map": dict(self.pin_map),
            "state": dict(self.state),
        }


class VirtualComponentFactory:
    """Create virtual component instances for laboratory simulations."""

    def create(
        self,
        component: ComponentSpec,
        controller: ControllerSpec,
        *,
        pin_prefix: str = "D",
        start_pin: int = 2,
    ) -> VirtualComponentInstance:
        pin_count = component.pins.count if hasattr(component.pins, "count") else 1
        pin_map: dict[str, str] = {}
        for i in range(pin_count):
            pin_map[f"pin_{i}"] = f"{pin_prefix}{start_pin + i}"

        return VirtualComponentInstance(
            instance_id=f"VCI{uuid.uuid4().hex[:8].upper()}",
            component=component,
            controller=controller,
            pin_map=pin_map,
        )

    def create_batch(
        self,
        components: list[ComponentSpec],
        controller: ControllerSpec,
    ) -> list[VirtualComponentInstance]:
        instances: list[VirtualComponentInstance] = []
        next_pin = 2
        for component in components:
            pin_count = component.pins.count if hasattr(component.pins, "count") else 1
            inst = self.create(component, controller, start_pin=next_pin)
            instances.append(inst)
            next_pin += pin_count + 1
        return instances
