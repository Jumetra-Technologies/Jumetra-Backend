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
