"""Sprint 29 — Live Hybrid Workspace (digital twin) tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from engine.events.event import Event
from engine.events.event_bus import EventBus
from engine.hardware_nodes import (
    BoardRenderer,
    DiscoveryListener,
    HardwareNode,
    HardwareNodeFactory,
    HardwareNodeStatus,
    WorkspaceEventType,
    WorkspaceSyncService,
    get_pin_layout,
)
from engine.hardware_nodes.pin_layout import PIN_COLORS, PinKind
from engine.hybrid.events import HybridEventType


# ---------------------------------------------------------------------------
# HardwareNode / factory / pin layouts
# ---------------------------------------------------------------------------


class TestHardwareNode:
    def test_create_and_serialize(self):
        node = HardwareNode(
            device_id="esp32_01",
            board_type="esp32",
            manufacturer="Espressif",
            transport="serial",
            firmware_version="1.0.0",
            endpoint="COM3",
        )
        d = node.to_dict()
        assert d["kind"] == "hardware"
        assert d["device_id"] == "esp32_01"
        assert d["node_id"].startswith("HN_")
        restored = HardwareNode.from_dict(d)
        assert restored.device_id == "esp32_01"

    def test_canvas_node_shape(self):
        node = HardwareNode(device_id="uno1", board_type="arduino-uno")
        canvas = node.to_canvas_node()
        assert canvas["type"] == "hardware"
        assert canvas["properties"]["hardware_node"] is True

    def test_pin_gpio_update(self):
        pins = {p.name: p for p in get_pin_layout("esp32")}
        node = HardwareNode(device_id="d1", board_type="esp32", pins=pins)
        updated = node.update_pin_gpio("D2", 1)
        assert updated is not None
        assert updated.state.logic.value == "HIGH"
        node.update_pin_gpio("D2", 0)
        assert node.pins["D2"].state.logic.value == "LOW"

    def test_waiting_and_online(self):
        node = HardwareNode(device_id="d1", board_type="esp32")
        node.mark_waiting()
        assert node.status == HardwareNodeStatus.WAITING
        node.touch_heartbeat()
        assert node.status == HardwareNodeStatus.ONLINE


class TestHardwareNodeFactory:
    def test_from_hybrid_dict(self):
        factory = HardwareNodeFactory()
        node = factory.from_hybrid_device(
            {
                "device_id": "mega_1",
                "board_type": "arduino-mega",
                "manufacturer": "Arduino",
                "transport": "serial",
                "port": "COM7",
                "capabilities": ["gpio", "pwm"],
                "connected": True,
            }
        )
        assert node.board_type == "arduino-mega"
        assert len(node.pins) > 10
        assert node.endpoint == "COM7"

    def test_from_waiting(self):
        factory = HardwareNodeFactory()
        node = factory.from_waiting(device_id="pico_w", board_type="raspberry-pi-pico")
        assert node.status == HardwareNodeStatus.WAITING
        assert node.available is False


class TestPinLayouts:
    @pytest.mark.parametrize(
        "board",
        [
            "esp32",
            "arduino-uno",
            "arduino-mega",
            "stm32",
            "raspberry-pi-pico",
            "raspberry-pi-4",
            "esp8266",
        ],
    )
    def test_layout_fields(self, board: str):
        pins = get_pin_layout(board)
        assert len(pins) >= 8
        for p in pins:
            assert p.name
            assert p.pin_type in {k.value for k in PinKind} or p.pin_type in PIN_COLORS
            assert isinstance(p.supports_input, bool)
            assert isinstance(p.supports_output, bool)
            assert p.voltage > 0

    def test_pin_colors(self):
        assert PIN_COLORS["GPIO"] == "#2563eb"
        assert PIN_COLORS["GROUND"] == "#374151"


class TestBoardRenderer:
    def test_silhouette_esp32(self):
        sil = BoardRenderer.silhouette("esp32")
        assert "usb" in sil["features"] or "dual-row" in sil["features"]
        assert sil["width"] > 0

    def test_render_spec(self):
        spec = BoardRenderer.render_spec("arduino-uno")
        assert "pins" in spec
        assert "silhouette" in spec
        assert "icsp" in spec["silhouette"]["features"] or "usb" in spec["silhouette"]["features"]


# ---------------------------------------------------------------------------
# Workspace sync / discovery / persistence / reconnect
# ---------------------------------------------------------------------------


class TestWorkspaceSync:
    def test_upsert_and_list(self, tmp_path: Path):
        sync = WorkspaceSyncService(data_dir=tmp_path)
        node = sync.upsert_from_device(
            {
                "device_id": "esp_a",
                "board_type": "esp32",
                "port": "COM3",
                "transport": "serial",
                "connected": True,
            }
        )
        assert node.device_id == "esp_a"
        listed = sync.list_nodes()
        assert len(listed) == 1
        assert listed[0]["status"] == "online"

    def test_pin_update_emits_event(self, tmp_path: Path):
        sync = WorkspaceSyncService(data_dir=tmp_path)
        sync.upsert_from_device({"device_id": "esp_a", "board_type": "esp32", "connected": True})
        seen: list[dict] = []
        sync.subscribe_ws(lambda m: seen.append(m))
        sync.update_pin_state("esp_a", "D2", 1)
        types = {m["type"] for m in seen}
        assert WorkspaceEventType.PIN_STATE_CHANGED in types
        assert WorkspaceEventType.HEARTBEAT in types

    def test_remove_marks_waiting(self, tmp_path: Path):
        sync = WorkspaceSyncService(data_dir=tmp_path)
        sync.upsert_from_device({"device_id": "esp_a", "board_type": "esp32", "connected": True})
        sync.remove_device("esp_a")
        node = sync.get_node("esp_a")
        assert node is not None
        assert node["status"] == "waiting"

    def test_position_restore(self, tmp_path: Path):
        sync = WorkspaceSyncService(data_dir=tmp_path)
        sync.upsert_from_device({"device_id": "esp_a", "board_type": "esp32", "connected": True})
        sync.update_layout("esp_a", position={"x": 400, "y": 250}, rotation=15, collapsed=True)
        sync.upsert_from_device({"device_id": "esp_a", "board_type": "esp32", "connected": True})
        node = sync.get_node("esp_a")
        assert node["position"]["x"] == 400
        assert node["rotation"] == 15
        assert node["collapsed"] is True

    def test_persistence_roundtrip(self, tmp_path: Path):
        sync = WorkspaceSyncService(data_dir=tmp_path)
        sync.upsert_from_device(
            {
                "device_id": "uno_1",
                "board_type": "arduino-uno",
                "port": "COM4",
                "connected": True,
            }
        )
        sync.update_layout("uno_1", position={"x": 10, "y": 20})
        store = tmp_path / "lab_workspace" / "hardware_nodes" / "default.json"
        assert store.exists()
        data = json.loads(store.read_text(encoding="utf-8"))
        assert data["nodes"][0]["device_id"] == "uno_1"

        sync2 = WorkspaceSyncService(data_dir=tmp_path)
        n = sync2.get_node("uno_1")
        assert n is not None
        assert n["status"] == "waiting"  # after restart
        assert n["position"]["x"] == 10

    def test_project_json_hardware(self, tmp_path: Path):
        sync = WorkspaceSyncService(data_dir=tmp_path)
        sync.upsert_from_device({"device_id": "stm1", "board_type": "stm32", "connected": True})
        proj = sync.save_project_hardware("proj_demo")
        assert "hardware" in proj
        assert proj["hardware"]["nodes"][0]["board_type"] == "stm32"
        path = tmp_path / "projects" / "proj_demo" / "project.json"
        assert path.exists()

    def test_reconnect_waiting(self, tmp_path: Path):
        sync = WorkspaceSyncService(data_dir=tmp_path)
        sync.upsert_from_device(
            {"device_id": "esp_a", "board_type": "esp32", "port": "COM3", "connected": True}
        )
        sync.remove_device("esp_a")
        result = sync.reconnect(
            hybrid_devices=[
                {"device_id": "esp_a", "board_type": "esp32", "endpoint": "COM3", "transport": "serial"}
            ]
        )
        assert "esp_a" in result["reconnected"]
        assert sync.get_node("esp_a")["status"] == "online"

    def test_reconnect_still_waiting(self, tmp_path: Path):
        sync = WorkspaceSyncService(data_dir=tmp_path)
        sync.upsert_from_device({"device_id": "esp_a", "board_type": "esp32", "connected": True})
        sync.remove_device("esp_a")
        result = sync.reconnect(hybrid_devices=[])
        assert "esp_a" in result["waiting"]

    def test_multi_board(self, tmp_path: Path):
        sync = WorkspaceSyncService(data_dir=tmp_path)
        for did, bt in [
            ("e1", "esp32"),
            ("a1", "arduino-uno"),
            ("p1", "raspberry-pi-pico"),
            ("s1", "stm32"),
            ("r1", "raspberry-pi-4"),
        ]:
            sync.upsert_from_device({"device_id": did, "board_type": bt, "connected": True})
        assert len(sync.list_nodes()) == 5


class TestDiscoveryListener:
    def test_connect_creates_node(self, tmp_path: Path):
        bus = EventBus()
        sync = WorkspaceSyncService(data_dir=tmp_path, event_bus=bus)
        DiscoveryListener(sync, event_bus=bus)
        bus.publish(
            Event.create(
                HybridEventType.PHYSICAL_DEVICE_CONNECTED,
                source="esp_x",
                payload={
                    "device_id": "esp_x",
                    "board_type": "esp32",
                    "port": "COM9",
                    "connected": True,
                },
            )
        )
        assert sync.get_node("esp_x") is not None
        assert sync.get_node("esp_x")["status"] == "online"

    def test_disconnect_removes(self, tmp_path: Path):
        bus = EventBus()
        sync = WorkspaceSyncService(data_dir=tmp_path, event_bus=bus)
        DiscoveryListener(sync, event_bus=bus)
        sync.upsert_from_device({"device_id": "esp_x", "board_type": "esp32", "connected": True})
        bus.publish(
            Event.create(
                HybridEventType.PHYSICAL_DEVICE_DISCONNECTED,
                source="esp_x",
                payload={"device_id": "esp_x"},
            )
        )
        assert sync.get_node("esp_x")["status"] == "waiting"

    def test_gpio_state_updates_pin(self, tmp_path: Path):
        bus = EventBus()
        sync = WorkspaceSyncService(data_dir=tmp_path, event_bus=bus)
        DiscoveryListener(sync, event_bus=bus)
        sync.upsert_from_device({"device_id": "esp_x", "board_type": "esp32", "connected": True})
        bus.publish(
            Event.create(
                HybridEventType.GPIO_STATE,
                source="esp_x",
                payload={"device_id": "esp_x", "pin": "D2", "value": 1},
            )
        )
        node = sync.get_node_obj("esp_x")
        assert node is not None
        assert node.pins["D2"].state.logic.value == "HIGH"

    def test_workspace_node_created_event(self, tmp_path: Path):
        sync = WorkspaceSyncService(data_dir=tmp_path)
        seen: list[str] = []
        sync.subscribe_ws(lambda m: seen.append(m["type"]))
        sync.upsert_from_device({"device_id": "n1", "board_type": "esp32", "connected": True})
        assert WorkspaceEventType.WORKSPACE_NODE_CREATED in seen
        assert WorkspaceEventType.BOARD_CONNECTED in seen


# ---------------------------------------------------------------------------
# API + WebSocket
# ---------------------------------------------------------------------------


@pytest.fixture()
def client(tmp_path: Path):
    app = create_app(data_dir=tmp_path)
    with TestClient(app) as test_client:
        yield test_client


class TestWorkspaceHardwareAPI:
    def test_list_empty(self, client: TestClient):
        res = client.get("/workspace/hardware")
        assert res.status_code == 200
        body = res.json()
        assert "hardware" in body
        assert body["count"] >= 0

    def test_reconnect_disconnect_events(self, client: TestClient, tmp_path: Path):
        svc = client.app.state.workspace_hardware_service
        svc.sync.upsert_from_device(
            {"device_id": "api_esp", "board_type": "esp32", "port": "COM1", "connected": True}
        )
        res = client.get("/workspace/hardware/api_esp")
        assert res.status_code == 200
        assert res.json()["device_id"] == "api_esp"
        assert "inspector" in res.json()
        assert "render" in res.json()

        r2 = client.post("/workspace/hardware/reconnect", json={"device_id": "api_esp"})
        assert r2.status_code == 200

        r3 = client.post("/workspace/hardware/disconnect", json={"device_id": "api_esp"})
        assert r3.status_code == 200

        ev = client.get("/workspace/hardware/events")
        assert ev.status_code == 200
        assert ev.json()["count"] >= 1

    def test_get_missing(self, client: TestClient):
        res = client.get("/workspace/hardware/does-not-exist")
        assert res.status_code == 404


class TestHardwareWebsocket:
    def test_ws_snapshot_and_events(self, client: TestClient):
        with client.websocket_connect("/ws/hardware") as ws:
            snap = ws.receive_json()
            assert snap["type"] == "hardware_snapshot"
            client.app.state.workspace_hardware_service.sync.upsert_from_device(
                {"device_id": "ws1", "board_type": "esp32", "connected": True}
            )
            types_seen: set[str] = set()
            # New node fan-out: BOARD_CONNECTED + NODE_CREATED + WORKSPACE_NODE_CREATED
            for _ in range(3):
                msg = ws.receive_json()
                types_seen.add(str(msg.get("type") or ""))
            assert WorkspaceEventType.BOARD_CONNECTED in types_seen
            assert WorkspaceEventType.WORKSPACE_NODE_CREATED in types_seen
            ws.send_text("ping")
            pong = ws.receive_json()
            assert pong["type"] == "pong"


class TestAutoDiscoveryIntegration:
    def test_hybrid_connect_event_creates_workspace_node(self, client: TestClient):
        bus: EventBus = client.app.state.event_bus
        bus.publish(
            Event.create(
                HybridEventType.PHYSICAL_DEVICE_CONNECTED,
                source="auto1",
                payload={
                    "device_id": "auto1",
                    "board_type": "arduino-uno",
                    "port": "COM11",
                    "manufacturer": "Arduino",
                    "connected": True,
                },
            )
        )
        res = client.get("/workspace/hardware/auto1")
        assert res.status_code == 200
        assert res.json()["board_type"] == "arduino-uno"
