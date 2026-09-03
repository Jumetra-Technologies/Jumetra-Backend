"""Sprint 25 — hybrid experiment session and bridge tests."""

from __future__ import annotations

import pytest

from engine.components import default_registry
from engine.controllers import default_controller_registry
from engine.events.event import Event
from engine.events.event_bus import EventBus
from engine.events.subscriber import EventSubscriber
from engine.hybrid import (
    DeviceAssignment,
    HybridBridgeService,
    HybridDeviceMode,
    HybridExperimentSession,
    HybridStorage,
    WokwiAdapter,
)
from engine.hybrid.events import HybridEventType


class _Recorder(EventSubscriber):
    def __init__(self) -> None:
        self.received: list[Event] = []

    def handle_event(self, event: Event) -> None:
        self.received.append(event)


@pytest.fixture
def bridge(tmp_path):
    return HybridBridgeService(
        default_registry(),
        default_controller_registry(),
        storage=HybridStorage(tmp_path),
        event_bus=EventBus(),
    )


class TestHybridExperimentSession:
    def test_session_tracks_events(self):
        session = HybridExperimentSession.create(
            name="Test",
            component_ids=["dht11", "led"],
            assignments=[
                DeviceAssignment(component_id="dht11", mode=HybridDeviceMode.VIRTUAL, available=True),
                DeviceAssignment(component_id="led", mode=HybridDeviceMode.PHYSICAL, available=False),
            ],
        )
        session.record_physical({"pin": "D2", "value": 1}, latency_ms=12.5)
        session.record_virtual({"event": "SENSOR_DATA"})
        session.record_simulation({"tick": 1})
        assert session.event_counts()["physical"] == 1
        assert session.missing_components(["dht11", "led"]) == ["led"]
        assert session.average_latency_ms() == 12.5


class TestHybridBridge:
    def test_create_experiment(self, bridge):
        project = bridge.create_experiment(
            name="Hybrid Lab",
            controller_id="esp32",
            component_ids=["dht22", "led"],
            device_modes={"dht22": "virtual", "led": "virtual"},
        )
        assert project["experiment_id"].startswith("HYB")
        assert project["laboratory_id"].startswith("LAB")
        assert len(project["assignments"]) == 2

    def test_lifecycle(self, bridge):
        project = bridge.create_experiment(
            name="Lifecycle",
            controller_id="arduino-uno",
            component_ids=["dht11"],
        )
        exp_id = project["experiment_id"]
        start = bridge.start(exp_id)
        assert start["status"] == "running"
        advance = bridge.advance(exp_id, 100)
        assert advance["state"]["event_counts"]["simulation"] >= 1
        stop = bridge.stop(exp_id)
        assert stop["status"] == "stopped"

    def test_publishes_binding_event(self, bridge):
        bus = bridge.event_bus
        recorder = _Recorder()
        bus.register_subscriber(recorder)
        bridge.create_experiment(
            name="Events",
            controller_id="esp32",
            component_ids=["led"],
        )
        assert any(e.event_type == HybridEventType.HYBRID_BINDING_CREATED for e in recorder.received)

    def test_wokwi_stub(self):
        wokwi = WokwiAdapter()
        wokwi.connect()
        wokwi.load_circuit({"nodes": []})
        assert wokwi.step(10)["stub"] is True

    def test_persistence(self, bridge, tmp_path):
        project = bridge.create_experiment(
            name="Persist",
            controller_id="esp32",
            component_ids=["relay"],
        )
        storage = HybridStorage(tmp_path)
        assert storage.load_project(project["experiment_id"]) is not None
        assert storage.load_assignments(project["experiment_id"]) is not None
        assert storage.load_mappings(project["experiment_id"]) is not None
