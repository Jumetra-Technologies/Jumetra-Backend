"""Sprint 26 — additional workspace coverage toward 450+ suite."""

from __future__ import annotations

from engine.lab_workspace import HistoryStack, WorkspaceSnapshot, auto_route_points, search_catalog
from engine.lab_workspace.service import LabWorkspaceService
from engine.lab_workspace.storage import LabWorkspaceStorage


def test_history_stack():
    h = HistoryStack(limit=2)
    a = WorkspaceSnapshot(nodes=[{"id": "1"}])
    b = WorkspaceSnapshot(nodes=[{"id": "2"}])
    c = WorkspaceSnapshot(nodes=[{"id": "3"}])
    h.push(a)
    h.push(b)
    assert h.can_undo
    restored = h.undo(c)
    assert restored is not None
    assert restored.nodes[0]["id"] == "2"
    assert h.redo(WorkspaceSnapshot()).nodes[0]["id"] == "3"


def test_auto_route():
    pts = auto_route_points({"x": 0, "y": 0}, {"x": 100, "y": 50})
    assert len(pts) == 4
    assert pts[0]["x"] == 0
    assert pts[-1]["x"] == 100


def test_search_catalog_category():
    items = search_catalog(category="actuators")
    assert any(i["component_id"] == "servo" for i in items)
    items = search_catalog(category="robotics")
    assert any(i["component_id"] == "stepper" for i in items)


def test_device_mode_and_serial(tmp_path):
    svc = LabWorkspaceService(storage=LabWorkspaceStorage(tmp_path))
    wid = svc.create(name="Modes")["workspace_id"]
    node = svc.add_node(wid, component_id="esp32", position={"x": 0, "y": 0})
    updated = svc.update_node(wid, node["id"], {"device_mode": "physical", "available": False})
    assert updated["device_mode"] == "physical"
    assert updated["available"] is False
    out = svc.send_serial(wid, "HELLO")
    assert out["ok"] is True
    state = svc.get_state(wid)
    assert len(state["serial"]) >= 2


def test_speed_multipliers(tmp_path):
    svc = LabWorkspaceService(storage=LabWorkspaceStorage(tmp_path))
    wid = svc.create(name="Speed")["workspace_id"]
    svc.add_node(wid, component_id="soil-moisture", position={"x": 0, "y": 0})
    svc.run(wid, speed="10x")
    state = svc.step(wid, 100)
    assert state["sim_time_ms"] == 1000
    assert state["adc_samples"]


def test_list_workspaces(tmp_path):
    svc = LabWorkspaceService(storage=LabWorkspaceStorage(tmp_path))
    svc.create(name="A")
    svc.create(name="B")
    assert len(svc.list_workspaces()) == 2


def test_disconnect(tmp_path):
    svc = LabWorkspaceService(storage=LabWorkspaceStorage(tmp_path))
    wid = svc.create(name="D")["workspace_id"]
    svc.connect(wid)
    state = svc.disconnect(wid)
    assert state["status"] == "stopped"


def test_persistence_file(tmp_path):
    storage = LabWorkspaceStorage(tmp_path)
    storage.save("WSABC", {"workspace_id": "WSABC", "name": "Saved"})
    loaded = storage.load("WSABC")
    assert loaded is not None
    assert loaded["name"] == "Saved"
    assert "WSABC" in storage.list_ids()
