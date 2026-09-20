# Node reconciliation source dump — from `C:\Users\BYU\Jumetra-Backend`

## `engine\hardware_nodes\__init__.py`

```python
"""Hardware nodes — digital twin of physical boards in the Engineering Workspace."""

from __future__ import annotations

from .board_renderer import BoardRenderer, get_pin_layout, layout_as_dicts
from .discovery_listener import DiscoveryListener
from .hardware_node import HardwareNode, HardwareNodeStatus
from .hardware_node_factory import HardwareNodeFactory
from .pin_layout import (
    PIN_COLORS,
    HardwarePinDef,
    LivePinState,
    PinKind,
    PinLogicState,
)
from .workspace_sync import WorkspaceEventType, WorkspaceSyncService

__all__ = [
    "BoardRenderer",
    "DiscoveryListener",
    "HardwareNode",
    "HardwareNodeFactory",
    "HardwareNodeStatus",
    "HardwarePinDef",
    "LivePinState",
    "PIN_COLORS",
    "PinKind",
    "PinLogicState",
    "WorkspaceEventType",
    "WorkspaceSyncService",
    "get_pin_layout",
    "layout_as_dicts",
]
```

## `engine\hardware_nodes\hardware_node.py`

```python
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
```

## `engine\hardware_nodes\hardware_node_factory.py`

```python
"""Factory: HybridHardwareDevice / PhysicalDevice → HardwareNode."""

from __future__ import annotations

import time
from typing import Any, Mapping, Optional, Union

from .board_renderer import get_pin_layout
from .hardware_node import HardwareNode, HardwareNodeStatus
from .pin_layout import HardwarePinDef


class HardwareNodeFactory:
    """Convert hybrid / discovery device payloads into workspace HardwareNodes."""

    def __init__(self, *, default_workspace_id: str = "") -> None:
        self.default_workspace_id = default_workspace_id
        self._next_slot = 0

    def from_hybrid_device(
        self,
        device: Union[Mapping[str, Any], Any],
        *,
        workspace_id: str = "",
        position: Optional[dict[str, float]] = None,
    ) -> HardwareNode:
        data = device if isinstance(device, Mapping) else _to_mapping(device)
        board_type = str(data.get("board_type") or "unknown")
        device_id = str(data.get("device_id") or data.get("port") or f"device_{int(time.time())}")

        layout_pins = {p.name: p for p in get_pin_layout(board_type)}
        # Overlay discovery-reported pins when present
        for raw in data.get("pins") or []:
            if not isinstance(raw, dict):
                continue
            name = str(raw.get("pin_id") or raw.get("name") or "")
            if not name:
                continue
            if name in layout_pins:
                # keep layout geometry; refresh type hints from discovery if richer
                continue
            layout_pins[name] = HardwarePinDef.from_dict(
                {
                    **raw,
                    "name": name,
                    "type": str(raw.get("type") or (raw.get("interfaces") or ["GPIO"])[0]).upper(),
                    "x": 0.5,
                    "y": 0.5,
                    "side": "right",
                }
            )

        caps = data.get("capabilities") or []
        if caps and isinstance(caps[0], dict):
            caps = [c.get("name", c) for c in caps]

        pos = position or self._auto_position()
        node = HardwareNode(
            device_id=device_id,
            board_type=board_type,
            manufacturer=str(data.get("manufacturer") or data.get("vendor") or ""),
            transport=str(data.get("transport") or data.get("communication_method") or "serial"),
            firmware_version=str(data.get("firmware_version") or ""),
            pins=layout_pins,
            capabilities=[str(c) for c in caps],
            status=HardwareNodeStatus.ONLINE if data.get("connected", True) else HardwareNodeStatus.WAITING,
            heartbeat_ms=int(time.time() * 1000),
            position=pos,
            workspace_id=workspace_id or self.default_workspace_id,
            label=str(data.get("label") or data.get("model") or board_type),
            model=str(data.get("model") or data.get("label") or board_type),
            category=str(data.get("category") or "microcontroller"),
            endpoint=str(data.get("endpoint") or data.get("port") or ""),
            available=bool(data.get("connected", True)),
            health="ok" if data.get("connected", True) else "waiting",
            metadata={
                "profile_id": data.get("profile_id"),
                "serial_number": (data.get("metadata") or {}).get("serial_number")
                if isinstance(data.get("metadata"), dict)
                else None,
            },
        )
        return node

    def from_waiting(
        self,
        *,
        device_id: str,
        board_type: str,
        workspace_id: str = "",
        endpoint: str = "",
        transport: str = "serial",
        manufacturer: str = "",
        position: Optional[dict[str, float]] = None,
    ) -> HardwareNode:
        pins = {p.name: p for p in get_pin_layout(board_type)}
        return HardwareNode(
            device_id=device_id,
            board_type=board_type,
            manufacturer=manufacturer,
            transport=transport,
            pins=pins,
            status=HardwareNodeStatus.WAITING,
            position=position or self._auto_position(),
            workspace_id=workspace_id or self.default_workspace_id,
            endpoint=endpoint,
            available=False,
            health="waiting",
            label=f"{board_type} (waiting)",
        )

    def _auto_position(self) -> dict[str, float]:
        slot = self._next_slot
        self._next_slot += 1
        col = slot % 4
        row = slot // 4
        return {"x": 80.0 + col * 320.0, "y": 80.0 + row * 220.0}


def _to_mapping(device: Any) -> dict[str, Any]:
    if hasattr(device, "to_dict"):
        return dict(device.to_dict())
    return {
        "device_id": getattr(device, "device_id", ""),
        "board_type": getattr(device, "board_type", "unknown"),
        "manufacturer": getattr(device, "manufacturer", "") or getattr(device, "vendor", ""),
        "transport": getattr(device, "transport", "serial"),
        "firmware_version": getattr(device, "firmware_version", ""),
        "capabilities": getattr(device, "capabilities", []),
        "pins": [],
        "connected": getattr(device, "connected", True),
        "port": getattr(device, "port", "") or getattr(device, "endpoint", ""),
        "endpoint": getattr(device, "endpoint", "") or getattr(device, "port", ""),
        "label": getattr(device, "label", ""),
        "model": getattr(device, "model", ""),
        "category": getattr(device, "category", "microcontroller"),
    }
```

## `engine\hardware_nodes\pin_layout.py`

```python
"""Live pin state and layout models for hardware nodes."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class PinKind(str, Enum):
    GPIO = "GPIO"
    ADC = "ADC"
    DAC = "DAC"
    PWM = "PWM"
    UART = "UART"
    SPI = "SPI"
    I2C = "I2C"
    POWER = "POWER"
    GROUND = "GROUND"


class PinLogicState(str, Enum):
    HIGH = "HIGH"
    LOW = "LOW"
    PWM = "PWM"
    FLOATING = "FLOATING"
    UNKNOWN = "UNKNOWN"


@dataclass
class LivePinState:
    """Realtime electrical / logic state for a single pin."""

    logic: PinLogicState = PinLogicState.UNKNOWN
    value: int = 0
    voltage: float = 0.0
    frequency_hz: float = 0.0
    duty_cycle: float = 0.0
    timestamp_ms: int = field(default_factory=lambda: int(time.time() * 1000))

    def to_dict(self) -> dict[str, Any]:
        return {
            "logic": self.logic.value,
            "value": self.value,
            "voltage": self.voltage,
            "frequency_hz": self.frequency_hz,
            "duty_cycle": self.duty_cycle,
            "timestamp_ms": self.timestamp_ms,
            "state": self.logic.value,  # alias for UI
        }

    @classmethod
    def from_gpio(cls, value: int, *, voltage_v: float = 3.3) -> "LivePinState":
        high = bool(value)
        return cls(
            logic=PinLogicState.HIGH if high else PinLogicState.LOW,
            value=1 if high else 0,
            voltage=voltage_v if high else 0.0,
            timestamp_ms=int(time.time() * 1000),
        )


@dataclass
class HardwarePinDef:
    """Static pin definition with live state."""

    name: str
    number: int | str
    pin_type: str  # GPIO, ADC, ...
    supports_input: bool = True
    supports_output: bool = True
    voltage: float = 3.3
    x: float = 0.0  # 0..1 normalized for silhouette
    y: float = 0.0
    side: str = "left"
    interfaces: list[str] = field(default_factory=list)
    state: LivePinState = field(default_factory=LivePinState)

    @property
    def pin_id(self) -> str:
        return self.name

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "pin_id": self.name,
            "number": self.number,
            "type": self.pin_type,
            "pin_type": self.pin_type,
            "supports_input": self.supports_input,
            "supports_output": self.supports_output,
            "voltage": self.voltage,
            "x": self.x,
            "y": self.y,
            "side": self.side,
            "interfaces": list(self.interfaces) or [self.pin_type.lower()],
            "state": self.state.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HardwarePinDef":
        state_raw = data.get("state")
        state = LivePinState()
        if isinstance(state_raw, dict):
            logic = str(state_raw.get("logic") or state_raw.get("state") or "UNKNOWN")
            try:
                state.logic = PinLogicState(logic)
            except ValueError:
                state.logic = PinLogicState.UNKNOWN
            state.value = int(state_raw.get("value") or 0)
            state.voltage = float(state_raw.get("voltage") or 0.0)
            state.frequency_hz = float(state_raw.get("frequency_hz") or 0.0)
            state.duty_cycle = float(state_raw.get("duty_cycle") or 0.0)
            state.timestamp_ms = int(state_raw.get("timestamp_ms") or time.time() * 1000)
        pin_type = str(data.get("type") or data.get("pin_type") or "GPIO").upper()
        return cls(
            name=str(data.get("name") or data.get("pin_id") or ""),
            number=data.get("number", 0),
            pin_type=pin_type,
            supports_input=bool(data.get("supports_input", True)),
            supports_output=bool(data.get("supports_output", pin_type not in ("POWER", "GROUND", "ADC"))),
            voltage=float(data.get("voltage") or 3.3),
            x=float(data.get("x") or 0.0),
            y=float(data.get("y") or 0.0),
            side=str(data.get("side") or "left"),
            interfaces=list(data.get("interfaces") or []),
            state=state,
        )


# UI color map (documented for dashboard)
PIN_COLORS: dict[str, str] = {
    "GPIO": "#2563eb",
    "ADC": "#16a34a",
    "DAC": "#15803d",
    "PWM": "#7c3aed",
    "UART": "#ea580c",
    "SPI": "#06b6d4",
    "I2C": "#ca8a04",
    "POWER": "#dc2626",
    "GROUND": "#374151",
}
```

## `engine\hardware_nodes\workspace_sync.py`

```python
"""Workspace sync — auto add/remove boards, pin states, persistence, reconnect."""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional

from .hardware_node import HardwareNode, HardwareNodeStatus
from .hardware_node_factory import HardwareNodeFactory
from .pin_layout import PinLogicState

logger = logging.getLogger(__name__)

WsBroadcast = Callable[[dict[str, Any]], None]


class WorkspaceEventType:
    """Workspace / digital-twin event names (EventBus + WebSocket)."""

    WORKSPACE_NODE_CREATED = "WORKSPACE_NODE_CREATED"
    WORKSPACE_NODE_REMOVED = "WORKSPACE_NODE_REMOVED"
    WORKSPACE_NODE_UPDATED = "NODE_UPDATED"
    BOARD_CONNECTED = "BOARD_CONNECTED"
    BOARD_DISCONNECTED = "BOARD_DISCONNECTED"
    PIN_STATE_CHANGED = "PIN_STATE_CHANGED"
    PIN_MODE_CHANGED = "PIN_MODE_CHANGED"
    HEARTBEAT = "HEARTBEAT"
    TRANSPORT_STATUS = "TRANSPORT_STATUS"
    FIRMWARE_VERSION = "FIRMWARE_VERSION"
    NODE_CREATED = "NODE_CREATED"
    NODE_UPDATED = "NODE_UPDATED"
    NODE_REMOVED = "NODE_REMOVED"


class WorkspaceSyncService:
    """
    Keep HardwareNodes in sync with the hybrid physical layer.

    Responsibilities:
    - Auto add / remove boards
    - Restore saved positions / rotation / collapsed
    - Update pin states and heartbeat
    - Reconnect after restart (or show Waiting for hardware)
    - Persist into project.json / hardware store
    """

    def __init__(
        self,
        data_dir: Path | str = "data",
        *,
        factory: Optional[HardwareNodeFactory] = None,
        default_workspace_id: str = "default",
        event_bus: Any = None,
    ) -> None:
        self.data_dir = Path(data_dir)
        self.hardware_dir = self.data_dir / "lab_workspace" / "hardware_nodes"
        self.projects_dir = self.data_dir / "projects"
        self.hardware_dir.mkdir(parents=True, exist_ok=True)
        self.projects_dir.mkdir(parents=True, exist_ok=True)
        self.factory = factory or HardwareNodeFactory(default_workspace_id=default_workspace_id)
        self.default_workspace_id = default_workspace_id
        self.event_bus = event_bus
        self._lock = threading.RLock()
        self._nodes: dict[str, HardwareNode] = {}  # device_id -> node
        self._wires: list[dict[str, Any]] = []
        self._event_log: list[dict[str, Any]] = []
        self._ws_subscribers: list[WsBroadcast] = []
        self._load_default()

    # ---- WebSocket fan-out -------------------------------------------------

    def subscribe_ws(self, callback: WsBroadcast) -> None:
        self._ws_subscribers.append(callback)

    def unsubscribe_ws(self, callback: WsBroadcast) -> None:
        try:
            self._ws_subscribers.remove(callback)
        except ValueError:
            pass

    def _broadcast(self, event_type: str, payload: dict[str, Any]) -> None:
        message = {
            "type": event_type,
            "event": event_type,
            "payload": payload,
            "timestamp_ms": int(time.time() * 1000),
        }
        self._event_log.append(message)
        if len(self._event_log) > 500:
            self._event_log = self._event_log[-500:]
        for cb in list(self._ws_subscribers):
            try:
                cb(message)
            except Exception:  # noqa: BLE001 — never break sync on WS errors
                logger.exception("workspace hardware WS subscriber failed")
        if self.event_bus is not None:
            # Publish lifecycle events only — pin/heartbeat stay WS-local to avoid loops
            if event_type in (
                WorkspaceEventType.WORKSPACE_NODE_CREATED,
                WorkspaceEventType.WORKSPACE_NODE_REMOVED,
                WorkspaceEventType.NODE_CREATED,
                WorkspaceEventType.NODE_REMOVED,
            ):
                try:
                    from engine.events.event import Event

                    self.event_bus.publish(
                        Event.create(
                            event_type=event_type,
                            source="workspace-sync",
                            payload=payload,
                        )
                    )
                except Exception:  # noqa: BLE001
                    logger.exception("failed to publish workspace event on EventBus")

    # ---- Queries -----------------------------------------------------------

    def list_nodes(self, workspace_id: str = "") -> list[dict[str, Any]]:
        with self._lock:
            nodes = list(self._nodes.values())
            if workspace_id:
                nodes = [n for n in nodes if n.workspace_id in ("", workspace_id)]
            return [n.to_dict() for n in nodes]

    def get_node(self, device_id: str) -> Optional[dict[str, Any]]:
        with self._lock:
            node = self._nodes.get(device_id)
            return node.to_dict() if node else None

    def get_node_obj(self, device_id: str) -> Optional[HardwareNode]:
        with self._lock:
            return self._nodes.get(device_id)

    def events(self, limit: int = 100) -> list[dict[str, Any]]:
        return list(self._event_log[-limit:])

    # ---- Board lifecycle ---------------------------------------------------

    def upsert_from_device(
        self,
        device: dict[str, Any] | Any,
        *,
        workspace_id: str = "",
    ) -> HardwareNode:
        with self._lock:
            data = device if isinstance(device, dict) else (
                device.to_dict() if hasattr(device, "to_dict") else dict(device)
            )
            device_id = str(data.get("device_id") or data.get("port") or "")
            existing = self._nodes.get(device_id) if device_id else None
            position = existing.position if existing else None
            rotation = existing.rotation if existing else 0.0
            collapsed = existing.collapsed if existing else False
            ws_id = workspace_id or (existing.workspace_id if existing else self.default_workspace_id)

            node = self.factory.from_hybrid_device(data, workspace_id=ws_id, position=position)
            if existing:
                # Preserve live pin states where possible
                for name, pin in existing.pins.items():
                    if name in node.pins:
                        node.pins[name].state = pin.state
                node.rotation = rotation
                node.collapsed = collapsed
                node.node_id = existing.node_id
                created = False
            else:
                created = True

            node.status = HardwareNodeStatus.ONLINE
            node.available = True
            node.health = "ok"
            node.touch_heartbeat()
            self._nodes[node.device_id] = node
            self._persist(ws_id)

        payload = node.to_dict()
        if created:
            self._broadcast(WorkspaceEventType.BOARD_CONNECTED, payload)
            self._broadcast(WorkspaceEventType.NODE_CREATED, payload)
            self._broadcast(WorkspaceEventType.WORKSPACE_NODE_CREATED, payload)
        else:
            self._broadcast(WorkspaceEventType.NODE_UPDATED, payload)
            self._broadcast(WorkspaceEventType.TRANSPORT_STATUS, {
                "device_id": node.device_id,
                "transport": node.transport,
                "status": "connected",
                "endpoint": node.endpoint,
            })
            if node.firmware_version:
                self._broadcast(WorkspaceEventType.FIRMWARE_VERSION, {
                    "device_id": node.device_id,
                    "firmware_version": node.firmware_version,
                })
        return node

    def remove_device(self, device_id: str) -> Optional[HardwareNode]:
        with self._lock:
            node = self._nodes.get(device_id)
            if node is None:
                return None
            node.mark_offline()
            # Keep node in waiting state for reconnect UX (persistence)
            node.mark_waiting()
            ws_id = node.workspace_id
            self._persist(ws_id)
            payload = node.to_dict()

        self._broadcast(WorkspaceEventType.BOARD_DISCONNECTED, payload)
        self._broadcast(WorkspaceEventType.NODE_REMOVED, payload)
        self._broadcast(WorkspaceEventType.WORKSPACE_NODE_REMOVED, payload)
        return node

    def hard_remove(self, device_id: str) -> bool:
        with self._lock:
            node = self._nodes.pop(device_id, None)
            if node is None:
                return False
            self._persist(node.workspace_id)
            payload = node.to_dict()
        self._broadcast(WorkspaceEventType.NODE_REMOVED, payload)
        self._broadcast(WorkspaceEventType.WORKSPACE_NODE_REMOVED, payload)
        return True

    # ---- Pin / heartbeat ---------------------------------------------------

    def update_pin_state(
        self,
        device_id: str,
        pin: str,
        value: Any,
        *,
        voltage: Optional[float] = None,
        frequency_hz: Optional[float] = None,
        duty_cycle: Optional[float] = None,
        mode: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        with self._lock:
            node = self._nodes.get(device_id)
            if node is None:
                return None
            pin_def = node.update_pin_gpio(pin, int(value) if value in (0, 1, True, False) or isinstance(value, int) else 0)
            if pin_def is None:
                return None
            if voltage is not None:
                pin_def.state.voltage = float(voltage)
            if frequency_hz is not None:
                pin_def.state.frequency_hz = float(frequency_hz)
                pin_def.state.logic = PinLogicState.PWM
            if duty_cycle is not None:
                pin_def.state.duty_cycle = float(duty_cycle)
            if mode:
                # mode change event separate
                pass
            node.touch_heartbeat()
            self._persist(node.workspace_id)
            pin_payload = {
                "device_id": device_id,
                "pin": pin_def.name,
                "state": pin_def.state.to_dict(),
                "type": pin_def.pin_type,
            }

        self._broadcast(WorkspaceEventType.PIN_STATE_CHANGED, pin_payload)
        if mode:
            self._broadcast(WorkspaceEventType.PIN_MODE_CHANGED, {
                "device_id": device_id,
                "pin": pin,
                "mode": mode,
            })
        self._broadcast(WorkspaceEventType.HEARTBEAT, {
            "device_id": device_id,
            "heartbeat_ms": node.heartbeat_ms,
        })
        return pin_payload

    def touch_heartbeat(self, device_id: str) -> None:
        with self._lock:
            node = self._nodes.get(device_id)
            if node is None:
                return
            node.touch_heartbeat()
            payload = {"device_id": device_id, "heartbeat_ms": node.heartbeat_ms}
        self._broadcast(WorkspaceEventType.HEARTBEAT, payload)

    # ---- Position / UI state -----------------------------------------------

    def update_layout(
        self,
        device_id: str,
        *,
        position: Optional[dict[str, float]] = None,
        rotation: Optional[float] = None,
        collapsed: Optional[bool] = None,
    ) -> Optional[dict[str, Any]]:
        with self._lock:
            node = self._nodes.get(device_id)
            if node is None:
                return None
            if position is not None:
                node.position = {"x": float(position.get("x", 0)), "y": float(position.get("y", 0))}
            if rotation is not None:
                node.rotation = float(rotation)
            if collapsed is not None:
                node.collapsed = bool(collapsed)
            self._persist(node.workspace_id)
            return node.to_dict()

    def set_wires(self, wires: list[dict[str, Any]], workspace_id: str = "") -> None:
        with self._lock:
            self._wires = list(wires)
            self._persist(workspace_id or self.default_workspace_id)

    # ---- Reconnect ---------------------------------------------------------

    def reconnect(self, device_id: str = "", *, hybrid_devices: Optional[list[dict[str, Any]]] = None) -> dict[str, Any]:
        """
        Attempt to bring waiting nodes online using currently connected hybrid devices.
        Missing hardware stays in Waiting for hardware.
        """
        hybrid_devices = hybrid_devices or []
        by_id = {str(d.get("device_id") or ""): d for d in hybrid_devices}
        by_endpoint = {str(d.get("endpoint") or d.get("port") or ""): d for d in hybrid_devices}

        reconnected: list[str] = []
        waiting: list[str] = []

        with self._lock:
            targets = [self._nodes[device_id]] if device_id and device_id in self._nodes else list(self._nodes.values())
            for node in targets:
                match = by_id.get(node.device_id) or by_endpoint.get(node.endpoint)
                if match:
                    node.status = HardwareNodeStatus.ONLINE
                    node.available = True
                    node.health = "ok"
                    node.endpoint = str(match.get("endpoint") or match.get("port") or node.endpoint)
                    node.transport = str(match.get("transport") or node.transport)
                    node.firmware_version = str(match.get("firmware_version") or node.firmware_version)
                    node.touch_heartbeat()
                    reconnected.append(node.device_id)
                else:
                    node.mark_waiting()
                    waiting.append(node.device_id)
            self._persist(self.default_workspace_id)

        for did in reconnected:
            n = self.get_node(did)
            if n:
                self._broadcast(WorkspaceEventType.BOARD_CONNECTED, n)
                self._broadcast(WorkspaceEventType.NODE_UPDATED, n)
        for did in waiting:
            n = self.get_node(did)
            if n:
                self._broadcast(WorkspaceEventType.TRANSPORT_STATUS, {
                    "device_id": did,
                    "status": "waiting",
                    "message": "Waiting for hardware",
                })

        return {
            "reconnected": reconnected,
            "waiting": waiting,
            "nodes": self.list_nodes(),
        }

    def disconnect_node(self, device_id: str) -> dict[str, Any]:
        node = self.remove_device(device_id)
        return {"ok": node is not None, "device_id": device_id, "node": node.to_dict() if node else None}

    # ---- Persistence -------------------------------------------------------

    def _store_path(self, workspace_id: str) -> Path:
        safe = (workspace_id or self.default_workspace_id).replace("/", "_")
        return self.hardware_dir / f"{safe}.json"

    def _project_path(self, project_id: str) -> Path:
        return self.projects_dir / project_id / "project.json"

    def _persist(self, workspace_id: str) -> None:
        payload = {
            "workspace_id": workspace_id or self.default_workspace_id,
            "nodes": [n.to_dict() for n in self._nodes.values()],
            "wires": list(self._wires),
            "updated_at_ms": int(time.time() * 1000),
        }
        path = self._store_path(workspace_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

        # Also write/merge project.json when workspace maps to a project id
        project_id = workspace_id or self.default_workspace_id
        if project_id and project_id != "default":
            self.save_project_hardware(project_id, payload)

    def save_project_hardware(self, project_id: str, snapshot: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        """Extend project.json with workspace hardware twin state."""
        path = self._project_path(project_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        existing: dict[str, Any] = {}
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                existing = {}
        snap = snapshot or {
            "workspace_id": project_id,
            "nodes": [n.to_dict() for n in self._nodes.values()],
            "wires": list(self._wires),
        }
        hardware_section = {
            "nodes": [
                {
                    "device_id": n.get("device_id"),
                    "board_type": n.get("board_type"),
                    "position": n.get("position"),
                    "rotation": n.get("rotation"),
                    "collapsed": n.get("collapsed"),
                    "transport": n.get("transport"),
                    "endpoint": n.get("endpoint"),
                    "hardware_profile": n.get("board_type"),
                    "pin_mappings": {
                        p.get("name"): p.get("number") for p in (n.get("pins") or []) if isinstance(p, dict)
                    },
                    "manufacturer": n.get("manufacturer"),
                    "firmware_version": n.get("firmware_version"),
                }
                for n in snap.get("nodes") or []
            ],
            "wires": snap.get("wires") or [],
        }
        existing["hardware"] = hardware_section
        existing.setdefault("id", project_id)
        path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
        return existing

    def load_project(self, project_id: str, *, hybrid_devices: Optional[list[dict[str, Any]]] = None) -> dict[str, Any]:
        """Load project.json hardware section and reconcile with live devices."""
        path = self._project_path(project_id)
        if not path.exists():
            # Fallback to hardware store
            store = self._store_path(project_id)
            if store.exists():
                data = json.loads(store.read_text(encoding="utf-8"))
                self._hydrate(data.get("nodes") or [], wires=data.get("wires") or [])
                return self.reconnect(hybrid_devices=hybrid_devices)
            return {"reconnected": [], "waiting": [], "nodes": []}

        data = json.loads(path.read_text(encoding="utf-8"))
        hw = data.get("hardware") or {}
        nodes_raw = hw.get("nodes") or []
        hydrated: list[dict[str, Any]] = []
        for entry in nodes_raw:
            board_type = str(entry.get("board_type") or "unknown")
            device_id = str(entry.get("device_id") or f"pending_{board_type}")
            node = self.factory.from_waiting(
                device_id=device_id,
                board_type=board_type,
                workspace_id=project_id,
                endpoint=str(entry.get("endpoint") or ""),
                transport=str(entry.get("transport") or "serial"),
                manufacturer=str(entry.get("manufacturer") or ""),
                position=entry.get("position"),
            )
            node.rotation = float(entry.get("rotation") or 0)
            node.collapsed = bool(entry.get("collapsed", False))
            hydrated.append(node.to_dict())
        self._hydrate(hydrated, wires=hw.get("wires") or [])
        return self.reconnect(hybrid_devices=hybrid_devices)

    def _hydrate(self, nodes: list[dict[str, Any]], *, wires: Optional[list[dict[str, Any]]] = None) -> None:
        with self._lock:
            for raw in nodes:
                try:
                    node = HardwareNode.from_dict(raw)
                    if not node.pins:
                        from .board_renderer import get_pin_layout

                        node.pins = {p.name: p for p in get_pin_layout(node.board_type)}
                    self._nodes[node.device_id] = node
                except Exception:  # noqa: BLE001
                    logger.exception("failed to hydrate hardware node")
            if wires is not None:
                self._wires = list(wires)

    def _load_default(self) -> None:
        path = self._store_path(self.default_workspace_id)
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                self._hydrate(data.get("nodes") or [], wires=data.get("wires") or [])
                # After restart, mark all as waiting until reconnect
                for node in self._nodes.values():
                    if node.status == HardwareNodeStatus.ONLINE:
                        node.mark_waiting()
            except Exception:  # noqa: BLE001
                logger.exception("failed to load hardware nodes store")
```

## `engine\hardware_nodes\discovery_listener.py`

```python
"""Listen for hybrid / discovery board events and sync workspace HardwareNodes."""

from __future__ import annotations

import logging
from typing import Any, Optional

from engine.events.event import Event
from engine.events.subscriber import EventSubscriber
from engine.hybrid.events import HybridEventType

from .workspace_sync import WorkspaceEventType, WorkspaceSyncService

logger = logging.getLogger(__name__)


class DiscoveryListener(EventSubscriber):
    """
    Whenever HybridRegistry / HybridRouter publishes BOARD / PHYSICAL connect events,
    create a HardwareNode and emit WORKSPACE_NODE_CREATED.

    On disconnect → WORKSPACE_NODE_REMOVED (node marked waiting).
    On GPIO_STATE → live pin updates.
    """

    CONNECT_EVENTS = frozenset(
        {
            HybridEventType.PHYSICAL_DEVICE_CONNECTED,
            "BOARD_CONNECTED",  # external alias only when source is not workspace-sync
        }
    )
    DISCONNECT_EVENTS = frozenset(
        {
            HybridEventType.PHYSICAL_DEVICE_DISCONNECTED,
            "BOARD_DISCONNECTED",
        }
    )
    # Only hybrid router GPIO — never workspace-sync echoes (avoids EventBus loops)
    GPIO_EVENTS = frozenset(
        {
            HybridEventType.GPIO_STATE,
            HybridEventType.GPIO_WRITE,
        }
    )

    def __init__(
        self,
        sync: WorkspaceSyncService,
        *,
        workspace_id: str = "",
        event_bus: Any = None,
    ) -> None:
        self.sync = sync
        self.workspace_id = workspace_id
        self.event_bus = event_bus
        if event_bus is not None:
            event_bus.register_subscriber(self)

    def handle_event(self, event: Event) -> None:
        # Ignore events we ourselves published via WorkspaceSyncService
        if str(event.source or "") == "workspace-sync":
            return

        et = str(event.event_type or "")
        payload = dict(event.payload or {})

        if et in self.CONNECT_EVENTS:
            device = payload if payload.get("device_id") or payload.get("board_type") else {
                **payload,
                "device_id": payload.get("device_id") or event.source,
            }
            try:
                self.sync.upsert_from_device(device, workspace_id=self.workspace_id)
            except Exception:  # noqa: BLE001
                logger.exception("DiscoveryListener failed to create HardwareNode")
            return

        if et in self.DISCONNECT_EVENTS:
            device_id = str(payload.get("device_id") or event.source or "")
            if device_id:
                self.sync.remove_device(device_id)
            return

        if et in self.GPIO_EVENTS:
            device_id = str(payload.get("device_id") or event.source or "")
            pin = str(payload.get("pin") or payload.get("pin_id") or "")
            if not device_id or not pin:
                return
            value = payload.get("value", 0)
            self.sync.update_pin_state(
                device_id,
                pin,
                value,
                voltage=payload.get("voltage"),
                frequency_hz=payload.get("frequency_hz"),
                duty_cycle=payload.get("duty_cycle"),
                mode=payload.get("mode"),
            )
            return

        if et in ("HEARTBEAT", WorkspaceEventType.HEARTBEAT):
            device_id = str(payload.get("device_id") or event.source or "")
            if device_id:
                self.sync.touch_heartbeat(device_id)
```

## `engine\lab_workspace\models.py`

```python
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
```

## `engine\lab_workspace\service.py`

```python
"""Engineering laboratory workspace orchestrator."""

from __future__ import annotations

import math
import time
import uuid
from typing import Any, Optional

from engine.events.event_bus import EventBus

from .catalog import get_component, list_categories, search_catalog
from .history import HistoryStack
from .models import (
    CanvasNode,
    CanvasWire,
    DeviceMode,
    EngineeringWorkspace,
    SimulationSpeed,
    WorkspaceSnapshot,
    WorkspaceStatus,
)
from .storage import LabWorkspaceStorage
from .wire import auto_route_points, validate_wire_with_peers


class LabWorkspaceService:
    """Enterprise engineering workspace — canvas, simulation, monitors."""

    def __init__(
        self,
        *,
        storage: Optional[LabWorkspaceStorage] = None,
        event_bus: Optional[EventBus] = None,
    ) -> None:
        self.storage = storage or LabWorkspaceStorage()
        self.event_bus = event_bus or EventBus()
        self._workspaces: dict[str, EngineeringWorkspace] = {}
        self._history: dict[str, HistoryStack] = {}
        self._subscribers: dict[str, list] = {}
        self._load_persisted()

    # ---- catalog ----------------------------------------------------------

    def catalog(
        self,
        *,
        q: str = "",
        category: str | None = None,
        interface: str | None = None,
        interfaces: list[str] | None = None,
        voltage: float | None = None,
        voltages: list[float] | None = None,
        controller_id: str | None = None,
    ) -> dict[str, Any]:
        from .catalog import CATEGORY_LABELS, explorer_tree

        return {
            "categories": list_categories(),
            "labels": CATEGORY_LABELS,
            "tree": explorer_tree(),
            "items": search_catalog(
                q,
                category,
                interface=interface,
                interfaces=interfaces,
                voltage=voltage,
                voltages=voltages,
                controller_id=controller_id,
            ),
        }

    # ---- lifecycle --------------------------------------------------------

    def create(self, *, name: str, project_id: str = "") -> dict[str, Any]:
        ws = EngineeringWorkspace.create(name=name, project_id=project_id)
        self._workspaces[ws.workspace_id] = ws
        self._history[ws.workspace_id] = HistoryStack()
        self._log(ws, "console", f"Workspace created: {ws.name}")
        self.storage.save(ws.workspace_id, ws.get_state())
        return ws.to_dict()

    def get(self, workspace_id: str) -> dict[str, Any]:
        return self._require(workspace_id).to_dict()

    def get_state(self, workspace_id: str) -> dict[str, Any]:
        return self._require(workspace_id).get_state()

    def list_workspaces(self) -> list[dict[str, Any]]:
        return [w.to_dict() for w in self._workspaces.values()]

    def connect(self, workspace_id: str) -> dict[str, Any]:
        ws = self._require(workspace_id)
        ws.status = WorkspaceStatus.CONNECTED
        ws.touch()
        self._log(ws, "console", "Connected to workspace runtime")
        self._persist(ws)
        return ws.get_state()

    def disconnect(self, workspace_id: str) -> dict[str, Any]:
        ws = self._require(workspace_id)
        if ws.status == WorkspaceStatus.RUNNING:
            ws.status = WorkspaceStatus.PAUSED
        else:
            ws.status = WorkspaceStatus.STOPPED
        ws.touch()
        self._log(ws, "console", "Disconnected from workspace runtime")
        self._persist(ws)
        return ws.get_state()

    # ---- canvas mutations -------------------------------------------------

    def add_node(
        self,
        workspace_id: str,
        *,
        component_id: str,
        position: dict[str, float],
        device_mode: str = "virtual",
        physical_port: str = "",
        physical_device_id: str = "",
        available: bool | None = None,
        label: str = "",
    ) -> dict[str, Any]:
        ws = self._require(workspace_id)
        self._push_history(ws)
        spec = get_component(component_id)
        if spec is None:
            raise KeyError(f"component not found: {component_id}")
        node_id = f"N{uuid.uuid4().hex[:8].upper()}"
        properties = dict(spec.get("params") or {})
        if physical_port:
            properties["physical_port"] = physical_port
        if physical_device_id:
            properties["physical_device_id"] = physical_device_id
        if spec.get("pins") and isinstance(spec.get("pins"), list):
            properties["catalog_pins"] = list(spec["pins"])
        if spec.get("simulation"):
            properties["simulation"] = dict(spec["simulation"])
        if spec.get("voltage"):
            properties["voltage"] = dict(spec["voltage"])
        if spec.get("compatible_controllers"):
            properties["compatible_controllers"] = list(spec["compatible_controllers"])
        is_physical = device_mode == DeviceMode.PHYSICAL.value
        node = CanvasNode(
            node_id=node_id,
            component_id=component_id,
            label=label or str(spec["name"]),
            category=str(spec["category"]),
            position=position,
            device_mode=DeviceMode(device_mode),
            properties=properties,
            live_state={},
            available=available if available is not None else not is_physical,
        )
        if is_physical and (physical_port or physical_device_id):
            node.available = True
        ws.nodes[node_id] = node
        ws.touch()
        self._log(ws, "console", f"Added {spec['name']} ({device_mode})")
        self._persist(ws)
        return node.to_dict()

    def update_node(self, workspace_id: str, node_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        ws = self._require(workspace_id)
        node = ws.nodes.get(node_id)
        if node is None:
            raise KeyError(f"node not found: {node_id}")
        self._push_history(ws)
        if "position" in patch:
            node.position = dict(patch["position"])
        if "device_mode" in patch:
            node.device_mode = DeviceMode(str(patch["device_mode"]))
            node.available = node.device_mode != DeviceMode.PHYSICAL or bool(patch.get("available", False))
        if "properties" in patch and isinstance(patch["properties"], dict):
            node.properties.update(patch["properties"])
        if "label" in patch:
            node.label = str(patch["label"])
        if "pin_map" in patch and isinstance(patch["pin_map"], dict):
            node.pin_map = dict(patch["pin_map"])
        if "available" in patch:
            node.available = bool(patch["available"])
        if "physical_port" in patch:
            node.properties["physical_port"] = str(patch["physical_port"])
            if node.device_mode == DeviceMode.PHYSICAL:
                node.available = True
        if "physical_device_id" in patch:
            node.properties["physical_device_id"] = str(patch["physical_device_id"])
            if node.device_mode == DeviceMode.PHYSICAL:
                node.available = True
        ws.touch()
        self._persist(ws)
        return node.to_dict()

    def delete_nodes(self, workspace_id: str, node_ids: list[str]) -> dict[str, Any]:
        ws = self._require(workspace_id)
        self._push_history(ws)
        for nid in node_ids:
            ws.nodes.pop(nid, None)
            for wid, wire in list(ws.wires.items()):
                if wire.source == nid or wire.target == nid:
                    ws.wires.pop(wid, None)
        ws.touch()
        self._persist(ws)
        return ws.to_react_flow()

    def duplicate_nodes(self, workspace_id: str, node_ids: list[str]) -> list[dict[str, Any]]:
        ws = self._require(workspace_id)
        self._push_history(ws)
        created: list[dict[str, Any]] = []
        for nid in node_ids:
            src = ws.nodes.get(nid)
            if src is None:
                continue
            new_id = f"N{uuid.uuid4().hex[:8].upper()}"
            clone = CanvasNode(
                node_id=new_id,
                component_id=src.component_id,
                label=src.label,
                category=src.category,
                position={"x": src.position["x"] + 40, "y": src.position["y"] + 40},
                device_mode=src.device_mode,
                pin_map=dict(src.pin_map),
                properties=dict(src.properties),
                live_state={},
                available=src.available,
            )
            ws.nodes[new_id] = clone
            created.append(clone.to_dict())
        ws.touch()
        self._persist(ws)
        return created

    def add_wire(
        self,
        workspace_id: str,
        *,
        source: str,
        target: str,
        source_handle: str = "out",
        target_handle: str = "in",
        protocol: str = "digital",
        voltage_v: float = 3.3,
    ) -> dict[str, Any]:
        ws = self._require(workspace_id)
        self._push_history(ws)
        wire_id = f"W{uuid.uuid4().hex[:8].upper()}"
        wire = CanvasWire(
            wire_id=wire_id,
            source=source,
            source_handle=source_handle,
            target=target,
            target_handle=target_handle,
            protocol=protocol,
            voltage_v=voltage_v,
        )
        wire = validate_wire_with_peers(wire, ws.nodes, ws.wires)
        ws.wires[wire_id] = wire
        route = auto_route_points(
            ws.nodes[source].position if source in ws.nodes else {"x": 0, "y": 0},
            ws.nodes[target].position if target in ws.nodes else {"x": 0, "y": 0},
        )
        ws.touch()
        self._log(ws, "console", f"Wire {wire.label} ({'ok' if wire.valid else 'invalid'})")
        self._persist(ws)
        data = wire.to_dict()
        data["route"] = route
        return data

    def delete_wires(self, workspace_id: str, wire_ids: list[str]) -> dict[str, Any]:
        ws = self._require(workspace_id)
        self._push_history(ws)
        for wid in wire_ids:
            ws.wires.pop(wid, None)
        ws.touch()
        self._persist(ws)
        return ws.to_react_flow()

    def undo(self, workspace_id: str) -> dict[str, Any]:
        ws = self._require(workspace_id)
        hist = self._history[workspace_id]
        snap = hist.undo(ws.snapshot())
        if snap is None:
            return ws.get_state()
        self._restore_snapshot(ws, snap)
        return ws.get_state()

    def redo(self, workspace_id: str) -> dict[str, Any]:
        ws = self._require(workspace_id)
        hist = self._history[workspace_id]
        snap = hist.redo(ws.snapshot())
        if snap is None:
            return ws.get_state()
        self._restore_snapshot(ws, snap)
        return ws.get_state()

    # ---- simulation controls ----------------------------------------------

    def run(self, workspace_id: str, *, speed: str = "1x") -> dict[str, Any]:
        ws = self._require(workspace_id)
        ws.status = WorkspaceStatus.RUNNING
        ws.speed = SimulationSpeed(speed)
        ws.touch()
        self._log(ws, "console", f"Simulation running @ {speed}")
        self._log_event(ws, "SIMULATION_STARTED", {"speed": speed})
        self._persist(ws)
        return ws.get_state()

    def pause(self, workspace_id: str) -> dict[str, Any]:
        ws = self._require(workspace_id)
        ws.status = WorkspaceStatus.PAUSED
        ws.touch()
        self._log(ws, "console", "Simulation paused")
        self._persist(ws)
        return ws.get_state()

    def reset(self, workspace_id: str) -> dict[str, Any]:
        ws = self._require(workspace_id)
        ws.status = WorkspaceStatus.CONNECTED
        ws.sim_time_ms = 0
        ws.tick_count = 0
        ws.events_per_sec = 0.0
        ws.fps = 0.0
        for node in ws.nodes.values():
            node.live_state = {}
        ws.gpio_samples.clear()
        ws.adc_samples.clear()
        ws.touch()
        self._log(ws, "console", "Simulation reset")
        self._persist(ws)
        return ws.get_state()

    def step(self, workspace_id: str, delta_ms: int = 100) -> dict[str, Any]:
        ws = self._require(workspace_id)
        if ws.status not in (WorkspaceStatus.RUNNING, WorkspaceStatus.PAUSED, WorkspaceStatus.CONNECTED):
            raise RuntimeError("workspace not ready for stepping")
        if ws.status == WorkspaceStatus.CONNECTED:
            ws.status = WorkspaceStatus.RUNNING

        multiplier = {"1x": 1, "2x": 2, "5x": 5, "10x": 10, "100x": 100}.get(ws.speed.value, 1)
        advance = delta_ms * multiplier
        ws.sim_time_ms += advance
        ws.tick_count += 1
        t = ws.sim_time_ms / 1000.0

        events = 0
        for node in ws.nodes.values():
            live = self._simulate_node(node, t)
            if live:
                node.live_state = live
                events += 1
                self._log_event(
                    ws,
                    "SENSOR_DATA" if node.category == "sensors" else "ACTUATOR_UPDATE",
                    {"node_id": node.node_id, "state": live},
                )
                if "gpio" in live or "digital" in live:
                    ws.gpio_samples.append(
                        {"t": ws.sim_time_ms, "node_id": node.node_id, "value": live.get("gpio", live.get("digital", 0))}
                    )
                if "adc" in live or "voltage" in live:
                    ws.adc_samples.append(
                        {
                            "t": ws.sim_time_ms,
                            "node_id": node.node_id,
                            "value": live.get("adc", live.get("voltage", 0)),
                        }
                    )

        ws.events_per_sec = round(events / max(advance / 1000.0, 0.001), 2)
        ws.fps = round(1000.0 / max(delta_ms, 1), 1)
        self._log(ws, "serial", f"[{ws.sim_time_ms}ms] tick={ws.tick_count} events={events}")
        ws.touch()
        self._persist(ws)
        return ws.get_state()

    def send_serial(self, workspace_id: str, line: str) -> dict[str, Any]:
        ws = self._require(workspace_id)
        self._log(ws, "serial", f"> {line}", direction="tx")
        self._log(ws, "serial", f"< ACK {line[:40]}", direction="rx")
        return {"ok": True, "serial": ws.serial_lines[-20:]}

    # ---- helpers ----------------------------------------------------------

    def _simulate_node(self, node: CanvasNode, t: float) -> dict[str, Any]:
        cid = node.component_id
        if cid in ("dht11", "dht22", "am2302", "ds18b20"):
            return {
                "temperature_c": round(22 + 3 * math.sin(t / 8), 1 if cid == "dht11" else 2),
                "humidity_pct": round(55 + 8 * math.cos(t / 12), 1),
                "SIGNAL_CHANGED": True,
            }
        if cid == "hc-sr04":
            return {"distance_cm": round(30 + 20 * abs(math.sin(t / 5)), 1)}
        if cid == "pir":
            return {"motion_detected": (int(t) // 3) % 2 == 0, "gpio": 1 if (int(t) // 3) % 2 == 0 else 0, "motion": (int(t) // 3) % 2 == 0}
        if cid == "soil-moisture":
            m = max(0, min(100, 60 - t * 0.2))
            return {"moisture_pct": round(m, 1), "adc": int(m * 10.23), "voltage": round(m / 100 * 3.3, 2)}
        if cid == "led" or cid == "rgb-led":
            on = bool(node.live_state.get("on", False))
            brightness = int(node.live_state.get("brightness", 255 if on else 0))
            pwm = float(node.live_state.get("pwm", 1.0 if on else 0.0))
            if not on and pwm > 0.05:
                on = True
                brightness = max(brightness, int(pwm * 255))
            return {
                "on": on,
                "brightness": brightness,
                "pwm": pwm,
                "gpio": 1 if on else 0,
                "SIGNAL_CHANGED": True,
            }
        if cid == "relay":
            closed = bool(node.live_state.get("closed", node.live_state.get("active", False)))
            return {"closed": closed, "active": closed, "gpio": 1 if closed else 0, "SIGNAL_CHANGED": True}
        if cid == "servo":
            if "angle_deg" in node.live_state or "angle" in node.live_state:
                angle = int(node.live_state.get("angle_deg", node.live_state.get("angle", 90)))
            else:
                angle = int(90 + 45 * math.sin(t / 3))
            return {"angle_deg": angle, "angle": angle, "SIGNAL_CHANGED": True}
        if cid in ("dc-motor", "stepper-motor", "stepper"):
            speed = float(node.live_state.get("speed", 0.5 + 0.5 * abs(math.sin(t / 2))))
            return {"speed": speed, "rpm": int(speed * 120), "rotating": speed > 0.05, "SIGNAL_CHANGED": True}
        if cid in ("mq2", "ldr", "gas-sensor", "water-level"):
            return {"adc": int(512 + 200 * math.sin(t)), "voltage": round(1.65 + 0.6 * math.sin(t), 2)}
        if node.category in {"arduino", "esp32", "stm32", "pico"}:
            return {"gpio": {"D2": int((t * 2) % 2), "D4": 1, "D13": 1}, "uptime_ms": int(t * 1000), "power_on": True}
        return {"active": True}

    def _require(self, workspace_id: str) -> EngineeringWorkspace:
        ws = self._workspaces.get(workspace_id)
        if ws is not None:
            return ws
        stored = self.storage.load(workspace_id)
        if stored is None:
            raise KeyError(f"workspace not found: {workspace_id}")
        ws = EngineeringWorkspace.from_state(stored)
        self._workspaces[workspace_id] = ws
        self._history.setdefault(workspace_id, HistoryStack())
        return ws

    def _load_persisted(self) -> None:
        for workspace_id in self.storage.list_ids():
            if workspace_id in self._workspaces:
                continue
            stored = self.storage.load(workspace_id)
            if stored is None:
                continue
            try:
                self._workspaces[workspace_id] = EngineeringWorkspace.from_state(stored)
                self._history[workspace_id] = HistoryStack()
            except Exception:
                continue

    def _push_history(self, ws: EngineeringWorkspace) -> None:
        self._history.setdefault(ws.workspace_id, HistoryStack()).push(ws.snapshot())

    def _restore_snapshot(self, ws: EngineeringWorkspace, snap: WorkspaceSnapshot) -> None:
        ws.nodes.clear()
        ws.wires.clear()
        for raw in snap.nodes:
            ws.nodes[raw["id"]] = CanvasNode(
                node_id=raw["id"],
                component_id=raw["component_id"],
                label=raw["label"],
                category=raw["category"],
                position=dict(raw["position"]),
                device_mode=DeviceMode(raw.get("device_mode", "virtual")),
                pin_map=dict(raw.get("pin_map") or {}),
                properties=dict(raw.get("properties") or {}),
                live_state=dict(raw.get("live_state") or {}),
                available=bool(raw.get("available", True)),
            )
        for raw in snap.wires:
            ws.wires[raw["id"]] = CanvasWire(
                wire_id=raw["id"],
                source=raw["source"],
                source_handle=raw.get("sourceHandle", "out"),
                target=raw["target"],
                target_handle=raw.get("targetHandle", "in"),
                color=raw.get("color", "#2563eb"),
                protocol=raw.get("protocol", "digital"),
                voltage_v=float(raw.get("voltage_v", 3.3)),
                label=raw.get("label", ""),
                valid=bool(raw.get("valid", True)),
                issues=list(raw.get("issues") or []),
            )
        ws.touch()
        self._persist(ws)

    def _log(self, ws: EngineeringWorkspace, channel: str, message: str, **extra: Any) -> None:
        entry = {
            "timestamp_ms": int(time.time() * 1000),
            "sim_time_ms": ws.sim_time_ms,
            "message": message,
            **extra,
        }
        if channel == "serial":
            ws.serial_lines.append(entry)
            ws.serial_lines = ws.serial_lines[-500:]
        else:
            ws.console_lines.append(entry)
            ws.console_lines = ws.console_lines[-500:]

    def _log_event(self, ws: EngineeringWorkspace, event_type: str, payload: dict[str, Any]) -> None:
        ws.event_log.append(
            {
                "timestamp_ms": int(time.time() * 1000),
                "sim_time_ms": ws.sim_time_ms,
                "type": event_type,
                "source": ws.workspace_id,
                "destination": "workspace",
                "payload": payload,
                "status": "COMPLETED",
            }
        )
        ws.event_log = ws.event_log[-500:]

    def _persist(self, ws: EngineeringWorkspace) -> None:
        self.storage.save(ws.workspace_id, ws.get_state())
```

## `engine\lab_workspace\storage.py`

```python
"""Persistence for engineering laboratory workspaces."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional


class LabWorkspaceStorage:
    """File-based persistence under ``data/lab_workspace/``."""

    def __init__(self, base_dir: Path | str = "data") -> None:
        self.base_dir = Path(base_dir) / "lab_workspace"
        self.sessions_dir = self.base_dir / "sessions"

    def _ensure(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)

    def save(self, workspace_id: str, data: dict[str, Any]) -> Path:
        path = self.sessions_dir / f"{workspace_id}.json"
        self._ensure(path)
        with path.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, sort_keys=True)
            fh.write("\n")
        return path

    def load(self, workspace_id: str) -> Optional[dict[str, Any]]:
        path = self.sessions_dir / f"{workspace_id}.json"
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)

    def list_ids(self) -> list[str]:
        if not self.sessions_dir.exists():
            return []
        return sorted(p.stem for p in self.sessions_dir.glob("*.json"))
```

## `engine\discovery\service.py`

```python
"""Background hardware discovery with hot-plug detection."""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Optional

from engine.communication.serial_adapter import SerialAdapter, SerialAdapterError
from engine.devices.base.lifecycle import DeviceLifecycleEvent
from engine.devices.device_manager import DeviceManager
from engine.events.event import Event
from engine.events.event_bus import EventBus
from engine.events.dashboard_publisher import DashboardEventPublisher

from .handshake import perform_handshake
from .identify import identify_board
from .models import DiscoveredDevice, DiscoveryStatus
from .scanner import PortInfo, default_port_lister

logger = logging.getLogger("hhip.discovery")

TransportFactory = Callable[[str], object]
ChangeCallback = Callable[[list[DiscoveredDevice]], None]


class HardwareDiscoveryService:
    """Scan USB serial ports, identify boards, and perform HHIP handshake."""

    def __init__(
        self,
        *,
        event_bus: Optional[EventBus] = None,
        device_manager: Optional[DeviceManager] = None,
        dashboard_publisher: Optional[DashboardEventPublisher] = None,
        scan_interval_s: float = 2.0,
        port_lister: Optional[Callable[[], list[PortInfo]]] = None,
        transport_factory: Optional[TransportFactory] = None,
        on_change: Optional[ChangeCallback] = None,
    ) -> None:
        self._event_bus = event_bus or EventBus()
        self._device_manager = device_manager or DeviceManager()
        self._device_manager.bind_event_bus(self._event_bus)
        self._dashboard = dashboard_publisher
        self._scan_interval_s = scan_interval_s
        self._port_lister = port_lister or default_port_lister
        self._transport_factory = transport_factory or (
            lambda port: SerialAdapter(port, timeout=0.3)
        )
        self._on_change = on_change
        self._lock = threading.RLock()
        self._devices: dict[str, DiscoveredDevice] = {}
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._running = False

    @property
    def event_bus(self) -> EventBus:
        return self._event_bus

    @property
    def device_manager(self) -> DeviceManager:
        return self._device_manager

    def start(self) -> None:
        if self._running:
            return
        self._stop.clear()
        self._running = True
        self._thread = threading.Thread(target=self._scan_loop, name="hhip-discovery", daemon=True)
        self._thread.start()
        logger.info("[DISCOVERY] Started (interval=%ss)", self._scan_interval_s)

    def stop(self) -> None:
        self._running = False
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=self._scan_interval_s + 2)
        self._thread = None
        logger.info("[DISCOVERY] Stopped")

    def scan_once(self) -> list[DiscoveredDevice]:
        """Run a single discovery pass (thread-safe)."""
        with self._lock:
            return self._scan_locked()

    def list_devices(self) -> list[DiscoveredDevice]:
        with self._lock:
            return list(self._devices.values())

    def get_device(self, port: str) -> Optional[DiscoveredDevice]:
        with self._lock:
            return self._devices.get(port)

    def _scan_loop(self) -> None:
        while self._running and not self._stop.is_set():
            try:
                self.scan_once()
            except Exception:
                logger.exception("[DISCOVERY] Scan pass failed")
            self._stop.wait(self._scan_interval_s)

    def _scan_locked(self) -> list[DiscoveredDevice]:
        now_ms = int(time.time() * 1000)
        try:
            ports = self._port_lister()
        except Exception as exc:  # noqa: BLE001
            logger.exception("[DISCOVERY] Port list failed: %s", exc)
            ports = []
        seen: set[str] = set()

        for info in ports:
            seen.add(info.device)
            board_type, label = identify_board(
                vid=info.vid,
                pid=info.pid,
                description=info.description,
                manufacturer=info.manufacturer,
            )
            existing = self._devices.get(info.device)
            if existing is None:
                device = DiscoveredDevice.from_port_info(
                    info.device,
                    vid=info.vid,
                    pid=info.pid,
                    manufacturer=info.manufacturer,
                    description=info.description,
                    serial_number=info.serial_number,
                    board_type=board_type,
                    label=label,
                    last_seen_ms=now_ms,
                )
                self._devices[info.device] = device
                self._probe_device(device, is_new=True)
            else:
                prev_status = existing.status
                existing.last_seen_ms = now_ms
                existing.vid = info.vid
                existing.pid = info.pid
                existing.manufacturer = info.manufacturer
                existing.description = info.description
                existing.serial_number = info.serial_number
                if prev_status == DiscoveryStatus.DISCONNECTED:
                    existing.board_type = board_type
                    existing.label = label
                    existing.status = DiscoveryStatus.CONNECTING
                    existing.error = None
                    self._probe_device(existing, is_new=True)
                elif existing.board_type == "unknown-serial" and board_type != "unknown-serial":
                    existing.board_type = board_type
                    existing.label = label

        # Hot-unplug
        for port, device in list(self._devices.items()):
            if port not in seen:
                if device.status != DiscoveryStatus.DISCONNECTED:
                    self._mark_disconnected(device, reason="Port removed")

        devices = list(self._devices.values())
        self._notify_change(devices)
        return devices

    def _probe_device(self, device: DiscoveredDevice, *, is_new: bool = False) -> None:
        device.status = DiscoveryStatus.CONNECTING
        device.error = None
        transport = self._transport_factory(device.port)
        try:
            transport.connect()  # type: ignore[attr-defined]
        except (SerialAdapterError, OSError, Exception) as exc:  # noqa: BLE001
            msg = str(exc).lower()
            if "access" in msg or "busy" in msg or "permission" in msg:
                device.status = DiscoveryStatus.BUSY
            else:
                device.status = DiscoveryStatus.ERROR
            device.error = str(exc)
            return

        try:
            result = perform_handshake(transport)  # type: ignore[arg-type]
        finally:
            try:
                transport.disconnect()  # type: ignore[attr-defined]
            except Exception:
                pass

        if result.success and result.hhip_firmware:
            device.status = DiscoveryStatus.CONNECTED
            device.hhip_firmware = True
            device.device_id = result.device_id
            device.firmware_version = result.firmware_version
            device.capabilities = list(result.capabilities)
            if result.device_type and result.device_type != "unknown":
                device.board_type = _normalize_board_type(result.device_type)
                device.label = _label_for_board(device.board_type)
            device.error = None
            self._register_physical(device)
            if is_new:
                self._publish_connected(device)
        elif device.board_type != "unknown-serial":
            device.status = DiscoveryStatus.CONNECTED
            device.hhip_firmware = False
            device.error = result.error or "HHIP firmware not detected"
            if is_new:
                self._publish_connected(device, partial=True)
        else:
            device.status = DiscoveryStatus.CONNECTED
            device.hhip_firmware = False
            device.label = "Unknown Serial Device"
            device.error = result.error or "Install or upload HHIP firmware"
            if is_new:
                self._publish_connected(device, partial=True)

    def _mark_disconnected(self, device: DiscoveredDevice, *, reason: str = "") -> None:
        previous_id = device.device_id
        device.status = DiscoveryStatus.DISCONNECTED
        device.error = reason or None
        device.hhip_firmware = False
        if previous_id and self._device_manager.get_device(previous_id):
            try:
                self._device_manager.remove_device(previous_id)
            except Exception:
                pass
        device.device_id = None
        self._publish_disconnected(device, previous_id=previous_id)

    def _register_physical(self, device: DiscoveredDevice) -> None:
        if not device.device_id:
            device.device_id = f"{device.board_type}_{device.port.replace('/', '_').replace(chr(92), '_')}"
        try:
            self._device_manager.register_physical_from_hello(
                device.device_id,
                device.board_type,
                firmware_version=device.firmware_version,
            )
        except Exception:
            logger.exception("[DISCOVERY] Failed to register %s", device.device_id)

    def _publish_connected(self, device: DiscoveredDevice, *, partial: bool = False) -> None:
        payload = device.to_dict()
        payload["partial"] = partial
        self._publish_bus(DeviceLifecycleEvent.CONNECTED, device)
        if self._dashboard:
            self._dashboard.publish_device_connected(
                device.device_id or device.port,
                **payload,
            )

    def _publish_disconnected(self, device: DiscoveredDevice, *, previous_id: Optional[str]) -> None:
        payload = device.to_dict()
        payload["previous_device_id"] = previous_id
        self._publish_bus(DeviceLifecycleEvent.DISCONNECTED, device)
        if self._dashboard:
            self._dashboard.publish_device_disconnected(
                previous_id or device.port,
                **payload,
            )

    def _publish_bus(self, event_type: str, device: DiscoveredDevice) -> None:
        event = Event.create(
            event_type=event_type,
            source=device.device_id or device.port,
            target="hhip",
            payload=device.to_dict(),
            metadata={"origin": "hardware_discovery"},
        )
        self._event_bus.publish(event)

    def _notify_change(self, devices: list[DiscoveredDevice]) -> None:
        if self._on_change:
            try:
                self._on_change(devices)
            except Exception:
                logger.exception("[DISCOVERY] on_change callback failed")


def _normalize_board_type(device_type: str) -> str:
    dt = device_type.lower().replace(" ", "-")
    mapping = {
        "esp32": "esp32",
        "esp8266": "esp8266",
        "arduino-uno": "arduino-uno",
        "arduino_uno": "arduino-uno",
        "uno": "arduino-uno",
        "mega": "arduino-mega",
        "arduino-mega": "arduino-mega",
        "nano": "arduino-nano",
        "stm32": "stm32",
        "pico": "raspberry-pi-pico",
        "raspberry-pi-pico": "raspberry-pi-pico",
    }
    return mapping.get(dt, dt)


def _label_for_board(board_type: str) -> str:
    labels = {
        "esp32": "ESP32 DevKit V1",
        "esp8266": "ESP8266",
        "arduino-uno": "Arduino Uno R3",
        "arduino-mega": "Arduino Mega 2560",
        "arduino-nano": "Arduino Nano",
        "stm32": "STM32 Blue Pill",
        "raspberry-pi-pico": "Raspberry Pi Pico",
    }
    return labels.get(board_type, board_type)
```

## `engine\hybrid\registry.py`

```python
"""Registry of connected physical hybrid devices (universal hardware)."""

from __future__ import annotations

import threading
from typing import Any, Optional, Union

from .device_agent import DeviceAgent
from .hardware import HardwareDevice, get_profile_registry
from .physical_device import PhysicalDevice
from .transports.hardware_transport import HardwareTransport

# Supported board families for Sprint 28
SUPPORTED_BOARD_TYPES = frozenset(
    {
        "esp32",
        "esp8266",
        "arduino-uno",
        "arduino-mega",
        "arduino-nano",
        "arduino",
        "stm32",
        "raspberry-pi-4",
        "raspberry-pi-pico",
        "raspberry-pi",
        "pico",
        "teensy",
        "nrf52",
        "microbit",
        "particle-photon",
        "adafruit-feather",
    }
)


class HybridRegistry:
    """Track active physical devices across serial, MQTT, and SSH transports."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._devices: dict[str, PhysicalDevice] = {}
        self._agents: dict[str, DeviceAgent] = {}
        self._transports: dict[str, HardwareTransport] = {}

    @staticmethod
    def supported_board_types() -> list[str]:
        profiles = get_profile_registry().list_profiles()
        ids = sorted({p.board_type for p in profiles})
        return ids or sorted(SUPPORTED_BOARD_TYPES)

    def list_devices(self) -> list[dict[str, Any]]:
        with self._lock:
            return [d.to_dict() for d in self._devices.values()]

    def get_device(self, device_id: str) -> Optional[PhysicalDevice]:
        with self._lock:
            return self._devices.get(device_id)

    def get_agent(self, device_id: str) -> Optional[DeviceAgent]:
        with self._lock:
            return self._agents.get(device_id)

    def get_transport(self, device_id: str) -> Optional[HardwareTransport]:
        with self._lock:
            return self._transports.get(device_id)

    def register(
        self,
        device: Union[PhysicalDevice, HardwareDevice],
        agent: DeviceAgent,
        transport: HardwareTransport,
    ) -> None:
        if isinstance(device, HardwareDevice):
            device = PhysicalDevice.from_hardware(device)
        with self._lock:
            self._devices[device.device_id] = device
            self._agents[device.device_id] = agent
            self._transports[device.device_id] = transport

    def unregister(self, device_id: str) -> Optional[PhysicalDevice]:
        with self._lock:
            agent = self._agents.pop(device_id, None)
            transport = self._transports.pop(device_id, None)
            device = self._devices.pop(device_id, None)
            if agent:
                try:
                    agent.disconnect()
                except Exception:
                    pass
            elif transport:
                try:
                    transport.disconnect()
                except Exception:
                    pass
            return device

    def disconnect(self, device_id: str) -> bool:
        removed = self.unregister(device_id)
        return removed is not None

    def poll_all(self) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        with self._lock:
            agents = list(self._agents.values())
        for agent in agents:
            events.extend(agent.poll())
        return events

    def profiles(self) -> list[dict[str, Any]]:
        return [p.to_dict() for p in get_profile_registry().list_profiles()]


# Backward-compatible alias
PhysicalDeviceRegistry = HybridRegistry
```

## `api\services\workspace_hardware_service.py`

```python
"""API façade for live hybrid workspace hardware nodes."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from engine.events.event_bus import EventBus
from engine.hardware_nodes import (
    BoardRenderer,
    DiscoveryListener,
    HardwareNodeFactory,
    WorkspaceSyncService,
)


class WorkspaceHardwareService:
    """Dependency-injected service for /workspace/hardware routes."""

    def __init__(
        self,
        data_dir: Path | str,
        *,
        event_bus: Optional[EventBus] = None,
        hybrid_service: Any = None,
    ) -> None:
        self.data_dir = Path(data_dir)
        self.event_bus = event_bus
        self.hybrid_service = hybrid_service
        self.factory = HardwareNodeFactory()
        self.sync = WorkspaceSyncService(
            data_dir=self.data_dir,
            factory=self.factory,
            event_bus=event_bus,
        )
        self.listener = DiscoveryListener(
            self.sync,
            event_bus=event_bus,
        )

    def list_hardware(self, workspace_id: str = "") -> dict[str, Any]:
        nodes = self.sync.list_nodes(workspace_id)
        return {"hardware": nodes, "count": len(nodes)}

    def get_hardware(self, device_id: str) -> dict[str, Any]:
        node = self.sync.get_node(device_id)
        if node is None:
            raise KeyError(f"hardware node not found: {device_id}")
        board_type = str(node.get("board_type") or "")
        return {
            **node,
            "render": BoardRenderer.render_spec(board_type),
            "inspector": self._inspector(node),
        }

    def reconnect(self, device_id: str = "", project_id: str = "") -> dict[str, Any]:
        hybrid = []
        if self.hybrid_service is not None:
            try:
                hybrid = self.hybrid_service.list_physical_devices()
            except Exception:  # noqa: BLE001
                hybrid = []
        if project_id:
            return self.sync.load_project(project_id, hybrid_devices=hybrid)
        return self.sync.reconnect(device_id, hybrid_devices=hybrid)

    def disconnect(self, device_id: str) -> dict[str, Any]:
        return self.sync.disconnect_node(device_id)

    def events(self, limit: int = 100) -> dict[str, Any]:
        ev = self.sync.events(limit=limit)
        return {"events": ev, "count": len(ev)}

    def update_layout(
        self,
        device_id: str,
        *,
        position: Optional[dict[str, float]] = None,
        rotation: Optional[float] = None,
        collapsed: Optional[bool] = None,
    ) -> dict[str, Any]:
        node = self.sync.update_layout(
            device_id,
            position=position,
            rotation=rotation,
            collapsed=collapsed,
        )
        if node is None:
            raise KeyError(f"hardware node not found: {device_id}")
        return node

    def _inspector(self, node: dict[str, Any]) -> dict[str, Any]:
        meta = node.get("metadata") or {}
        return {
            "manufacturer": node.get("manufacturer") or "",
            "chip": node.get("board_type") or "",
            "firmware": node.get("firmware_version") or "",
            "transport": node.get("transport") or "",
            "com_port": node.get("endpoint") or node.get("port") or "",
            "ip_address": meta.get("ip_address") or "",
            "capabilities": node.get("capabilities") or [],
            "memory": meta.get("memory") or "",
            "voltage": meta.get("voltage") or 3.3,
            "temperature": meta.get("temperature"),
            "heartbeat": node.get("heartbeat_ms") or node.get("heartbeat"),
            "serial_number": meta.get("serial_number") or "",
            "last_sync": node.get("last_sync_ms"),
            "health": node.get("health") or "unknown",
            "status": node.get("status"),
            "waiting_message": "Waiting for hardware" if node.get("status") == "waiting" else None,
        }
```

## `api\routes\workspace_hardware.py`

```python
"""Live hybrid workspace hardware nodes API — Sprint 29."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/workspace/hardware", tags=["workspace-hardware"])


class ReconnectRequest(BaseModel):
    device_id: str = ""
    project_id: str = ""


class DisconnectRequest(BaseModel):
    device_id: str


class LayoutUpdateRequest(BaseModel):
    position: Optional[dict[str, float]] = None
    rotation: Optional[float] = None
    collapsed: Optional[bool] = None


@router.get("")
@router.get("/")
def list_workspace_hardware(request: Request, workspace_id: str = "") -> dict[str, Any]:
    svc = request.app.state.workspace_hardware_service
    return svc.list_hardware(workspace_id)


@router.get("/events")
def list_hardware_events(request: Request, limit: int = 100) -> dict[str, Any]:
    return request.app.state.workspace_hardware_service.events(limit=limit)


@router.post("/reconnect")
def reconnect_hardware(body: ReconnectRequest, request: Request) -> dict[str, Any]:
    return request.app.state.workspace_hardware_service.reconnect(
        device_id=body.device_id,
        project_id=body.project_id,
    )


@router.post("/disconnect")
def disconnect_hardware(body: DisconnectRequest, request: Request) -> dict[str, Any]:
    result = request.app.state.workspace_hardware_service.disconnect(body.device_id)
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=f"hardware node not found: {body.device_id}")
    return result


@router.get("/{device_id}")
def get_workspace_hardware(device_id: str, request: Request) -> dict[str, Any]:
    try:
        return request.app.state.workspace_hardware_service.get_hardware(device_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/{device_id}/layout")
def patch_hardware_layout(
    device_id: str,
    body: LayoutUpdateRequest,
    request: Request,
) -> dict[str, Any]:
    try:
        return request.app.state.workspace_hardware_service.update_layout(
            device_id,
            position=body.position,
            rotation=body.rotation,
            collapsed=body.collapsed,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
```
