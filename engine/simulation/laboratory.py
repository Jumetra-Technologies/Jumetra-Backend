"""Virtual laboratory orchestration with simulation runtime."""

from __future__ import annotations

import uuid
from typing import Any, Optional

from engine.components.registry import ComponentRegistry
from engine.controllers.compatibility import CompatibilityEngine, ControllerRegistry
from engine.events.event_bus import EventBus

from .factory import VirtualComponentFactory
from .runtime.engine import SimulationEngine
from .session import LaboratoryManager, SimulationSession, SimulationStatus, VirtualLaboratory
from .storage.persistence import LaboratoryStorage


class VirtualLaboratoryService:
    """High-level service for creating and running virtual laboratories."""

    def __init__(
        self,
        component_registry: ComponentRegistry,
        controller_registry: ControllerRegistry,
        *,
        laboratory_manager: Optional[LaboratoryManager] = None,
        storage: Optional[LaboratoryStorage] = None,
        event_bus: Optional[EventBus] = None,
    ) -> None:
        self.components = component_registry
        self.controllers = controller_registry
        self.compatibility = CompatibilityEngine()
        self.factory = VirtualComponentFactory()
        self.labs = laboratory_manager or LaboratoryManager()
        self.storage = storage or LaboratoryStorage()
        self.event_bus = event_bus or EventBus()
        self._engines: dict[str, SimulationEngine] = {}

    def create(
        self,
        *,
        name: str,
        controller_id: str,
        component_ids: list[str],
        description: str = "",
        metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        controller = self.controllers.require(controller_id)
        specs = [self.components.require(cid) for cid in component_ids]

        compatibility_report = []
        for spec in specs:
            result = self.compatibility.check(spec, controller)
            if not result.compatible:
                raise ValueError(
                    f"{spec.name} is not compatible with {controller.name}: "
                    + "; ".join(result.reasons)
                )
            compatibility_report.append(result.to_dict())

        lab = self.labs.create(
            name=name,
            controller_id=controller_id,
            component_ids=component_ids,
            description=description,
            metadata={**(metadata or {}), "compatibility": compatibility_report},
        )

        instances = self.factory.create_batch(specs, controller)
        circuit = self._build_circuit(controller, instances)

        session = SimulationSession(
            session_id=f"SIM{lab.laboratory_id[3:]}",
            laboratory_id=lab.laboratory_id,
            name=name,
            controller=controller,
            components=instances,
            circuit=circuit,
        )
        lab.session = session

        lab_dict = lab.to_dict()
        self.storage.save_project(lab.laboratory_id, lab_dict)
        self.storage.save_circuit(lab.laboratory_id, circuit)
        return lab_dict

    def start(self, laboratory_id: str) -> dict[str, Any]:
        lab = self._get_lab(laboratory_id)
        if lab.session is None:
            raise RuntimeError(f"laboratory {laboratory_id} has no session")

        instances = [c.to_dict() for c in lab.session.components]
        engine = SimulationEngine(
            laboratory_id=laboratory_id,
            controller_id=lab.controller_id,
            component_instances=instances,
            circuit=lab.session.circuit,
            event_bus=self.event_bus,
        )
        validation = engine.validate_circuit(
            controller_spec=lab.session.controller,
            component_specs={
                c.component.component_id: c.component for c in lab.session.components
            },
        )
        engine.start()
        self._engines[laboratory_id] = engine
        lab.session.status = SimulationStatus.RUNNING
        lab.session.started_at = engine.clock.now()

        result = {
            "laboratory": lab.to_dict(),
            "status": engine.state.value,
            "validation": validation,
            "state": engine.get_state(),
            "message": "Virtual hardware simulation started",
        }
        self.storage.save_run(laboratory_id, f"RUN{uuid.uuid4().hex[:6].upper()}", engine.get_state())
        return result

    def pause_simulation(self, laboratory_id: str) -> dict[str, Any]:
        engine = self._require_engine(laboratory_id)
        engine.pause()
        return {"status": engine.state.value, "state": engine.get_state()}

    def stop_simulation(self, laboratory_id: str) -> dict[str, Any]:
        engine = self._require_engine(laboratory_id)
        engine.stop()
        lab = self._get_lab(laboratory_id)
        if lab.session:
            lab.session.status = SimulationStatus.STOPPED
        state = engine.get_state()
        self.storage.save_run(laboratory_id, f"RUN{uuid.uuid4().hex[:6].upper()}", state)
        self._engines.pop(laboratory_id, None)
        return {"status": engine.state.value, "state": state}

    def advance_simulation(self, laboratory_id: str, delta_ms: int = 100) -> dict[str, Any]:
        engine = self._require_engine(laboratory_id)
        step = engine.advance_time(delta_ms)
        return {"status": engine.state.value, "step": step, "state": engine.get_state()}

    def get_simulation_state(self, laboratory_id: str) -> dict[str, Any]:
        engine = self._engines.get(laboratory_id)
        if engine is not None:
            return engine.get_state()
        stored = self.storage.load_project(laboratory_id)
        if stored is None:
            raise KeyError(f"laboratory not found: {laboratory_id}")
        return {"laboratory_id": laboratory_id, "state": "created", "stored": stored}

    def send_command(self, laboratory_id: str, instance_id: str, action: str, value: Any = None) -> dict:
        engine = self._require_engine(laboratory_id)
        return engine.send_actuator_command(instance_id, action, value)

    def _get_lab(self, laboratory_id: str) -> VirtualLaboratory:
        try:
            return self.labs.get(laboratory_id)
        except KeyError:
            stored = self.storage.load_project(laboratory_id)
            if stored is None:
                raise
            raise KeyError(f"laboratory {laboratory_id} not in memory; reload not implemented")

    def _require_engine(self, laboratory_id: str) -> SimulationEngine:
        engine = self._engines.get(laboratory_id)
        if engine is None:
            raise RuntimeError(f"simulation not running for {laboratory_id}")
        return engine

    @staticmethod
    def _build_circuit(controller, instances) -> dict[str, Any]:
        nodes = [
            {
                "id": controller.controller_id,
                "type": "controller",
                "label": controller.name,
                "position": {"x": 250, "y": 50},
            }
        ]
        edges = []
        for i, inst in enumerate(instances):
            node_id = inst.instance_id
            nodes.append(
                {
                    "id": node_id,
                    "type": "component",
                    "label": inst.component.name,
                    "component_id": inst.component.component_id,
                    "position": {"x": 100 + (i % 3) * 180, "y": 200 + (i // 3) * 120},
                    "pin_map": inst.pin_map,
                }
            )
            edges.append(
                {
                    "id": f"e-{controller.controller_id}-{node_id}",
                    "source": controller.controller_id,
                    "target": node_id,
                    "label": ", ".join(inst.pin_map.values()),
                }
            )
        return {"nodes": nodes, "edges": edges}
