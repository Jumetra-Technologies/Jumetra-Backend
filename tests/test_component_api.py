"""Sprint 23 — component and laboratory API tests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import create_app


@pytest.fixture
def client(tmp_path):
    app = create_app(data_dir=tmp_path)
    with TestClient(app) as test_client:
        yield test_client


class TestComponentsAPI:
    def test_search_components(self, client):
        resp = client.get("/components/search", params={"q": "dht"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 2
        ids = [item["component"]["component_id"] for item in data]
        assert "dht11" in ids

    def test_search_by_category(self, client):
        resp = client.get("/components/search", params={"category": "sensor"})
        assert resp.status_code == 200
        assert all(item["component"]["category"] == "sensor" for item in resp.json())

    def test_get_component_detail(self, client):
        resp = client.get("/components/dht11")
        assert resp.status_code == 200
        body = resp.json()
        assert body["component"]["name"] == "DHT11"
        assert len(body["compatibility"]) >= 1

    def test_component_not_found(self, client):
        resp = client.get("/components/missing-part")
        assert resp.status_code == 404


class TestControllersAPI:
    def test_list_controllers(self, client):
        resp = client.get("/controllers")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 6
        ids = {c["controller_id"] for c in data}
        assert "esp32" in ids
        assert "arduino-uno" in ids


class TestLaboratoryAPI:
    def test_create_laboratory(self, client):
        resp = client.post(
            "/laboratory/create",
            json={
                "name": "IoT Greenhouse",
                "controller_id": "esp32",
                "component_ids": ["dht22", "soil-moisture", "relay"],
                "description": "Virtual greenhouse simulation",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["laboratory_id"].startswith("LAB")
        assert body["session"]["circuit"]["nodes"]

    def test_start_laboratory(self, client):
        create = client.post(
            "/laboratory/create",
            json={
                "name": "LED Test",
                "controller_id": "arduino-uno",
                "component_ids": ["led"],
            },
        ).json()
        lab_id = create["laboratory_id"]
        resp = client.post(f"/laboratory/{lab_id}/start")
        assert resp.status_code == 200
        assert resp.json()["status"] == "running"

    def test_create_invalid_controller(self, client):
        resp = client.post(
            "/laboratory/create",
            json={"name": "Bad", "controller_id": "unknown", "component_ids": ["led"]},
        )
        assert resp.status_code == 404

    def test_start_unknown_lab(self, client):
        resp = client.post("/laboratory/LABUNKNOWN/start")
        assert resp.status_code == 404


class TestSimulationAPI:
    def _create_lab(self, client):
        return client.post(
            "/laboratory/create",
            json={
                "name": "Sim API Lab",
                "controller_id": "esp32",
                "component_ids": ["dht11", "led"],
            },
        ).json()

    def test_get_simulation_state(self, client):
        lab = self._create_lab(client)
        lab_id = lab["laboratory_id"]
        resp = client.get(f"/laboratory/{lab_id}/simulation")
        assert resp.status_code == 200
        assert resp.json()["laboratory_id"] == lab_id

    def test_simulation_lifecycle(self, client):
        lab = self._create_lab(client)
        lab_id = lab["laboratory_id"]
        assert client.post(f"/laboratory/{lab_id}/start").status_code == 200
        assert client.post(f"/laboratory/{lab_id}/simulation/advance", json={"delta_ms": 100}).json()["status"] == "running"
        assert client.post(f"/laboratory/{lab_id}/simulation/pause").json()["status"] == "paused"
        assert client.post(f"/laboratory/{lab_id}/simulation/stop").json()["status"] == "stopped"

    def test_actuator_command(self, client):
        lab = self._create_lab(client)
        lab_id = lab["laboratory_id"]
        client.post(f"/laboratory/{lab_id}/start")
        instance_id = lab["session"]["components"][1]["instance_id"]
        resp = client.post(
            f"/laboratory/{lab_id}/simulation/command",
            json={"instance_id": instance_id, "action": "on"},
        )
        assert resp.status_code == 200
        assert resp.json()["on"] is True
