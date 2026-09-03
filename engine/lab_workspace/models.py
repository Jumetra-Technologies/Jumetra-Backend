"""Engineering laboratory workspace models."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class DeviceMode(str, Enum):
    PHYSICAL = "physical"
    VIRTUAL = "virtual"
    SIMULATOR = "simulator"
    HYBRID = "hybrid"


class SimulationSpeed(str, Enum):
    REALTIME = "1x"
    X2 = "2x"
    X5 = "5x"
    X10 = "10x"
    X100 = "100x"


class WorkspaceStatus(str, Enum):
    CREATED = "created"
    CONNECTED = "connected"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"


@dataclass
class CanvasNode:
    node_id: str
    component_id: str
    label: str
    category: str
    position: dict[str, float]
    device_mode: DeviceMode = DeviceMode.VIRTUAL
    pin_map: dict[str, str] = field(default_factory=dict)
    properties: dict[str, Any] = field(default_factory=dict)
    live_state: dict[str, Any] = field(default_factory=dict)
    available: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.node_id,
            "component_id": self.component_id,
            "label": self.label,
            "category": self.category,
            "position": dict(self.position),
            "device_mode": self.device_mode.value,
            "pin_map": dict(self.pin_map),
            "properties": dict(self.properties),
            "live_state": dict(self.live_state),
            "available": self.available,
            "type": "component",
        }


@dataclass
class CanvasWire:
    wire_id: str
    source: str
    source_handle: str
    target: str
    target_handle: str
    color: str = "#2563eb"
    protocol: str = "digital"
    voltage_v: float = 3.3
    label: str = ""
    valid: bool = True
    issues: list[str] = field(default_factory=list)
    bus: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.wire_id,
            "source": self.source,
            "sourceHandle": self.source_handle,
            "target": self.target,
            "targetHandle": self.target_handle,
            "color": self.color,
            "protocol": self.protocol,
            "voltage_v": self.voltage_v,
            "label": self.label,
            "valid": self.valid,
            "issues": list(self.issues),
            "bus": dict(self.bus),
        }


@dataclass
class WorkspaceSnapshot:
    """Serializable canvas + simulation state for undo/redo and persistence."""

    nodes: list[dict[str, Any]] = field(default_factory=list)
    wires: list[dict[str, Any]] = field(default_factory=list)
    selected_ids: list[str] = field(default_factory=list)
    viewport: dict[str, float] = field(default_factory=lambda: {"x": 0, "y": 0, "zoom": 1})

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": list(self.nodes),
            "wires": list(self.wires),
            "selected_ids": list(self.selected_ids),
            "viewport": dict(self.viewport),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkspaceSnapshot":
        return cls(
            nodes=list(data.get("nodes") or []),
            wires=list(data.get("wires") or []),
            selected_ids=list(data.get("selected_ids") or []),
            viewport=dict(data.get("viewport") or {"x": 0, "y": 0, "zoom": 1}),
        )


@dataclass
class EngineeringWorkspace:
    workspace_id: str
    name: str
    project_id: str = ""
    status: WorkspaceStatus = WorkspaceStatus.CREATED
    nodes: dict[str, CanvasNode] = field(default_factory=dict)
    wires: dict[str, CanvasWire] = field(default_factory=dict)
    speed: SimulationSpeed = SimulationSpeed.REALTIME
    sim_time_ms: int = 0
    tick_count: int = 0
    events_per_sec: float = 0.0
    fps: float = 0.0
    console_lines: list[dict[str, Any]] = field(default_factory=list)
    serial_lines: list[dict[str, Any]] = field(default_factory=list)
    event_log: list[dict[str, Any]] = field(default_factory=list)
    gpio_samples: list[dict[str, Any]] = field(default_factory=list)
    adc_samples: list[dict[str, Any]] = field(default_factory=list)
    created_at: int = field(default_factory=lambda: int(time.time() * 1000))
    updated_at: int = field(default_factory=lambda: int(time.time() * 1000))
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(cls, *, name: str, project_id: str = "") -> "EngineeringWorkspace":
        return cls(
            workspace_id=f"WS{uuid.uuid4().hex[:10].upper()}",
            name=name,
            project_id=project_id,
        )

    def touch(self) -> None:
        self.updated_at = int(time.time() * 1000)

    def to_react_flow(self) -> dict[str, Any]:
        return {
            "nodes": [n.to_dict() for n in self.nodes.values()],
            "edges": [w.to_dict() for w in self.wires.values()],
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "workspace_id": self.workspace_id,
            "name": self.name,
            "project_id": self.project_id,
            "status": self.status.value,
            "speed": self.speed.value,
            "sim_time_ms": self.sim_time_ms,
            "tick_count": self.tick_count,
            "events_per_sec": self.events_per_sec,
            "fps": self.fps,
            "canvas": self.to_react_flow(),
            "node_count": len(self.nodes),
            "wire_count": len(self.wires),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": dict(self.metadata),
        }

    def get_state(self) -> dict[str, Any]:
        return {
            **self.to_dict(),
            "console": self.console_lines[-100:],
            "serial": self.serial_lines[-100:],
            "events": self.event_log[-100:],
            "gpio_samples": self.gpio_samples[-200:],
            "adc_samples": self.adc_samples[-200:],
            "devices": [n.to_dict() for n in self.nodes.values()],
            "inspector": {
                "fps": self.fps,
                "events_per_sec": self.events_per_sec,
                "sim_time_ms": self.sim_time_ms,
                "tick_count": self.tick_count,
                "queue_length": len(self.event_log),
                "node_count": len(self.nodes),
                "wire_count": len(self.wires),
                "status": self.status.value,
            },
        }

    def snapshot(self) -> WorkspaceSnapshot:
        return WorkspaceSnapshot(
            nodes=[n.to_dict() for n in self.nodes.values()],
            wires=[w.to_dict() for w in self.wires.values()],
        )

    @classmethod
    def from_state(cls, data: dict[str, Any]) -> "EngineeringWorkspace":
        """Restore a workspace from persisted ``get_state()`` JSON."""
        ws = cls(
            workspace_id=str(data["workspace_id"]),
            name=str(data.get("name") or "Untitled Workspace"),
            project_id=str(data.get("project_id") or ""),
            status=WorkspaceStatus(str(data.get("status") or WorkspaceStatus.CREATED.value)),
            speed=SimulationSpeed(str(data.get("speed") or SimulationSpeed.REALTIME.value)),
            sim_time_ms=int(data.get("sim_time_ms") or 0),
            tick_count=int(data.get("tick_count") or 0),
            events_per_sec=float(data.get("events_per_sec") or 0.0),
            fps=float(data.get("fps") or 0.0),
            created_at=int(data.get("created_at") or int(time.time() * 1000)),
            updated_at=int(data.get("updated_at") or int(time.time() * 1000)),
            metadata=dict(data.get("metadata") or {}),
        )
        canvas = data.get("canvas") or {}
        for raw in canvas.get("nodes") or []:
            ws.nodes[str(raw["id"])] = CanvasNode(
                node_id=str(raw["id"]),
                component_id=str(raw["component_id"]),
                label=str(raw.get("label") or raw["component_id"]),
                category=str(raw.get("category") or "sensors"),
                position=dict(raw.get("position") or {"x": 0, "y": 0}),
                device_mode=DeviceMode(str(raw.get("device_mode") or DeviceMode.VIRTUAL.value)),
                pin_map=dict(raw.get("pin_map") or {}),
                properties=dict(raw.get("properties") or {}),
                live_state=dict(raw.get("live_state") or {}),
                available=bool(raw.get("available", True)),
            )
        for raw in canvas.get("edges") or []:
            ws.wires[str(raw["id"])] = CanvasWire(
                wire_id=str(raw["id"]),
                source=str(raw["source"]),
                source_handle=str(raw.get("sourceHandle") or "out"),
                target=str(raw["target"]),
                target_handle=str(raw.get("targetHandle") or "in"),
                color=str(raw.get("color") or "#2563eb"),
                protocol=str(raw.get("protocol") or "digital"),
                voltage_v=float(raw.get("voltage_v") or 3.3),
                label=str(raw.get("label") or ""),
                valid=bool(raw.get("valid", True)),
                issues=list(raw.get("issues") or []),
                bus=dict(raw.get("bus") or {}),
            )
        ws.console_lines = list(data.get("console") or [])
        ws.serial_lines = list(data.get("serial") or [])
        ws.event_log = list(data.get("events") or [])
        ws.gpio_samples = list(data.get("gpio_samples") or [])
        ws.adc_samples = list(data.get("adc_samples") or [])
        return ws
