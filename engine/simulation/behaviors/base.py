"""Virtual component behavior base classes."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional

from engine.events.event_bus import EventBus

from ..events import SimulationEventType, publish_simulation_event


class VirtualComponentBehavior(ABC):
    """Base behavior for a simulated hardware component."""

    component_id: str = ""

    def __init__(
        self,
        instance_id: str,
        *,
        pin_map: Optional[dict[str, str]] = None,
        event_bus: Optional[EventBus] = None,
        laboratory_id: str = "",
    ) -> None:
        self.instance_id = instance_id
        self.pin_map = dict(pin_map or {})
        self.event_bus = event_bus
        self.laboratory_id = laboratory_id
        self.state: dict[str, Any] = {"active": True}

    @abstractmethod
    def tick(self, delta_ms: int, sim_time_ms: int) -> dict[str, Any]:
        """Advance simulation and return any emitted readings."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "instance_id": self.instance_id,
            "component_id": self.component_id,
            "pin_map": dict(self.pin_map),
            "state": dict(self.state),
        }

    def _publish(self, event_type: str, payload: dict[str, Any]) -> None:
        if self.event_bus is None:
            return
        publish_simulation_event(
            self.event_bus,
            event_type,
            source=self.instance_id,
            payload=payload,
            laboratory_id=self.laboratory_id,
        )


class VirtualSensor(VirtualComponentBehavior):
    """Sensor that generates readings over simulated time."""

    def read(self) -> dict[str, Any]:
        return dict(self.state.get("last_reading") or {})

    def tick(self, delta_ms: int, sim_time_ms: int) -> dict[str, Any]:
        reading = self._generate_reading(sim_time_ms)
        self.state["last_reading"] = reading
        self.state["last_tick_ms"] = sim_time_ms
        self._publish(SimulationEventType.SENSOR_DATA, {"reading": reading, "component_id": self.component_id})
        return reading

    @abstractmethod
    def _generate_reading(self, sim_time_ms: int) -> dict[str, Any]:
        """Produce sensor-specific data for the current sim time."""


class VirtualActuator(VirtualComponentBehavior):
    """Actuator that receives commands and updates output state."""

    def command(self, action: str, value: Any = None) -> dict[str, Any]:
        result = self._apply_command(action, value)
        self.state["last_command"] = {"action": action, "value": value}
        self._publish(
            SimulationEventType.ACTUATOR_UPDATE,
            {"action": action, "value": value, "state": dict(self.state), "component_id": self.component_id},
        )
        return result

    def tick(self, delta_ms: int, sim_time_ms: int) -> dict[str, Any]:
        self.state["sim_time_ms"] = sim_time_ms
        return {"state": dict(self.state)}

    @abstractmethod
    def _apply_command(self, action: str, value: Any) -> dict[str, Any]:
        """Apply actuator-specific command."""
