"""Sprint 26 — engineering workspace API tests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import create_app


@pytest.fixture
def client(tmp_path):
    app = create_app(data_dir=tmp_path)
    with TestClient(app) as test_client:
        yield test_client


class TestWorkspaceAPI:
    def test_catalog(self, client):
        resp = client.get("/engineering/workspace/catalog")
        assert resp.status_code == 200
        body = resp.json()
        assert "esp32" in body["categories"]
        assert "sensors" in body["categories"]
        assert "ai-modules" in body["categories"]
        assert "robotics" in body["categories"]
        assert "marketplace" in body["categories"]
        assert len(body["items"]) >= 20

    def test_catalog_search(self, client):
        resp = client.get("/engineering/workspace/catalog", params={"q": "dht"})
        assert resp.status_code == 200
        ids = [i["component_id"] for i in resp.json()["items"]]
        assert "dht11" in ids

    def test_create_connect_run_step(self, client):
        created = client.post("/engineering/workspace", json={"name": "Lab A"}).json()
        wid = created["workspace_id"]
        assert wid.startswith("WS")

        assert client.post(f"/engineering/workspace/{wid}/connect").status_code == 200
        node = client.post(
            f"/engineering/workspace/{wid}/nodes",
            json={"component_id": "dht11", "position": {"x": 10, "y": 20}, "device_mode": "virtual"},
        ).json()
        assert node["component_id"] == "dht11"

        led = client.post(
            f"/engineering/workspace/{wid}/nodes",
            json={"component_id": "led", "position": {"x": 200, "y": 20}},
        ).json()

        wire = client.post(
            f"/engineering/workspace/{wid}/wires",
            json={"source": node["id"], "target": led["id"], "protocol": "digital"},
        ).json()
        assert wire["id"].startswith("W")

        assert client.post(f"/engineering/workspace/{wid}/run", json={"speed": "2x"}).status_code == 200
        stepped = client.post(f"/engineering/workspace/{wid}/step", json={"delta_ms": 100}).json()
        assert stepped["tick_count"] >= 1
        assert stepped["canvas"]["nodes"]

        state = client.get(f"/engineering/workspace/{wid}/state").json()
        assert "inspector" in state
        assert "serial" in state

        assert client.post(f"/engineering/workspace/{wid}/pause").status_code == 200
        assert client.post(f"/engineering/workspace/{wid}/reset").status_code == 200

    def test_undo_redo(self, client):
        wid = client.post("/engineering/workspace", json={"name": "Undo"}).json()["workspace_id"]
        client.post(
            f"/engineering/workspace/{wid}/nodes",
            json={"component_id": "relay", "position": {"x": 0, "y": 0}},
        )
        client.post(f"/engineering/workspace/{wid}/undo")
        state = client.get(f"/engineering/workspace/{wid}/state").json()
        assert state["node_count"] == 0
        client.post(f"/engineering/workspace/{wid}/redo")
        state = client.get(f"/engineering/workspace/{wid}/state").json()
        assert state["node_count"] == 1

    def test_serial_transmit(self, client):
        wid = client.post("/engineering/workspace", json={"name": "Serial"}).json()["workspace_id"]
        resp = client.post(f"/engineering/workspace/{wid}/serial", json={"line": "AT"})
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_unknown_workspace(self, client):
        assert client.get("/engineering/workspace/WSMISSING/state").status_code == 404
