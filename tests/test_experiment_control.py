"""Sprint 22 — experiment control API tests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import create_app


@pytest.fixture
def client(tmp_path):
    app = create_app(data_dir=tmp_path)
    with TestClient(app) as test_client:
        yield test_client


class TestExperimentControl:
    def test_start_experiment(self, client):
        resp = client.post(
            "/experiments/start",
            json={
                "name": "live_sync_test",
                "devices": ["esp32_a", "esp32_b"],
                "strategy": "adaptive",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "running"
        assert body["strategy"] == "adaptive"
        assert len(body["devices"]) == 2
        exp_id = body["experiment_id"]

        status = client.get(f"/experiments/{exp_id}/status")
        assert status.status_code == 200
        assert status.json()["status"] == "running"

    def test_pause_experiment(self, client):
        start = client.post(
            "/experiments/start",
            json={"name": "pause_test", "devices": ["esp32_a"]},
        ).json()
        exp_id = start["experiment_id"]

        pause = client.post(f"/experiments/{exp_id}/pause")
        assert pause.status_code == 200
        assert pause.json()["status"] == "paused"

    def test_stop_experiment(self, client):
        start = client.post(
            "/experiments/start",
            json={"name": "stop_test", "devices": ["esp32_a"]},
        ).json()
        exp_id = start["experiment_id"]

        stop = client.post(f"/experiments/{exp_id}/stop")
        assert stop.status_code == 200
        assert stop.json()["status"] == "completed"

        exported = client.get(f"/experiments/{exp_id}")
        assert exported.status_code == 200

    def test_pause_not_running_fails(self, client):
        start = client.post(
            "/experiments/start",
            json={"name": "fail_test", "devices": []},
        ).json()
        exp_id = start["experiment_id"]
        client.post(f"/experiments/{exp_id}/stop")

        resp = client.post(f"/experiments/{exp_id}/pause")
        assert resp.status_code == 400

    def test_status_not_found(self, client):
        resp = client.get("/experiments/EXP_MISSING/status")
        assert resp.status_code == 404


class TestWorkspaceAPI:
    def test_list_projects(self, client):
        resp = client.get("/workspace/projects")
        assert resp.status_code == 200
        projects = resp.json()
        assert len(projects) >= 1
        assert "name" in projects[0]

    def test_get_project_detail(self, client):
        projects = client.get("/workspace/projects").json()
        project_id = projects[0]["id"]
        resp = client.get(f"/workspace/projects/{project_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert "experiments" in body
        assert "datasets" in body
        assert "reports" in body

    def test_project_not_found(self, client):
        resp = client.get("/workspace/projects/missing-id")
        assert resp.status_code == 404
