"""Sprint 26 — lab workspace engine unit tests."""

from __future__ import annotations

from engine.lab_workspace import (
    LabWorkspaceService,
    LabWorkspaceStorage,
    validate_wire_with_peers,
    CanvasWire,
    CanvasNode,
)


def test_service_lifecycle(tmp_path):
    svc = LabWorkspaceService(storage=LabWorkspaceStorage(tmp_path))
    ws = svc.create(name="Unit Lab")
    wid = ws["workspace_id"]
    svc.connect(wid)
    n1 = svc.add_node(wid, component_id="esp32", position={"x": 0, "y": 0}, device_mode="virtual")
    n2 = svc.add_node(wid, component_id="dht22", position={"x": 100, "y": 0})
    wire = svc.add_wire(wid, source=n1["id"], target=n2["id"], protocol="digital")
    assert wire["valid"] is True
    svc.run(wid, speed="5x")
    state = svc.step(wid, 100)
    assert state["tick_count"] == 1
    assert any(n["live_state"] for n in state["canvas"]["nodes"])


def test_wire_voltage_warning():
    nodes = {
        "a": CanvasNode("a", "esp32", "ESP32", "esp32", {"x": 0, "y": 0}),
        "b": CanvasNode("b", "hc-sr04", "HC-SR04", "sensors", {"x": 1, "y": 1}),
    }
    wire = CanvasWire("w1", "a", "out", "b", "in", protocol="digital", voltage_v=5.0)
    result = validate_wire_with_peers(wire, nodes, {})
    assert any("Voltage" in i for i in result.issues)


def test_duplicate_and_delete(tmp_path):
    svc = LabWorkspaceService(storage=LabWorkspaceStorage(tmp_path))
    wid = svc.create(name="Dup")["workspace_id"]
    node = svc.add_node(wid, component_id="led", position={"x": 0, "y": 0})
    clones = svc.duplicate_nodes(wid, [node["id"]])
    assert len(clones) == 1
    svc.delete_nodes(wid, [node["id"], clones[0]["id"]])
    assert svc.get_state(wid)["node_count"] == 0


def test_catalog_categories():
    svc = LabWorkspaceService()
    cat = svc.catalog()
    assert set(cat["categories"]) >= {
        "sensors",
        "actuators",
        "esp32",
        "arduino",
        "robotics",
        "ai-modules",
        "marketplace",
    }


def test_workspace_reload_from_disk(tmp_path):
    storage = LabWorkspaceStorage(tmp_path)
    svc1 = LabWorkspaceService(storage=storage)
    wid = svc1.create(name="Persist Lab")["workspace_id"]
    svc1.add_node(wid, component_id="led", position={"x": 10, "y": 20})
    svc1.add_node(wid, component_id="esp32", position={"x": 100, "y": 20}, device_mode="physical", physical_port="COM4")

    svc2 = LabWorkspaceService(storage=storage)
    state = svc2.get_state(wid)
    assert state["node_count"] == 2
    assert any(n["component_id"] == "led" for n in state["canvas"]["nodes"])
