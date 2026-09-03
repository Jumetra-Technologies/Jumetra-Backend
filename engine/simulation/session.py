"""Simulation session — runtime state for a virtual laboratory."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from engine.controllers.models import ControllerSpec

from .adapters import InProcessSimulatorAdapter, SimulatorAdapter
from .factory import VirtualComponentInstance


class SimulationStatus(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"


@dataclass
class SimulationSession:
    """Manages one virtual laboratory simulation run."""

    session_id: str
    laboratory_id: str
    name: str
    controller: ControllerSpec
    components: list[VirtualComponentInstance] = field(default_factory=list)
    status: SimulationStatus = SimulationStatus.CREATED
    adapter: Optional[SimulatorAdapter] = None
    circuit: dict[str, Any] = field(default_factory=dict)
    tick_ms: int = 0
    created_at: int = field(default_factory=lambda: int(time.time() * 1000))
    started_at: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "laboratory_id": self.laboratory_id,
            "name": self.name,
            "controller": self.controller.to_dict(),
            "components": [c.to_dict() for c in self.components],
            "status": self.status.value,
            "circuit": dict(self.circuit),
            "tick_ms": self.tick_ms,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "adapter": self.adapter.name if self.adapter else None,
        }

    def start(self, adapter: Optional[SimulatorAdapter] = None) -> None:
        if self.status == SimulationStatus.RUNNING:
            return
        self.adapter = adapter or InProcessSimulatorAdapter()
        self.adapter.connect()
        self.adapter.load_circuit(self.circuit)
        self.status = SimulationStatus.RUNNING
        self.started_at = int(time.time() * 1000)

    def step(self, delta_ms: int = 10) -> dict[str, Any]:
        if self.adapter is None or self.status != SimulationStatus.RUNNING:
            raise RuntimeError("simulation is not running")
        result = self.adapter.step(delta_ms)
        self.tick_ms += delta_ms
        return result

    def stop(self) -> None:
        if self.adapter is not None:
            self.adapter.disconnect()
        self.status = SimulationStatus.STOPPED


@dataclass
class VirtualLaboratory:
    """Virtual laboratory definition — controller + component set."""

    laboratory_id: str
    name: str
    controller_id: str
    component_ids: list[str]
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    session: Optional[SimulationSession] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "laboratory_id": self.laboratory_id,
            "name": self.name,
            "controller_id": self.controller_id,
            "component_ids": list(self.component_ids),
            "description": self.description,
            "metadata": dict(self.metadata),
            "session": self.session.to_dict() if self.session else None,
        }


class LaboratoryManager:
    """Create and manage virtual laboratories."""

    def __init__(self) -> None:
        self._labs: dict[str, VirtualLaboratory] = {}

    def create(
        self,
        *,
        name: str,
        controller_id: str,
        component_ids: list[str],
        description: str = "",
        metadata: Optional[dict[str, Any]] = None,
    ) -> VirtualLaboratory:
        lab_id = f"LAB{uuid.uuid4().hex[:8].upper()}"
        lab = VirtualLaboratory(
            laboratory_id=lab_id,
            name=name,
            controller_id=controller_id,
            component_ids=list(component_ids),
            description=description,
            metadata=dict(metadata or {}),
        )
        self._labs[lab_id] = lab
        return lab

    def get(self, laboratory_id: str) -> VirtualLaboratory:
        lab = self._labs.get(laboratory_id)
        if lab is None:
            raise KeyError(f"laboratory not found: {laboratory_id}")
        return lab

    def list_all(self) -> list[VirtualLaboratory]:
        return list(self._labs.values())
