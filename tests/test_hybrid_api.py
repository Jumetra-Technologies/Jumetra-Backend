"""Sprint 25/27 — hybrid bridge API tests."""

from __future__ import annotations

import threading
import time

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from engine.communication.memory_adapter import make_adapter_pair
from engine.hybrid.device_agent import AGENT_EVENT_DEVICE_DISCOVERY
from engine.protocol.messages import MessageType, create_message


@pytest.fixture
def client(tmp_path):
    app = create_app(data_dir=tmp_path)
    with TestClient(app) as test_client:
        yield test_client


def _discovery_message(device_id: str = "esp32_api") -> dict:
    return create_message(
        type_=MessageType.EVENT,
        source=device_id,
        target="hhip",
        sequence=1,
        payload={
            "event": AGENT_EVENT_DEVICE_DISCOVERY,
            "device_id": device_id,
            "board_type": "esp32",
            "capabilities": ["gpio"],
            "pins": [{"pin_id": "D13", "name": "LED", "number": 13, "interfaces": ["gpio"]}],
        },
    )


class TestHybridAPI:
    def test_create_hybrid_experiment(self, client):
        resp = client.post(
            "/hybrid/create",
            json={
                "name": "API Hybrid",
                "controller_id": "esp32",
                "component_ids": ["dht11", "led"],
                "device_modes": {"dht11": "virtual", "led": "simulated"},
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["experiment_id"].startswith("HYB")

    def test_hybrid_lifecycle(self, client):
        create = client.post(
            "/hybrid/create",
            json={
                "name": "Lifecycle",
                "controller_id": "esp32",
                "component_ids": ["dht22"],
            },
        ).json()
        exp_id = create["experiment_id"]
        assert client.post(f"/hybrid/{exp_id}/start").status_code == 200
        assert client.post(f"/hybrid/{exp_id}/advance", json={"delta_ms": 100}).status_code == 200
        assert client.get(f"/hybrid/{exp_id}").status_code == 200
        assert client.post(f"/hybrid/{exp_id}/stop").status_code == 200

    def test_list_physical_devices_empty(self, client):
        resp = client.get("/hybrid/devices")
        assert resp.status_code == 200
        assert resp.json()["count"] == 0

    def test_connect_physical_device_api(self, client):
        engine_side, device_side = make_adapter_pair(timeout=0.2)
        layer = client.app.state.hybrid_service._physical  # noqa: SLF001
        layer._transport_factory = lambda _: engine_side  # noqa: SLF001
        device_side.connect()

        def boot():
            time.sleep(0.05)
            device_side.send(_discovery_message("esp32_api"))

        threading.Thread(target=boot, daemon=True).start()
        resp = client.post(
            "/hybrid/devices/connect",
            json={"port": "COM_API", "board_type": "esp32", "device_id": "esp32_api"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["device_id"] == "esp32_api"

        pins = client.get("/hybrid/devices/esp32_api/pins")
        assert pins.status_code == 200
        assert pins.json()["count"] >= 1

        conn = client.post(
            "/hybrid/connections",
            json={
                "virtual_node_id": "NLED",
                "virtual_pin_id": "in",
                "physical_device_id": "esp32_api",
                "physical_pin_id": "D13",
            },
        )
        assert conn.status_code == 200
        assert conn.json()["valid"] is True

        listed = client.get("/hybrid/connections")
        assert listed.status_code == 200
        assert listed.json()["count"] >= 1

