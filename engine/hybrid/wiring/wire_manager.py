"""WireManager — create/validate/persist hybrid workspace connections."""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional

from engine.events.event_bus import EventBus
from engine.hybrid.pin_mapper import PinMapper

from .connection_events import WiringEventType, publish_wiring_event
from .connection_graph import ConnectionGraph
from .connection_history import ConnectionHistory
from .pin_connection import (
    ConnectionStatus,
    PinConnection,
    PinEndpoint,
    WIRE_COLORS,
)
from .pin_validator import PinValidator
from .wire_renderer import WireRenderer

logger = logging.getLogger(__name__)

WsBroadcast = Callable[[dict[str, Any]], None]


class WireManager:
    """
    Central wiring service for the Engineering Workspace.

    - Validates and stores PinConnections
    - Maintains ConnectionGraph
    - Mirrors physical↔virtual into legacy PinMapper for HybridRouter fanout
    - Broadcasts WebSocket + EventBus wiring events
    - Persists to project / workspace JSON
    """

    def __init__(
        self,
        data_dir: Path | str = "data",
        *,
        event_bus: Optional[EventBus] = None,
        pin_mapper: Optional[PinMapper] = None,
        hybrid_router: Any = None,
        validator: Optional[PinValidator] = None,
    ) -> None:
        self.data_dir = Path(data_dir)
        self.store_dir = self.data_dir / "lab_workspace" / "wiring"
        self.store_dir.mkdir(parents=True, exist_ok=True)
        self.event_bus = event_bus
        self.pin_mapper = pin_mapper
        self.hybrid_router = hybrid_router
        self.validator = validator or PinValidator()
        self.graph = ConnectionGraph()
        self.history = ConnectionHistory()
        self.renderer = WireRenderer()
        self._lock = threading.RLock()
        self._connections: dict[str, PinConnection] = {}
        self._ws: list[WsBroadcast] = []
        self._pin_state: dict[str, dict[str, Any]] = {}  # device:pin -> live state
        self._load_default()

    # ---- WS ---------------------------------------------------------------

    def subscribe_ws(self, callback: WsBroadcast) -> None:
        self._ws.append(callback)

    def unsubscribe_ws(self, callback: WsBroadcast) -> None:
        try:
            self._ws.remove(callback)
        except ValueError:
            pass

    def _broadcast(self, event_type: str, payload: dict[str, Any]) -> None:
        message = {
            "type": event_type,
            "event": event_type,
            "payload": payload,
            "timestamp_ms": int(time.time() * 1000),
        }
        for cb in list(self._ws):
            try:
                cb(message)
            except Exception:  # noqa: BLE001
                logger.exception("wiring WS subscriber failed")
        publish_wiring_event(self.event_bus, event_type, payload=payload)

    # ---- Queries ----------------------------------------------------------

    def list_connections(self, workspace_id: str = "") -> list[dict[str, Any]]:
        with self._lock:
            items = list(self._connections.values())
            if workspace_id:
                items = [c for c in items if c.workspace_id in ("", workspace_id)]
            return [c.to_dict() for c in items]

    def get_connection(self, connection_id: str) -> Optional[dict[str, Any]]:
        with self._lock:
            c = self._connections.get(connection_id)
            if c is None:
                return None
            data = c.to_dict()
            data["render"] = self.renderer.render_spec(c)
            return data

    def get_connection_obj(self, connection_id: str) -> Optional[PinConnection]:
        with self._lock:
            return self._connections.get(connection_id)

    # ---- Connect / disconnect ---------------------------------------------

    def connect(
        self,
        *,
        source: PinEndpoint,
        destination: PinEndpoint,
        wire_type: str = "",
        workspace_id: str = "",
        transport: str = "",
        routing: Optional[list[dict[str, float]]] = None,
        auto: bool = False,
        force: bool = False,
    ) -> PinConnection:
        result = self.validator.validate(source, destination, requested_wire_type=wire_type)
        if not result.ok and not force:
            conn = PinConnection.create(
                source=source,
                destination=destination,
                wire_type=result.wire_type,
                workspace_id=workspace_id,
                transport=transport,
            )
            conn.valid = False
            conn.status = ConnectionStatus.INVALID.value
            conn.issues = list(result.errors)
            conn.warnings = list(result.warnings)
            conn.suggestions = list(result.suggestions)
            raise ValueError("; ".join(result.errors) or "invalid connection")

        conn = PinConnection.create(
            source=source,
            destination=destination,
            wire_type=result.wire_type,
            workspace_id=workspace_id,
            transport=transport,
        )
        conn.valid = result.ok
        conn.issues = list(result.errors)
        conn.warnings = list(result.warnings)
        conn.suggestions = list(result.suggestions)
        conn.wire_color = WIRE_COLORS.get(conn.wire_type, WIRE_COLORS["digital"])
        if routing:
            conn.routing = list(routing)
        else:
            conn.routing = self.renderer.auto_route({"x": 0, "y": 0}, {"x": 100, "y": 100})

        # Mirror into PinMapper when physical ↔ virtual for HybridRouter
        if self.pin_mapper is not None:
            phys, virt = self._split_phys_virt(source, destination)
            if phys and virt:
                try:
                    legacy = self.pin_mapper.create_connection(
                        virtual_node_id=virt.device_id,
                        virtual_pin_id=virt.pin,
                        physical_device_id=phys.device_id,
                        physical_pin_id=phys.pin,
                        workspace_id=workspace_id,
                    )
                    conn.hybrid_connection_id = str(legacy.get("connection_id") or "")
                except Exception:  # noqa: BLE001
                    logger.exception("failed to mirror into PinMapper")

        with self._lock:
            self._connections[conn.connection_id] = conn
            self.graph.add_connection(conn)
            self.history.record_create(conn.to_dict())
            self._persist(workspace_id)

        payload = conn.to_dict()
        payload["auto"] = auto
        self._broadcast(WiringEventType.WIRE_CREATED, payload)
        self._broadcast(WiringEventType.PIN_CONNECTED, payload)
        return conn

    def connect_from_dict(self, body: dict[str, Any]) -> PinConnection:
        src = PinEndpoint.from_dict(
            {
                "device_id": body.get("source_device") or body.get("source"),
                "pin": body.get("source_pin") or body.get("source_handle"),
                "device_kind": body.get("source_kind") or "unknown",
                "pin_type": body.get("source_pin_type") or body.get("source_type") or "GPIO",
                "voltage": body.get("source_voltage", 3.3),
                "supports_input": body.get("source_supports_input", True),
                "supports_output": body.get("source_supports_output", True),
                "available": body.get("source_available", True),
            }
        )
        dst = PinEndpoint.from_dict(
            {
                "device_id": body.get("destination_device") or body.get("target"),
                "pin": body.get("destination_pin") or body.get("target_handle"),
                "device_kind": body.get("destination_kind") or "unknown",
                "pin_type": body.get("destination_pin_type") or body.get("destination_type") or "GPIO",
                "voltage": body.get("destination_voltage", 3.3),
                "supports_input": body.get("destination_supports_input", True),
                "supports_output": body.get("destination_supports_output", True),
                "available": body.get("destination_available", True),
            }
        )
        return self.connect(
            source=src,
            destination=dst,
            wire_type=str(body.get("wire_type") or body.get("protocol") or ""),
            workspace_id=str(body.get("workspace_id") or ""),
            transport=str(body.get("transport") or ""),
            routing=body.get("routing"),
            auto=bool(body.get("auto", False)),
            force=bool(body.get("force", False)),
        )

    def disconnect(self, connection_id: str) -> Optional[PinConnection]:
        with self._lock:
            conn = self._connections.pop(connection_id, None)
            if conn is None:
                return None
            self.graph.remove_connection(connection_id)
            self.history.record_delete(conn.to_dict())
            if conn.hybrid_connection_id and self.pin_mapper is not None:
                try:
                    self.pin_mapper.delete_connection(conn.hybrid_connection_id)
                except Exception:  # noqa: BLE001
                    logger.exception("failed to delete PinMapper link")
            self._persist(conn.workspace_id)
            payload = conn.to_dict()

        self._broadcast(WiringEventType.WIRE_REMOVED, payload)
        self._broadcast(WiringEventType.PIN_DISCONNECTED, payload)
        return conn

    def update_connection(self, connection_id: str, patch: dict[str, Any]) -> PinConnection:
        with self._lock:
            conn = self._connections.get(connection_id)
            if conn is None:
                raise KeyError(f"connection not found: {connection_id}")
            before = conn.to_dict()
            if "wire_type" in patch:
                conn.wire_type = str(patch["wire_type"]).lower()
                conn.wire_color = WIRE_COLORS.get(conn.wire_type, conn.wire_color)
            if "wire_color" in patch:
                conn.wire_color = str(patch["wire_color"])
            if "direction" in patch:
                conn.direction = str(patch["direction"])
            if "status" in patch:
                conn.status = str(patch["status"])
            if "routing" in patch and isinstance(patch["routing"], list):
                conn.routing = list(patch["routing"])
            if "latency_ms" in patch or "latency" in patch:
                conn.latency_ms = float(patch.get("latency_ms", patch.get("latency", 0)))
            if "transport" in patch:
                conn.transport = str(patch["transport"])
            self.history.record_update(before, conn.to_dict())
            self._persist(conn.workspace_id)
            payload = conn.to_dict()

        self._broadcast(WiringEventType.WIRE_UPDATED, payload)
        self._broadcast(WiringEventType.PIN_UPDATED, payload)
        return conn

    # ---- Live pin control -------------------------------------------------

    def write_pin(
        self,
        device_id: str,
        pin: str,
        value: Any,
        *,
        mode: str = "",
        virtual_node_id: str = "",
    ) -> dict[str, Any]:
        t0 = time.perf_counter()
        result: dict[str, Any] = {
            "device_id": device_id,
            "pin": pin,
            "value": value,
            "mode": mode or None,
            "ok": True,
        }
        int_val = 1 if value in (True, "HIGH", "high", 1, "1") else 0
        if isinstance(value, (int, float)) and value not in (0, 1):
            # PWM / analog numeric
            int_val = int(value)

        if self.hybrid_router is not None and hasattr(self.hybrid_router, "write_gpio"):
            try:
                routed = self.hybrid_router.write_gpio(
                    device_id, pin, int_val, virtual_node_id=virtual_node_id
                )
                result["routed"] = routed
            except KeyError:
                # Device not online — still update digital twin / local state
                result["routed"] = {"simulated": True, "value": int_val, "waiting": True}
                result["warning"] = f"device not connected: {device_id}"
            except Exception as exc:  # noqa: BLE001
                result["ok"] = False
                result["error"] = str(exc)
        else:
            result["routed"] = {"simulated": True, "value": int_val}

        latency = (time.perf_counter() - t0) * 1000.0
        result["latency_ms"] = round(latency, 3)
        key = f"{device_id}:{pin}"
        state = {
            "logic": "HIGH" if int_val else "LOW",
            "value": int_val,
            "mode": mode or "OUTPUT",
            "timestamp_ms": int(time.time() * 1000),
            "latency_ms": result["latency_ms"],
        }
        with self._lock:
            self._pin_state[key] = state
            # Update latency on related wires
            for conn in self.graph.connections_for_pin(device_id, pin):
                conn.latency_ms = result["latency_ms"]

        self._broadcast(WiringEventType.SIGNAL_CHANGED, {**result, "state": state})
        self._broadcast(WiringEventType.PIN_UPDATED, {**result, "state": state})
        if mode:
            self._broadcast(
                WiringEventType.PIN_MODE_CHANGED,
                {"device_id": device_id, "pin": pin, "mode": mode},
            )
        return result

    def set_pin_mode(self, device_id: str, pin: str, mode: str) -> dict[str, Any]:
        mode_u = mode.upper()
        key = f"{device_id}:{pin}"
        with self._lock:
            st = self._pin_state.get(key) or {}
            st["mode"] = mode_u
            st["timestamp_ms"] = int(time.time() * 1000)
            self._pin_state[key] = st
        payload = {"device_id": device_id, "pin": pin, "mode": mode_u}
        self._broadcast(WiringEventType.PIN_MODE_CHANGED, payload)
        self._broadcast(WiringEventType.PIN_UPDATED, payload)
        # If mode is HIGH/LOW treat as write
        if mode_u in ("HIGH", "LOW"):
            return self.write_pin(device_id, pin, 1 if mode_u == "HIGH" else 0, mode="OUTPUT")
        return payload

    def get_pin_state(self, device_id: str, pin: str) -> dict[str, Any]:
        key = f"{device_id}:{pin}"
        with self._lock:
            state = dict(self._pin_state.get(key) or {})
            wires = [c.to_dict() for c in self.graph.connections_for_pin(device_id, pin)]
        return {
            "device_id": device_id,
            "pin": pin,
            "pin_number": pin,
            "mode": state.get("mode") or "UNKNOWN",
            "current_value": state.get("value"),
            "logic": state.get("logic") or "UNKNOWN",
            "voltage": state.get("voltage"),
            "direction": state.get("mode"),
            "pwm": state.get("pwm"),
            "frequency": state.get("frequency_hz"),
            "adc": state.get("adc"),
            "connected_wires": wires,
            "connected_components": [
                w["destination_device"] if w["source_device"] == device_id else w["source_device"]
                for w in wires
            ],
            "live_events": [],
            "state": state,
        }

    # ---- Graph helpers ----------------------------------------------------

    def find_connected_components(self) -> list[list[str]]:
        return self.graph.find_connected_components()

    def trace_signal_path(
        self,
        start_device: str,
        start_pin: str,
        end_device: str = "",
        end_pin: str = "",
    ) -> list[str]:
        return self.graph.trace_signal_path(start_device, start_pin, end_device, end_pin)

    def highlight_path(
        self,
        start_device: str,
        start_pin: str,
        end_device: str,
        end_pin: str,
    ) -> dict[str, Any]:
        return self.graph.highlight_path(start_device, start_pin, end_device, end_pin)

    def mark_waiting_for_device(self, device_id: str) -> None:
        with self._lock:
            for conn in self._connections.values():
                if conn.source_device == device_id or conn.destination_device == device_id:
                    conn.status = ConnectionStatus.WAITING.value
            self._persist("")

    def mark_active_for_device(self, device_id: str) -> None:
        with self._lock:
            for conn in self._connections.values():
                if conn.source_device == device_id or conn.destination_device == device_id:
                    if conn.valid:
                        conn.status = ConnectionStatus.ACTIVE.value
            self._persist("")

    # ---- Persistence ------------------------------------------------------

    def _store_path(self, workspace_id: str) -> Path:
        safe = (workspace_id or "default").replace("/", "_")
        return self.store_dir / f"{safe}.json"

    def _persist(self, workspace_id: str) -> None:
        path = self._store_path(workspace_id or "default")
        payload = {
            "workspace_id": workspace_id or "default",
            "connections": [c.to_dict() for c in self._connections.values()],
            "updated_at_ms": int(time.time() * 1000),
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        # Merge into project.json hardware.wires when workspace looks like a project
        if workspace_id and workspace_id != "default":
            self._merge_project(workspace_id, payload["connections"])

    def _merge_project(self, project_id: str, connections: list[dict[str, Any]]) -> None:
        path = self.data_dir / "projects" / project_id / "project.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        data: dict[str, Any] = {}
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                data = {}
        hw = data.setdefault("hardware", {})
        hw["wires"] = connections
        hw["connection_graph"] = {
            "components": self.find_connected_components(),
            "count": len(connections),
        }
        data["id"] = data.get("id") or project_id
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def load_workspace(self, workspace_id: str = "default") -> dict[str, Any]:
        path = self._store_path(workspace_id)
        if not path.exists():
            # try project.json
            proj = self.data_dir / "projects" / workspace_id / "project.json"
            if proj.exists():
                data = json.loads(proj.read_text(encoding="utf-8"))
                wires = (data.get("hardware") or {}).get("wires") or []
                return self._hydrate(wires, workspace_id=workspace_id)
            return {"connections": [], "waiting": []}
        data = json.loads(path.read_text(encoding="utf-8"))
        return self._hydrate(data.get("connections") or [], workspace_id=workspace_id)

    def _hydrate(self, raw: list[dict[str, Any]], *, workspace_id: str) -> dict[str, Any]:
        waiting: list[str] = []
        with self._lock:
            self._connections.clear()
            self.graph.clear()
            for item in raw:
                conn = PinConnection.from_dict(item)
                if workspace_id:
                    conn.workspace_id = conn.workspace_id or workspace_id
                # Missing hardware stays connected but waiting
                if conn.status == ConnectionStatus.ACTIVE.value:
                    # keep as waiting until devices confirm — caller can activate
                    pass
                self._connections[conn.connection_id] = conn
                self.graph.add_connection(conn)
                if conn.status == ConnectionStatus.WAITING.value:
                    waiting.append(conn.connection_id)
        return {"connections": self.list_connections(workspace_id), "waiting": waiting}

    def _load_default(self) -> None:
        path = self._store_path("default")
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                self._hydrate(data.get("connections") or [], workspace_id="default")
            except Exception:  # noqa: BLE001
                logger.exception("failed to load wiring store")

    @staticmethod
    def _split_phys_virt(
        a: PinEndpoint, b: PinEndpoint
    ) -> tuple[Optional[PinEndpoint], Optional[PinEndpoint]]:
        kinds = {
            "physical": "physical",
            "virtual": "virtual",
            "simulated": "virtual",
            "hybrid": "hybrid",
        }
        ak = kinds.get(a.device_kind, a.device_kind)
        bk = kinds.get(b.device_kind, b.device_kind)
        if ak == "physical" and bk in ("virtual", "simulated"):
            return a, b
        if bk == "physical" and ak in ("virtual", "simulated"):
            return b, a
        return None, None
