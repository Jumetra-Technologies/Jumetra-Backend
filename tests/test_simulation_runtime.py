"""Sprint 24 — simulation runtime tests."""

from __future__ import annotations

import pytest

from engine.events.event import Event
from engine.events.event_bus import EventBus
from engine.events.subscriber import EventSubscriber
from engine.simulation.events import SimulationEventType
from engine.simulation.runtime.engine import EngineState, SimulationEngine


@pytest.fixture
def bus():
    return EventBus()


class _Recorder(EventSubscriber):
    def __init__(self) -> None:
        self.received: list[Event] = []

    def handle_event(self, event: Event) -> None:
        self.received.append(event)


@pytest.fixture
def sample_circuit():
    return {
        "nodes": [
            {"id": "esp32", "type": "controller", "label": "ESP32", "position": {"x": 250, "y": 50}},
            {
                "id": "VCI001",
                "type": "component",
                "label": "DHT11",
                "component_id": "dht11",
                "position": {"x": 100, "y": 200},
                "pin_map": {"pin_0": "D2"},
            },
            {
                "id": "VCI002",
                "type": "component",
                "label": "LED",
                "component_id": "led",
                "position": {"x": 300, "y": 200},
                "pin_map": {"pin_0": "D3"},
            },
        ],
        "edges": [
            {"id": "e1", "source": "esp32", "target": "VCI001", "label": "D2, pin_0"},
            {"id": "e2", "source": "esp32", "target": "VCI002", "label": "D3, pin_0"},
        ],
    }


@pytest.fixture
def instances():
    return [
        {"instance_id": "VCI001", "component_id": "dht11", "pin_map": {"pin_0": "D2"}},
        {"instance_id": "VCI002", "component_id": "led", "pin_map": {"pin_0": "D3"}},
    ]


class TestSimulationRuntime:
    def test_engine_lifecycle(self, bus, sample_circuit, instances):
        engine = SimulationEngine(
            laboratory_id="LAB001",
            controller_id="esp32",
            component_instances=instances,
            circuit=sample_circuit,
            event_bus=bus,
        )
        assert engine.state == EngineState.CREATED
        engine.start()
        assert engine.state == EngineState.RUNNING
        step = engine.advance_time(100)
        assert step["sim_time_ms"] == 100
        assert len(step["behaviors"]) == 2
        engine.pause()
        assert engine.state == EngineState.PAUSED
        engine.stop()
        assert engine.state == EngineState.STOPPED

    def test_advance_requires_running(self, bus, sample_circuit, instances):
        engine = SimulationEngine(
            laboratory_id="LAB001",
            controller_id="esp32",
            component_instances=instances,
            circuit=sample_circuit,
            event_bus=bus,
        )
        with pytest.raises(RuntimeError):
            engine.advance_time(100)

    def test_actuator_command(self, bus, sample_circuit, instances):
        engine = SimulationEngine(
            laboratory_id="LAB001",
            controller_id="esp32",
            component_instances=instances,
            circuit=sample_circuit,
            event_bus=bus,
        )
        engine.start()
        result = engine.send_actuator_command("VCI002", "on")
        assert result["on"] is True

    def test_simulation_events_published(self, bus, sample_circuit, instances):
        recorder = _Recorder()
        bus.register_subscriber(recorder)
        engine = SimulationEngine(
            laboratory_id="LAB001",
            controller_id="esp32",
            component_instances=instances,
            circuit=sample_circuit,
            event_bus=bus,
        )
        engine.start()
        engine.advance_time(100)
        engine.stop()
        types = {e.event_type for e in recorder.received}
        assert SimulationEventType.SIMULATION_STARTED in types
        assert SimulationEventType.SENSOR_DATA in types
        assert SimulationEventType.SIMULATION_TICK in types
        assert SimulationEventType.SIMULATION_STOPPED in types

    def test_clock_advances(self, bus, sample_circuit, instances):
        engine = SimulationEngine(
            laboratory_id="LAB001",
            controller_id="esp32",
            component_instances=instances,
            circuit=sample_circuit,
            event_bus=bus,
        )
        engine.start()
        engine.advance_time(250)
        engine.advance_time(250)
        state = engine.get_state()
        assert state["sim_time_ms"] == 500
        assert state["tick_count"] == 2
