"""Registry load + /components/search regression tests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from engine.components.paths import resolve_components_dir
from engine.components.registry import ComponentSearch, default_registry


@pytest.fixture
def client(tmp_path):
    app = create_app(data_dir=tmp_path)
    with TestClient(app) as test_client:
        yield test_client


def test_resolve_components_dir_absolute_and_populated():
    path = resolve_components_dir()
    assert path.is_absolute()
    assert path.is_dir()
    assert len(list(path.glob("*.json"))) >= 30


def test_registry_loads_more_than_30_components():
    registry = default_registry()
    assert len(registry.list_all()) > 30


def test_search_esp32_returns_result():
    registry = default_registry()
    hits = ComponentSearch(registry).search("ESP32")
    ids = {h.component.component_id for h in hits}
    assert "esp32" in ids


def test_search_temperature_returns_dht_sensors():
    registry = default_registry()
    hits = ComponentSearch(registry).search("temperature")
    ids = {h.component.component_id for h in hits}
    assert "dht11" in ids or "dht22" in ids
    assert any(i.startswith("dht") or i == "am2302" for i in ids)


def test_category_filtering_works():
    registry = default_registry()
    sensors = ComponentSearch(registry).search("", category="sensor")
    assert sensors
    assert all(h.component.category in {"sensor", "sensors"} for h in sensors)
    mcus = ComponentSearch(registry).search("", category="mcu")
    assert mcus
    assert any(h.component.component_id == "esp32" for h in mcus)


def test_components_debug_endpoint(client):
    resp = client.get("/components/debug")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_components"] > 30
    assert isinstance(body["categories"], list)
    assert len(body["sample_components"]) >= 1
    assert body["components_dir"]


def test_components_search_api_esp32(client):
    resp = client.get("/components/search", params={"q": "ESP32"})
    assert resp.status_code == 200
    data = resp.json()
    assert data
    ids = {item["component"]["component_id"] for item in data}
    assert "esp32" in ids


def test_components_search_api_temperature(client):
    resp = client.get("/components/search", params={"q": "temperature"})
    assert resp.status_code == 200
    ids = {item["component"]["component_id"] for item in resp.json()}
    assert "dht22" in ids or "dht11" in ids
