"""Sprint 24 — virtual actuator behavior tests."""

from __future__ import annotations

import pytest

from engine.events.event import Event
from engine.events.event_bus import EventBus
from engine.events.subscriber import EventSubscriber
from engine.simulation.behaviors.actuators import (
    ACTUATOR_BEHAVIORS,
    LEDActuator,
    RelayActuator,
    ServoActuator,
)
from engine.simulation.events import SimulationEventType


@pytest.fixture
def bus():
    return EventBus()


class _Recorder(EventSubscriber):
    def __init__(self) -> None:
        self.received: list[Event] = []

    def handle_event(self, event: Event) -> None:
        self.received.append(event)


class TestVirtualActuators:
    def test_led_on_off(self, bus):
        led = LEDActuator("LED001", event_bus=bus)
        led.command("on")
        assert led.state["on"] is True
        assert led.state["brightness"] == 255
        led.command("off")
        assert led.state["on"] is False

    def test_led_brightness(self, bus):
        led = LEDActuator("LED001", event_bus=bus)
        led.command("brightness", 128)
        assert led.state["brightness"] == 128
        assert led.state["on"] is True

    def test_relay_toggle(self, bus):
        relay = RelayActuator("RLY001", event_bus=bus)
        relay.command("close")
        assert relay.state["closed"] is True
        relay.command("toggle")
        assert relay.state["closed"] is False

    def test_servo_angle(self, bus):
        servo = ServoActuator("SRV001", event_bus=bus)
        servo.command("angle", 45)
        assert servo.state["angle_deg"] == 45
        servo.command("angle", 999)
        assert servo.state["angle_deg"] == 180

    def test_actuator_publishes_events(self, bus):
        recorder = _Recorder()
        bus.register_subscriber(recorder)
        led = LEDActuator("LED001", event_bus=bus, laboratory_id="LAB001")
        led.command("on")
        assert any(e.event_type == SimulationEventType.ACTUATOR_UPDATE for e in recorder.received)

    def test_actuator_tick_maintains_state(self, bus):
        servo = ServoActuator("SRV001", event_bus=bus)
        servo.command("angle", 90)
        result = servo.tick(50, 500)
        assert result["state"]["angle_deg"] == 90

    def test_all_catalog_actuators_registered(self):
        expected = {"led", "relay", "servo"}
        assert expected == set(ACTUATOR_BEHAVIORS.keys())
