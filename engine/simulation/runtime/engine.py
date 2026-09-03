"""SimulationEngine — functional virtual hardware simulation runtime."""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from engine.events.event_bus import EventBus

from ..behaviors.base import VirtualComponentBehavior
from ..behaviors.factory import create_behavior
from ..circuit.graph import CircuitGraph
from ..circuit.validation import CircuitValidator
from ..events import SimulationEventType, publish_simulation_event
from ..virtual_controllers.base import VirtualMicrocontroller, create_virtual_controller
from .clock import SimulationClock
from .scheduler import SimulationScheduler


class EngineState(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"


class SimulationEngine:
    """Orchestrates virtual controller, component behaviors, and event bus."""

    def __init__(
        self,
        *,
        laboratory_id: str,
        controller_id: str,
        component_instances: list[dict[str, Any]],
        circuit: dict[str, Any],
        event_bus: Optional[EventBus] = None,
        tick_interval_ms: int = 100,
    ) -> None:
        self.laboratory_id = laboratory_id
        self.controller_id = controller_id
        self.event_bus = event_bus or EventBus()
        self.clock = SimulationClock()
        self.scheduler = SimulationScheduler()
        self.state = EngineState.CREATED
        self.tick_interval_ms = tick_interval_ms
        self.tick_count = 0
        self.event_log: list[dict[str, Any]] = []

        self.circuit_graph = CircuitGraph.from_legacy_circuit(circuit, laboratory_id=laboratory_id)
        self.controller: VirtualMicrocontroller = create_virtual_controller(
            controller_id,
            event_bus=self.event_bus,
            laboratory_id=laboratory_id,
        )
        self.behaviors: list[VirtualComponentBehavior] = []
        for inst in component_instances:
            behavior = create_behavior(
                str(inst.get("component_id") or inst.get("component", {}).get("component_id", "")),
                str(inst.get("instance_id", "")),
                pin_map=dict(inst.get("pin_map") or {}),
                event_bus=self.event_bus,
                laboratory_id=laboratory_id,
            )
            if behavior is not None:
                self.behaviors.append(behavior)

        self._wire_scheduler()

    def _wire_scheduler(self) -> None:
        def _tick_behaviors(_interval: int, sim_time: int) -> None:
            if self.state != EngineState.RUNNING:
                return
            for behavior in self.behaviors:
                behavior.tick(_interval, sim_time)

        self.scheduler.schedule("behaviors", self.tick_interval_ms, _tick_behaviors)

    def start(self) -> None:
        if self.state == EngineState.RUNNING:
            return
        self.state = EngineState.RUNNING
        publish_simulation_event(
            self.event_bus,
            SimulationEventType.SIMULATION_STARTED,
            source=self.laboratory_id,
            payload={"controller_id": self.controller_id},
            laboratory_id=self.laboratory_id,
        )

    def pause(self) -> None:
        if self.state == EngineState.RUNNING:
            self.state = EngineState.PAUSED

    def stop(self) -> None:
        self.state = EngineState.STOPPED
        publish_simulation_event(
            self.event_bus,
            SimulationEventType.SIMULATION_STOPPED,
            source=self.laboratory_id,
            payload={"tick_count": self.tick_count},
            laboratory_id=self.laboratory_id,
        )

    def advance_time(self, delta_ms: int) -> dict[str, Any]:
        if self.state != EngineState.RUNNING:
            raise RuntimeError("simulation is not running")
        if delta_ms <= 0:
            raise ValueError("delta_ms must be positive")

        sim_time = self.clock.advance(delta_ms)
        fired = self.scheduler.tick(delta_ms, sim_time)
        self.tick_count += 1

        publish_simulation_event(
            self.event_bus,
            SimulationEventType.SIMULATION_TICK,
            source=self.laboratory_id,
            payload={"delta_ms": delta_ms, "sim_time_ms": sim_time, "tick": self.tick_count},
            laboratory_id=self.laboratory_id,
            timestamp=sim_time,
        )

        return {
            "sim_time_ms": sim_time,
            "tick": self.tick_count,
            "fired_tasks": fired,
            "behaviors": [b.to_dict() for b in self.behaviors],
            "controller": self.controller.to_dict(),
        }

    def send_actuator_command(self, instance_id: str, action: str, value: Any = None) -> dict[str, Any]:
        for behavior in self.behaviors:
            if behavior.instance_id == instance_id and hasattr(behavior, "command"):
                return behavior.command(action, value)  # type: ignore[union-attr]
        raise KeyError(f"actuator not found: {instance_id}")

    def get_state(self) -> dict[str, Any]:
        return {
            "laboratory_id": self.laboratory_id,
            "controller_id": self.controller_id,
            "state": self.state.value,
            "sim_time_ms": self.clock.now(),
            "tick_count": self.tick_count,
            "behaviors": [b.to_dict() for b in self.behaviors],
            "controller": self.controller.to_dict(),
            "circuit": self.circuit_graph.to_dict(),
        }

    def validate_circuit(
        self,
        *,
        controller_spec: Any = None,
        component_specs: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        validator = CircuitValidator()
        result = validator.validate(
            self.circuit_graph,
            controller=controller_spec,
            components=component_specs or {},
        )
        return result.to_dict()
