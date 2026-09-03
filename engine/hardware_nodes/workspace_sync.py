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
