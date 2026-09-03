"""Sprint 24 — virtual sensor behavior tests."""

from __future__ import annotations

import pytest

from engine.events.event_bus import EventBus
from engine.events.subscriber import EventSubscriber
from engine.events.event import Event
from engine.simulation.behaviors.sensors import (
    DHT11Sensor,
    DHT22Sensor,
    HCSR04Sensor,
    PIRSensor,
    SoilMoistureSensor,
    SENSOR_BEHAVIORS,
)
from engine.simulation.events import SimulationEventType


@pytest.fixture
def bus():
    b = EventBus()
    return b


class _Recorder(EventSubscriber):
    def __init__(self) -> None:
        self.received: list[Event] = []

    def handle_event(self, event: Event) -> None:
        self.received.append(event)


class TestVirtualSensors:
    @pytest.mark.parametrize(
        "component_id,cls",
        [
            ("dht11", DHT11Sensor),
            ("dht22", DHT22Sensor),
            ("hc-sr04", HCSR04Sensor),
            ("pir", PIRSensor),
            ("soil-moisture", SoilMoistureSensor),
        ],
    )
    def test_sensor_generates_data(self, bus, component_id, cls):
        sensor = cls("INST001", event_bus=bus, laboratory_id="LAB001")
        reading = sensor.tick(100, 1000)
        assert reading
        assert sensor.state["last_reading"] == reading
        assert sensor.read() == reading

    def test_dht11_temperature_range(self, bus):
        sensor = DHT11Sensor("INST001", event_bus=bus)
        reading = sensor.tick(100, 5000)
        assert 15.0 <= reading["temperature_c"] <= 30.0
        assert 30.0 <= reading["humidity_pct"] <= 70.0

    def test_pir_motion_toggles(self, bus):
        sensor = PIRSensor("INST001", event_bus=bus)
        r1 = sensor.tick(100, 0)
        r2 = sensor.tick(100, 3500)
        assert isinstance(r1["motion_detected"], bool)
        assert r1["motion_detected"] != r2["motion_detected"]

    def test_sensor_publishes_events(self, bus):
        recorder = _Recorder()
        bus.register_subscriber(recorder)
        sensor = DHT22Sensor("INST001", event_bus=bus, laboratory_id="LAB001")
        sensor.tick(100, 2000)
        assert any(e.event_type == SimulationEventType.SENSOR_DATA for e in recorder.received)

    def test_all_catalog_sensors_registered(self):
        expected = {"dht11", "dht22", "hc-sr04", "pir", "soil-moisture"}
        assert expected == set(SENSOR_BEHAVIORS.keys())
