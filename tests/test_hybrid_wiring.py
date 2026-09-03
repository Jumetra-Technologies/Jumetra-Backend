"""Sprint 30 — Interactive hybrid wiring & live pin control tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from engine.hybrid.wiring import (
    AutoMapper,
    ConnectionGraph,
    PinConnection,
    PinEndpoint,
    PinValidator,
    WireManager,
    WireRenderer,
    WiringEventType,
)


def _ep(
    device_id: str,
    pin: str,
    *,
    kind: str = "virtual",
    pin_type: str = "GPIO",
    voltage: float = 3.3,
    supports_input: bool = True,
    supports_output: bool = True,
    available: bool = True,
) -> PinEndpoint:
    return PinEndpoint(
        device_id=device_id,
        pin=pin,
        device_kind=kind,
        pin_type=pin_type,
        voltage=voltage,
        supports_input=supports_input,
        supports_output=supports_output,
        available=available,
    )


class TestPinValidator:
    def test_reject_gpio_to_5v(self):
        v = PinValidator()
        r = v.validate(_ep("esp", "D2"), _ep("rail", "5V", pin_type="POWER", voltage=5.0))
        assert not r.ok
        assert any("power" in e.lower() or "Reject" in e for e in r.errors)

    def test_reject_uart_tx_to_tx(self):
        v = PinValidator()
        r = v.validate(
            _ep("a", "TX", pin_type="UART", supports_input=False, supports_output=True),
            _ep("b", "TX0", pin_type="UART", supports_input=False, supports_output=True),
        )
        assert not r.ok

    def test_reject_output_to_output(self):
        v = PinValidator()
        r = v.validate(
            _ep("a", "OUT1", supports_input=False, supports_output=True),
            _ep("b", "OUT2", supports_input=False, supports_output=True),
        )
        assert not r.ok

    def test_warn_33_to_5_suggest_level_shifter(self):
        v = PinValidator()
        r = v.validate(
            _ep("esp", "D2", voltage=3.3),
            _ep("uno", "D13", voltage=5.0, kind="physical"),
        )
        assert r.ok
        assert r.warnings
        assert any("level shifter" in s.lower() for s in r.suggestions)

    def test_pwm_adc_uart_ok(self):
        v = PinValidator()
        assert v.validate(_ep("a", "PWM1", pin_type="PWM"), _ep("b", "IN", pin_type="GPIO")).ok
        assert v.validate(
            _ep("a", "A0", pin_type="ADC", supports_output=False),
            _ep("b", "DAC", pin_type="DAC"),
        ).ok
        assert v.validate(
            _ep("a", "TX", pin_type="UART", supports_input=False),
            _ep("b", "RX", pin_type="UART", supports_output=False),
        ).ok


class TestWireCreationDeletion:
    def test_create_and_delete(self, tmp_path: Path):
        mgr = WireManager(data_dir=tmp_path)
        conn = mgr.connect(
            source=_ep("esp32", "D2", kind="physical"),
            destination=_ep("led1", "IN", kind="virtual"),
            workspace_id="ws1",
        )
        assert conn.connection_id
        assert conn.valid
        assert len(mgr.list_connections()) == 1
        removed = mgr.disconnect(conn.connection_id)
        assert removed is not None
        assert mgr.list_connections() == []

    def test_physical_physical_and_virtual_virtual(self, tmp_path: Path):
        mgr = WireManager(data_dir=tmp_path)
        mgr.connect(
            source=_ep("p1", "D1", kind="physical"),
            destination=_ep("p2", "D2", kind="physical"),
        )
        mgr.connect(
            source=_ep("v1", "OUT", kind="virtual"),
            destination=_ep("v2", "IN", kind="virtual"),
        )
        assert len(mgr.list_connections()) == 2


class TestAutoMapper:
    def test_drag_creates_pin_connected_event(self, tmp_path: Path):
        mgr = WireManager(data_dir=tmp_path)
        seen: list[str] = []
        mgr.subscribe_ws(lambda m: seen.append(m["type"]))
        am = AutoMapper(mgr)
        result = am.map_drag(
            source_device="esp32",
            source_pin="D2",
            destination_device="led1",
            destination_pin="IN",
            source_meta={"device_kind": "physical", "pin_type": "GPIO"},
            destination_meta={"device_kind": "virtual", "pin_type": "GPIO"},
        )
        assert result["ok"]
        assert result["connection"]["source_pin"] == "D2"
        assert WiringEventType.PIN_CONNECTED in seen
        assert WiringEventType.WIRE_CREATED in seen

    def test_preview_rejects_bad_wire(self, tmp_path: Path):
        am = AutoMapper(WireManager(data_dir=tmp_path))
        prev = am.preview(
            source_device="a",
            source_pin="D2",
            destination_device="b",
            destination_pin="5V",
            source_meta={"pin_type": "GPIO"},
            destination_meta={"pin_type": "POWER"},
        )
        assert prev["ok"] is False


class TestSignalPropagationAndPinEdit:
    def test_write_pin_broadcasts_signal(self, tmp_path: Path):
        mgr = WireManager(data_dir=tmp_path)
        mgr.connect(
            source=_ep("esp", "D2", kind="physical"),
            destination=_ep("led", "IN", kind="virtual"),
        )
        seen: list[dict] = []
        mgr.subscribe_ws(lambda m: seen.append(m))
        result = mgr.write_pin("esp", "D2", 1, mode="OUTPUT")
        assert result["ok"]
        assert result["latency_ms"] >= 0
        types = {m["type"] for m in seen}
        assert WiringEventType.SIGNAL_CHANGED in types
        assert WiringEventType.PIN_UPDATED in types
        state = mgr.get_pin_state("esp", "D2")
        assert state["logic"] == "HIGH"
        assert state["connected_components"] == ["led"]

    def test_pin_mode_high_low(self, tmp_path: Path):
        mgr = WireManager(data_dir=tmp_path)
        mgr.set_pin_mode("esp", "D4", "HIGH")
        assert mgr.get_pin_state("esp", "D4")["logic"] == "HIGH"
        mgr.set_pin_mode("esp", "D4", "LOW")
        assert mgr.get_pin_state("esp", "D4")["logic"] == "LOW"


class TestConnectionGraph:
    def test_traversal_and_highlight(self, tmp_path: Path):
        mgr = WireManager(data_dir=tmp_path)
        mgr.connect(source=_ep("a", "P1"), destination=_ep("b", "P1"))
        mgr.connect(source=_ep("b", "P1"), destination=_ep("c", "P1"))
        path = mgr.trace_signal_path("a", "P1", "c", "P1")
        assert "a:P1" in path and "c:P1" in path
        hl = mgr.highlight_path("a", "P1", "c", "P1")
        assert hl["connection_ids"]
        assert hl["path"]
        comps = mgr.find_connected_components()
        assert comps

    def test_remove_connection_from_graph(self):
        g = ConnectionGraph()
        conn = PinConnection.create(source=_ep("a", "1"), destination=_ep("b", "2"))
        g.add_connection(conn)
        assert g.get(conn.connection_id)
        g.remove_connection(conn.connection_id)
        assert g.get(conn.connection_id) is None


class TestPersistence:
    def test_persist_and_reload(self, tmp_path: Path):
        mgr = WireManager(data_dir=tmp_path)
        conn = mgr.connect(
            source=_ep("esp", "D2", kind="physical"),
            destination=_ep("led", "IN", kind="virtual"),
            workspace_id="lab1",
            wire_type="digital",
        )
        store = tmp_path / "lab_workspace" / "wiring" / "lab1.json"
        assert store.exists()
        data = json.loads(store.read_text(encoding="utf-8"))
        assert data["connections"][0]["connection_id"] == conn.connection_id

        mgr2 = WireManager(data_dir=tmp_path)
        loaded = mgr2.load_workspace("lab1")
        assert loaded["connections"]
        assert loaded["connections"][0]["source_pin"] == "D2"

    def test_waiting_for_hardware_status(self, tmp_path: Path):
        mgr = WireManager(data_dir=tmp_path)
        conn = mgr.connect(
            source=_ep("esp", "D2", kind="physical", available=False),
            destination=_ep("led", "IN", kind="virtual"),
        )
        assert conn.status == "waiting"


class TestWireRenderer:
    def test_colors_and_spec(self):
        assert WireRenderer.color_for("power") == "#dc2626"
        assert WireRenderer.color_for("ground") == "#111827"
        assert WireRenderer.color_for("pwm") == "#7c3aed"
        conn = PinConnection.create(
            source=_ep("a", "1"), destination=_ep("b", "2"), wire_type="digital"
        )
        spec = WireRenderer.render_spec(conn, signal_high=True)
        assert spec["animated"]
        assert spec["signal_high"]


@pytest.fixture()
def client(tmp_path: Path):
    app = create_app(data_dir=tmp_path)
    with TestClient(app) as test_client:
        yield test_client


class TestWiringREST:
    def test_crud(self, client: TestClient):
        res = client.post(
            "/workspace/connections",
            json={
                "source_device": "esp1",
                "source_pin": "D2",
                "destination_device": "led1",
                "destination_pin": "IN",
                "source_kind": "physical",
                "destination_kind": "virtual",
                "auto": True,
            },
        )
        assert res.status_code == 200, res.text
        cid = res.json()["connection_id"]

        listed = client.get("/workspace/connections")
        assert listed.status_code == 200
        assert listed.json()["count"] >= 1

        got = client.get(f"/workspace/connections/{cid}")
        assert got.status_code == 200
        assert "render" in got.json()

        patched = client.patch(f"/workspace/connections/{cid}", json={"wire_type": "pwm"})
        assert patched.status_code == 200
        assert patched.json()["wire_type"] == "pwm"

        deleted = client.delete(f"/workspace/connections/{cid}")
        assert deleted.status_code == 200

    def test_reject_invalid(self, client: TestClient):
        res = client.post(
            "/workspace/connections",
            json={
                "source_device": "esp",
                "source_pin": "D2",
                "destination_device": "rail",
                "destination_pin": "5V",
                "source_pin_type": "GPIO",
                "destination_pin_type": "POWER",
                "auto": True,
            },
        )
        assert res.status_code == 400

    def test_pin_write_and_inspect(self, client: TestClient):
        client.post(
            "/workspace/connections",
            json={
                "source_device": "esp1",
                "source_pin": "D2",
                "destination_device": "led1",
                "destination_pin": "IN",
                "source_kind": "physical",
                "destination_kind": "virtual",
            },
        )
        wr = client.post(
            "/workspace/connections/pin-write",
            json={"device_id": "esp1", "pin": "D2", "value": 1, "mode": "OUTPUT"},
        )
        assert wr.status_code == 200
        assert wr.json()["ok"] is True
        insp = client.get("/workspace/connections/pin/esp1/D2")
        assert insp.status_code == 200
        assert insp.json()["logic"] == "HIGH"


class TestWiringWebsocket:
    def test_ws_events(self, client: TestClient):
        with client.websocket_connect("/ws/wiring") as ws:
            snap = ws.receive_json()
            assert snap["type"] == "wiring_snapshot"
            client.app.state.workspace_wiring_service.create_connection(
                {
                    "source_device": "ws_esp",
                    "source_pin": "D2",
                    "destination_device": "ws_led",
                    "destination_pin": "IN",
                    "source_kind": "physical",
                    "destination_kind": "virtual",
                    "auto": True,
                }
            )
            types: set[str] = set()
            for _ in range(2):
                msg = ws.receive_json()
                types.add(str(msg.get("type") or ""))
            assert WiringEventType.WIRE_CREATED in types or WiringEventType.PIN_CONNECTED in types
            ws.send_text("ping")
            pong = ws.receive_json()
            assert pong["type"] == "pong"


class TestHistoryAndHybridKinds:
    def test_history_undo_stacks(self, tmp_path: Path):
        mgr = WireManager(data_dir=tmp_path)
        conn = mgr.connect(source=_ep("a", "1"), destination=_ep("b", "2"))
        entry = mgr.history.pop_undo()
        assert entry is not None
        assert entry.action == "create"
        assert entry.connection["connection_id"] == conn.connection_id

    def test_hybrid_to_hybrid(self, tmp_path: Path):
        mgr = WireManager(data_dir=tmp_path)
        conn = mgr.connect(
            source=_ep("h1", "D1", kind="hybrid"),
            destination=_ep("h2", "D2", kind="hybrid"),
        )
        assert conn.valid

    def test_spi_i2c_can_usb_inference(self):
        v = PinValidator()
        assert v.validate(_ep("a", "MOSI", pin_type="SPI"), _ep("b", "MOSI_IN", pin_type="SPI")).wire_type == "spi"
        assert v.validate(_ep("a", "SDA", pin_type="I2C"), _ep("b", "SDA", pin_type="I2C")).wire_type == "i2c"
        assert v.validate(_ep("a", "CANH", pin_type="CAN"), _ep("b", "CANH", pin_type="CAN")).wire_type == "can"
        assert v.validate(_ep("a", "D+", pin_type="USB"), _ep("b", "D+", pin_type="USB")).wire_type == "usb"

    def test_update_connection_color(self, tmp_path: Path):
        mgr = WireManager(data_dir=tmp_path)
        conn = mgr.connect(source=_ep("a", "1"), destination=_ep("b", "2"))
        updated = mgr.update_connection(conn.connection_id, {"wire_color": "#ff00ff", "latency_ms": 1.5})
        assert updated.wire_color == "#ff00ff"
        assert updated.latency_ms == 1.5

    def test_mark_waiting_and_active(self, tmp_path: Path):
        mgr = WireManager(data_dir=tmp_path)
        conn = mgr.connect(source=_ep("esp", "D2", kind="physical"), destination=_ep("led", "IN"))
        mgr.mark_waiting_for_device("esp")
        assert mgr.get_connection(conn.connection_id)["status"] == "waiting"
        mgr.mark_active_for_device("esp")
        assert mgr.get_connection(conn.connection_id)["status"] == "active"

    def test_preview_and_highlight_api(self, client: TestClient):
        client.post(
            "/workspace/connections",
            json={
                "source_device": "a",
                "source_pin": "P1",
                "destination_device": "b",
                "destination_pin": "P1",
                "auto": True,
            },
        )
        prev = client.post(
            "/workspace/connections/preview",
            json={
                "source_device": "a",
                "source_pin": "P1",
                "destination_device": "b",
                "destination_pin": "P1",
            },
        )
        assert prev.status_code == 200
        hl = client.post(
            "/workspace/connections/highlight",
            json={
                "start_device": "a",
                "start_pin": "P1",
                "end_device": "b",
                "end_pin": "P1",
            },
        )
        assert hl.status_code == 200
        assert "path" in hl.json()

    def test_pin_mode_api(self, client: TestClient):
        res = client.post(
            "/workspace/connections/pin-mode",
            json={"device_id": "esp", "pin": "D5", "mode": "PULLUP"},
        )
        assert res.status_code == 200
        assert res.json()["mode"] == "PULLUP"

    def test_get_missing_connection(self, client: TestClient):
        assert client.get("/workspace/connections/missing").status_code == 404

    def test_project_json_merge(self, tmp_path: Path):
        mgr = WireManager(data_dir=tmp_path)
        mgr.connect(
            source=_ep("esp", "D2"),
            destination=_ep("led", "IN"),
            workspace_id="projX",
        )
        path = tmp_path / "projects" / "projX" / "project.json"
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["hardware"]["wires"]
        assert "connection_graph" in data["hardware"]

    def test_neighbors(self, tmp_path: Path):
        mgr = WireManager(data_dir=tmp_path)
        mgr.connect(source=_ep("a", "1"), destination=_ep("b", "2"))
        assert "b:2" in mgr.graph.neighbors("a", "1")

    def test_self_pin_rejected(self):
        v = PinValidator()
        r = v.validate(_ep("a", "D1"), _ep("a", "D1"))
        assert not r.ok

    def test_power_ground_short(self):
        v = PinValidator()
        r = v.validate(
            _ep("a", "3V3", pin_type="POWER"),
            _ep("b", "GND", pin_type="GROUND"),
        )
        assert not r.ok

    def test_auto_route_points(self):
        pts = WireRenderer.auto_route({"x": 0, "y": 0}, {"x": 100, "y": 50})
        assert len(pts) == 4

    def test_connect_from_dict(self, tmp_path: Path):
        mgr = WireManager(data_dir=tmp_path)
        conn = mgr.connect_from_dict(
            {
                "source": "n1",
                "source_handle": "out",
                "target": "n2",
                "target_handle": "in",
                "protocol": "digital",
                "source_kind": "virtual",
                "destination_kind": "virtual",
            }
        )
        assert conn.source_pin == "out"

