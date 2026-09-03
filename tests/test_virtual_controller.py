"""Sprint 24 — virtual microcontroller tests."""

from __future__ import annotations

import pytest

from engine.events.event import Event
from engine.events.event_bus import EventBus
from engine.events.subscriber import EventSubscriber
from engine.simulation.events import SimulationEventType
from engine.simulation.virtual_controllers.arduino_uno import VirtualArduinoUno
from engine.simulation.virtual_controllers.base import PinMode, create_virtual_controller
from engine.simulation.virtual_controllers.esp32 import VirtualESP32
from engine.simulation.virtual_controllers.stm32 import VirtualSTM32


@pytest.fixture
def bus():
    return EventBus()


class _Recorder(EventSubscriber):
    def __init__(self) -> None:
        self.received: list[Event] = []

    def handle_event(self, event: Event) -> None:
        self.received.append(event)


class TestVirtualMicrocontrollers:
    def test_esp32_pin_count(self, bus):
        mcu = VirtualESP32(event_bus=bus, laboratory_id="LAB001")
        assert mcu.digital_pin_count == 34
        assert mcu.analog_pin_count == 18
        assert "GPIO0" in mcu.to_dict()["gpio"]

    def test_arduino_uno_gpio(self, bus):
        mcu = VirtualArduinoUno(event_bus=bus)
        mcu.pin_mode("D13", PinMode.OUTPUT)
        mcu.digital_write("D13", 1)
        assert mcu.digital_read("D13") == 1

    def test_stm32_pwm_and_analog(self, bus):
        mcu = VirtualSTM32(event_bus=bus)
        mcu.pwm_write("PA0", 0.5)
        assert mcu.to_dict()["pwm"]["PA0"] == 0.5
        assert mcu.analog_read("PA0") > 0

    def test_uart_buffer(self, bus):
        mcu = VirtualESP32(event_bus=bus)
        mcu.uart_write("hello")
        assert mcu.uart_read() == "hello"

    def test_i2c_read_write(self, bus):
        mcu = VirtualArduinoUno(event_bus=bus)
        mcu.i2c_write(0x27, b"\x01\x02")
        data = mcu.i2c_read(0x27, 2)
        assert len(data) == 2

    def test_gpio_change_event(self, bus):
        recorder = _Recorder()
        bus.register_subscriber(recorder)
        mcu = create_virtual_controller("esp32", event_bus=bus, laboratory_id="LAB001")
        mcu.pin_mode("GPIO2", PinMode.OUTPUT)
        mcu.digital_write("GPIO2", 1)
        assert any(e.event_type == SimulationEventType.GPIO_CHANGE for e in recorder.received)

    @pytest.mark.parametrize("controller_id", ["esp32", "arduino-uno", "stm32"])
    def test_factory_creates_controllers(self, bus, controller_id):
        mcu = create_virtual_controller(controller_id, event_bus=bus)
        assert mcu.controller_id
        assert mcu.digital_pin_count > 0

    def test_unsupported_controller_raises(self, bus):
        with pytest.raises(KeyError):
            create_virtual_controller("unknown-board", event_bus=bus)
