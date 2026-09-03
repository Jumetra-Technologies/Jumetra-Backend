"""HardwareNode — digital twin representation of a physical board in the workspace."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from .pin_layout import HardwarePinDef, LivePinState, PinLogicState


class HardwareNodeStatus(str, Enum):
    ONLINE = "online"
    WAITING = "waiting"
    OFFLINE = "offline"
    ERROR = "error"
    CONNECTING = "connecting"


@dataclass
class HardwareNode:
    """Engineering workspace node for any connected (or expected) physical board."""

    device_id: str
    board_type: str
    manufacturer: str = ""
    transport: str = "serial"
    firmware_version: str = ""
    pins: dict[str, HardwarePinDef] = field(default_factory=dict)
    capabilities: list[str] = field(default_factory=list)
    status: HardwareNodeStatus = HardwareNodeStatus.CONNECTING
    heartbeat_ms: int = 0
    position: dict[str, float] = field(default_factory=lambda: {"x": 120.0, "y": 120.0})
    rotation: float = 0.0
    workspace_id: str = ""
    label: str = ""
    model: str = ""
    category: str = "microcontroller"
    endpoint: str = ""
    collapsed: bool = False
    available: bool = True
    last_sync_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    health: str = "unknown"
    metadata: dict[str, Any] = field(default_factory=dict)
    node_id: str = ""  # canvas node id when mirrored into lab workspace

    def __post_init__(self) -> None:
        if not self.node_id:
            safe = self.device_id.replace("/", "_").replace("\\", "_").replace(":", "_")
            self.node_id = f"HN_{safe}"
        if not self.label:
            self.label = self.model or self.board_type

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "device_id": self.device_id,
            "board_type": self.board_type,
            "manufacturer": self.manufacturer,
            "transport": self.transport,
            "communication_method": self.transport,
            "firmware_version": self.firmware_version,
            "pins": [p.to_dict() for p in self.pins.values()],
            "capabilities": list(self.capabilities),
            "status": self.status.value,
            "heartbeat": self.heartbeat_ms,
            "heartbeat_ms": self.heartbeat_ms,
            "position": dict(self.position),
            "rotation": self.rotation,
            "workspace_id": self.workspace_id,
            "label": self.label,
            "model": self.model,
            "category": self.category,
            "endpoint": self.endpoint,
            "port": self.endpoint,
            "collapsed": self.collapsed,
            "available": self.available,
            "last_sync_ms": self.last_sync_ms,
            "health": self.health,
            "metadata": dict(self.metadata),
            # Unified hardware node — no virtual/physical distinction in UI
            "kind": "hardware",
            "component_id": self.board_type,
        }

    def to_canvas_node(self) -> dict[str, Any]:
        """Shape compatible with lab_workspace CanvasNode.to_dict()."""
        return {
            "id": self.node_id,
            "component_id": self.board_type,
            "label": self.label,
            "category": self.category if self.category in {
                "arduino", "esp32", "stm32", "pico", "sensors", "actuators", "displays"
            } else _category_bucket(self.board_type),
            "position": dict(self.position),
            "device_mode": "physical" if self.available else "physical",
            "pin_map": {},
            "properties": {
                "physical_port": self.endpoint,
                "physical_device_id": self.device_id,
                "transport": self.transport,
                "manufacturer": self.manufacturer,
                "firmware_version": self.firmware_version,
                "hardware_node": True,
                "waiting": self.status == HardwareNodeStatus.WAITING,
            },
            "live_state": {
                "pins": {pid: p.state.to_dict() for pid, p in self.pins.items()},
                "heartbeat_ms": self.heartbeat_ms,
                "health": self.health,
                "status": self.status.value,
            },
            "available": self.available and self.status != HardwareNodeStatus.WAITING,
            "type": "hardware",
        }

    def update_pin_gpio(self, pin_name: str, value: int) -> Optional[HardwarePinDef]:
        pin = self.pins.get(pin_name)
        if pin is None:
            # try case-insensitive / number match
            for p in self.pins.values():
                if p.name.upper() == pin_name.upper() or str(p.number) == str(pin_name):
                    pin = p
                    break
        if pin is None:
            return None
        pin.state = LivePinState.from_gpio(value, voltage_v=pin.voltage)
        self.last_sync_ms = pin.state.timestamp_ms
        self.heartbeat_ms = pin.state.timestamp_ms
        return pin

    def touch_heartbeat(self) -> None:
        now = int(time.time() * 1000)
        self.heartbeat_ms = now
        self.last_sync_ms = now
        if self.status in (HardwareNodeStatus.CONNECTING, HardwareNodeStatus.WAITING):
            self.status = HardwareNodeStatus.ONLINE
            self.available = True
            self.health = "ok"

    def mark_waiting(self) -> None:
        self.status = HardwareNodeStatus.WAITING
        self.available = False
        self.health = "waiting"

    def mark_offline(self) -> None:
        self.status = HardwareNodeStatus.OFFLINE
        self.available = False
        self.health = "offline"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HardwareNode":
        pins: dict[str, HardwarePinDef] = {}
        for raw in data.get("pins") or []:
            if isinstance(raw, dict):
                pin = HardwarePinDef.from_dict(raw)
                if pin.name:
                    pins[pin.name] = pin
        status_raw = str(data.get("status") or "connecting")
        try:
            status = HardwareNodeStatus(status_raw)
        except ValueError:
            status = HardwareNodeStatus.CONNECTING
        return cls(
            device_id=str(data.get("device_id") or ""),
            board_type=str(data.get("board_type") or "unknown"),
            manufacturer=str(data.get("manufacturer") or data.get("vendor") or ""),
            transport=str(data.get("transport") or data.get("communication_method") or "serial"),
            firmware_version=str(data.get("firmware_version") or ""),
            pins=pins,
            capabilities=[str(c) for c in (data.get("capabilities") or [])],
            status=status,
            heartbeat_ms=int(data.get("heartbeat_ms") or data.get("heartbeat") or 0),
            position=dict(data.get("position") or {"x": 120.0, "y": 120.0}),
            rotation=float(data.get("rotation") or 0.0),
            workspace_id=str(data.get("workspace_id") or ""),
            label=str(data.get("label") or ""),
            model=str(data.get("model") or ""),
            category=str(data.get("category") or "microcontroller"),
            endpoint=str(data.get("endpoint") or data.get("port") or ""),
            collapsed=bool(data.get("collapsed", False)),
            available=bool(data.get("available", True)),
            last_sync_ms=int(data.get("last_sync_ms") or 0),
            health=str(data.get("health") or "unknown"),
            metadata=dict(data.get("metadata") or {}),
            node_id=str(data.get("node_id") or ""),
        )


def _category_bucket(board_type: str) -> str:
    bt = board_type.lower()
    if "arduino" in bt:
        return "arduino"
    if "esp32" in bt or "esp8266" in bt:
        return "esp32"
    if "stm32" in bt:
        return "stm32"
    if "pico" in bt:
        return "pico"
    if "raspberry" in bt or "rpi" in bt:
        return "pico"
    return "esp32"
