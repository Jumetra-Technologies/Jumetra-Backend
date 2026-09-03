"""Hybrid experiment session — unified physical, virtual, and simulation tracking."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from engine.events.event_bus import EventBus

from ..device import HybridDevice
from ..modes import HybridDeviceMode
from ..events import HybridEventType, publish_hybrid_event


class HybridExperimentStatus(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"


@dataclass
class DeviceAssignment:
    """Maps a catalog component to a device mode and target."""

    component_id: str
    mode: HybridDeviceMode
    device_id: str = ""
    instance_id: str = ""
    pin: str = ""
    available: bool = False
    simulator_backend: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "component_id": self.component_id,
            "mode": self.mode.value,
            "device_id": self.device_id,
            "instance_id": self.instance_id,
            "pin": self.pin,
            "available": self.available,
            "simulator_backend": self.simulator_backend,
        }


@dataclass
class HybridExperimentSession:
    """Tracks a hybrid experiment across physical, virtual, and simulated devices."""

    experiment_id: str
    name: str
    laboratory_id: str = ""
    controller_id: str = ""
    component_ids: list[str] = field(default_factory=list)
    assignments: list[DeviceAssignment] = field(default_factory=list)
    devices: list[HybridDevice] = field(default_factory=list)
    status: HybridExperimentStatus = HybridExperimentStatus.CREATED
    physical_events: list[dict[str, Any]] = field(default_factory=list)
    virtual_events: list[dict[str, Any]] = field(default_factory=list)
    simulation_events: list[dict[str, Any]] = field(default_factory=list)
    latency_samples_ms: list[float] = field(default_factory=list)
    sync_observations: list[dict[str, Any]] = field(default_factory=list)
    created_at: int = field(default_factory=lambda: int(time.time() * 1000))
    started_at: Optional[int] = None

    @classmethod
    def create(
        cls,
        *,
        name: str,
        laboratory_id: str = "",
        controller_id: str = "",
        component_ids: Optional[list[str]] = None,
        assignments: Optional[list[DeviceAssignment]] = None,
    ) -> "HybridExperimentSession":
        return cls(
            experiment_id=f"HYB{uuid.uuid4().hex[:8].upper()}",
            name=name,
            laboratory_id=laboratory_id,
            controller_id=controller_id,
            component_ids=list(component_ids or []),
            assignments=list(assignments or []),
        )

    def start(self, event_bus: Optional[EventBus] = None) -> None:
        if self.status == HybridExperimentStatus.RUNNING:
            return
        self.status = HybridExperimentStatus.RUNNING
        self.started_at = int(time.time() * 1000)
        if event_bus is not None:
            publish_hybrid_event(
                event_bus,
                HybridEventType.HYBRID_EXPERIMENT_STARTED,
                source=self.experiment_id,
                payload={"name": self.name, "assignments": [a.to_dict() for a in self.assignments]},
                experiment_id=self.experiment_id,
            )

    def stop(self, event_bus: Optional[EventBus] = None) -> None:
        self.status = HybridExperimentStatus.STOPPED
        if event_bus is not None:
            publish_hybrid_event(
                event_bus,
                HybridEventType.HYBRID_EXPERIMENT_STOPPED,
                source=self.experiment_id,
                payload={"event_counts": self.event_counts()},
                experiment_id=self.experiment_id,
            )

    def record_physical(self, payload: dict[str, Any], *, latency_ms: Optional[float] = None) -> None:
        entry = {"timestamp_ms": int(time.time() * 1000), **payload}
        self.physical_events.append(entry)
        if latency_ms is not None:
            self.latency_samples_ms.append(latency_ms)

    def record_virtual(self, payload: dict[str, Any]) -> None:
        self.virtual_events.append({"timestamp_ms": int(time.time() * 1000), **payload})

    def record_simulation(self, payload: dict[str, Any]) -> None:
        self.simulation_events.append({"timestamp_ms": int(time.time() * 1000), **payload})

    def record_sync_observation(self, observation: dict[str, Any]) -> None:
        """Record sync latency observation without modifying sync algorithms."""
        self.sync_observations.append({"timestamp_ms": int(time.time() * 1000), **observation})

    def event_counts(self) -> dict[str, int]:
        return {
            "physical": len(self.physical_events),
            "virtual": len(self.virtual_events),
            "simulation": len(self.simulation_events),
        }

    def missing_components(self, required: list[str]) -> list[str]:
        assigned = {a.component_id for a in self.assignments if a.available}
        return [cid for cid in required if cid not in assigned]

    def hardware_availability(self) -> dict[str, Any]:
        by_mode: dict[str, list[dict[str, Any]]] = {
            HybridDeviceMode.PHYSICAL.value: [],
            HybridDeviceMode.VIRTUAL.value: [],
            HybridDeviceMode.SIMULATED.value: [],
            HybridDeviceMode.HYBRID.value: [],
        }
        for device in self.devices:
            by_mode[device.mode.value].append(device.to_dict())
        for assignment in self.assignments:
            if not assignment.available:
                by_mode.setdefault("missing", []).append(assignment.to_dict())
        return by_mode

    def average_latency_ms(self) -> float:
        if not self.latency_samples_ms:
            return 0.0
        return round(sum(self.latency_samples_ms) / len(self.latency_samples_ms), 2)

    def to_dict(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "name": self.name,
            "laboratory_id": self.laboratory_id,
            "controller_id": self.controller_id,
            "component_ids": list(self.component_ids),
            "assignments": [a.to_dict() for a in self.assignments],
            "devices": [d.to_dict() for d in self.devices],
            "status": self.status.value,
            "event_counts": self.event_counts(),
            "average_latency_ms": self.average_latency_ms(),
            "sync_observations": len(self.sync_observations),
            "created_at": self.created_at,
            "started_at": self.started_at,
        }

    def get_state(self) -> dict[str, Any]:
        return {
            **self.to_dict(),
            "physical_events": self.physical_events[-20:],
            "virtual_events": self.virtual_events[-20:],
            "simulation_events": self.simulation_events[-20:],
            "hardware_availability": self.hardware_availability(),
            "missing_components": self.missing_components(self.component_ids),
        }
