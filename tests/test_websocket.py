"""Sprint 22 — WebSocket event stream tests."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.seed import seed_experiments
from engine.events.dashboard_publisher import DashboardEventType


@pytest.fixture
def client(tmp_path):
    seed_experiments(tmp_path)
    app = create_app(data_dir=tmp_path)
    with TestClient(app) as test_client:
        yield test_client


def _receive_until(ws, event_type: str, max_reads: int = 30) -> dict:
    for _ in range(max_reads):
        data = json.loads(ws.receive_text())
        if data.get("event_type") == event_type:
            return data
    raise AssertionError(f"event {event_type} not received within {max_reads} reads")


class TestWebSocketEvents:
    def test_websocket_receives_published_event(self, client):
        publisher = client.app.state.publisher
        with client.websocket_connect("/ws/events") as ws:
            publisher.publish(
                DashboardEventType.SYNC_STARTED,
                experiment_id="EXP_TEST01",
                payload={"name": "test"},
            )
            data = _receive_until(ws, "SYNC_STARTED")
            assert data["experiment_id"] == "EXP_TEST01"

    def test_websocket_receives_history_on_connect(self, client):
        publisher = client.app.state.publisher
        publisher.publish(
            DashboardEventType.DEVICE_CONNECTED,
            device_id="esp32_a",
        )
        with client.websocket_connect("/ws/events") as ws:
            data = _receive_until(ws, "DEVICE_CONNECTED")
            assert data["device_id"] == "esp32_a"

    def test_all_event_types_publish(self, client):
        publisher = client.app.state.publisher
        with client.websocket_connect("/ws/events") as ws:
            for event_type in DashboardEventType:
                publisher.publish(event_type, experiment_id="EXP_ALL", device_id="dev1")
                data = _receive_until(ws, event_type.value)
                assert data["event_type"] == event_type.value
