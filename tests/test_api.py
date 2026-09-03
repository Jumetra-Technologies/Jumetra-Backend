"""Sprint 21 — FastAPI dashboard bridge tests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.seed import seed_experiments


@pytest.fixture
def client(tmp_path):
    seed_experiments(tmp_path)
    app = create_app(data_dir=tmp_path)
    with TestClient(app) as test_client:
        yield test_client


class TestHealth:
    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestExperimentsAPI:
    def test_list_experiments(self, client):
        resp = client.get("/experiments")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        strategies = {e["strategy"] for e in data}
        assert strategies == {"fixed", "adaptive"}

    def test_get_experiment_detail(self, client):
        resp = client.get("/experiments/EXP_FIXED01")
        assert resp.status_code == 200
        body = resp.json()
        assert body["experiment_id"] == "EXP_FIXED01"
        assert body["strategy"] == "fixed"
        assert "analytics" in body
        assert "report" in body
        assert len(body["sync_measurements"]) == 5

    def test_experiment_not_found(self, client):
        resp = client.get("/experiments/EXP_MISSING")
        assert resp.status_code == 404


class TestDevicesAPI:
    def test_list_devices(self, client):
        resp = client.get("/devices")
        assert resp.status_code == 200
        data = resp.json()
        ids = {d["device_id"] for d in data}
        assert "esp32_a" in ids
        assert "esp32_b" in ids

    def test_get_device_detail(self, client):
        resp = client.get("/devices/esp32_a")
        assert resp.status_code == 200
        body = resp.json()
        assert body["device_id"] == "esp32_a"
        assert body["status"] == "connected"
        assert "metrics" in body
        assert "reliability" in body

    def test_device_not_found(self, client):
        resp = client.get("/devices/unknown_device")
        assert resp.status_code == 404


class TestAnalyticsAPI:
    def test_analytics_overview(self, client):
        resp = client.get("/analytics")
        assert resp.status_code == 200
        body = resp.json()
        assert body["experiment_count"] == 2
        assert body["device_count"] >= 2
        assert body["average_sync_error"] > 0

    def test_dashboard_overview(self, client):
        resp = client.get("/analytics/dashboard")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_experiments"] == 2
        assert body["connected_devices"] >= 2
        assert "latency" in body

    def test_comparison(self, client):
        resp = client.get("/analytics/comparison")
        assert resp.status_code == 200
        body = resp.json()
        assert body["fixed_experiment_id"] == "EXP_FIXED01"
        assert body["adaptive_experiment_id"] == "EXP_ADAPT01"
        assert body["communication_savings"] == 6  # 2 devices × (10 - 7) comm cost units


class TestDataLoading:
    def test_analytics_engine_integration(self, client):
        resp = client.get("/experiments/EXP_ADAPT01")
        report = resp.json()["report"]
        assert report["strategy"] == "adaptive"
        assert report["correction_success_rate"] >= 0

    def test_seed_data_round_trip(self, tmp_path):
        ids = seed_experiments(tmp_path)
        assert len(ids) == 2
        app = create_app(data_dir=tmp_path)
        with TestClient(app) as c:
            assert len(c.get("/experiments").json()) == 2
