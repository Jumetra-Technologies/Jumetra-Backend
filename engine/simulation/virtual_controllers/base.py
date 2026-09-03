"""Virtual microcontroller base — GPIO, ADC, PWM, UART, I2C."""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Optional

from engine.events.event_bus import EventBus

from ..events import SimulationEventType, publish_simulation_event


class PinMode(str, Enum):
    INPUT = "input"
    OUTPUT = "output"
    INPUT_PULLUP = "input_pullup"
    ANALOG = "analog"
    PWM = "pwm"


class VirtualMicrocontroller(ABC):
    """Simulated microcontroller with peripheral support."""

    controller_id: str = ""

    def __init__(
        self,
        *,
        event_bus: Optional[EventBus] = None,
        laboratory_id: str = "",
    ) -> None:
        self.event_bus = event_bus
        self.laboratory_id = laboratory_id
        self._gpio: dict[str, int] = {}
        self._pin_modes: dict[str, PinMode] = {}
        self._pwm: dict[str, float] = {}
        self._i2c_devices: dict[int, dict[str, Any]] = {}
        self._uart_buffer: list[str] = []
        self._init_pins()

    @abstractmethod
    def _init_pins(self) -> None:
        """Initialize default pin map for this board."""

    @property
    @abstractmethod
    def digital_pin_count(self) -> int:
        pass

    @property
    @abstractmethod
    def analog_pin_count(self) -> int:
        pass

    def pin_mode(self, pin: str, mode: PinMode) -> None:
        self._pin_modes[pin] = mode
        if pin not in self._gpio:
            self._gpio[pin] = 0

    def digital_write(self, pin: str, value: int) -> None:
        old = self._gpio.get(pin, 0)
        self._gpio[pin] = 1 if value else 0
        if old != self._gpio[pin]:
            self._emit_gpio(pin, self._gpio[pin])

    def digital_read(self, pin: str) -> int:
        return self._gpio.get(pin, 0)

    def analog_read(self, pin: str) -> int:
        return min(1023, max(0, self._gpio.get(pin, 0) * 4))

    def pwm_write(self, pin: str, duty: float) -> None:
        duty_clamped = max(0.0, min(1.0, float(duty)))
        self._pwm[pin] = duty_clamped
        self._gpio[pin] = int(duty_clamped * 255)
        self._emit_gpio(pin, self._gpio[pin], pwm=duty_clamped)

    def uart_write(self, data: str) -> None:
        self._uart_buffer.append(data)

    def uart_read(self) -> str:
        return self._uart_buffer.pop(0) if self._uart_buffer else ""

    def i2c_write(self, address: int, data: bytes) -> None:
        self._i2c_devices.setdefault(address, {})["last_write"] = data.hex()

    def i2c_read(self, address: int, length: int = 1) -> bytes:
        dev = self._i2c_devices.get(address, {})
        return bytes.fromhex(dev.get("last_write", "00")[: length * 2] or "00")

    def to_dict(self) -> dict[str, Any]:
        return {
            "controller_id": self.controller_id,
            "gpio": dict(self._gpio),
            "pin_modes": {k: v.value for k, v in self._pin_modes.items()},
            "pwm": dict(self._pwm),
            "digital_pin_count": self.digital_pin_count,
            "analog_pin_count": self.analog_pin_count,
        }

    def _emit_gpio(self, pin: str, value: int, pwm: Optional[float] = None) -> None:
        if self.event_bus is None:
            return
        payload: dict[str, Any] = {"pin": pin, "value": value, "controller_id": self.controller_id}
        if pwm is not None:
            payload["pwm"] = pwm
        publish_simulation_event(
            self.event_bus,
            SimulationEventType.GPIO_CHANGE,
            source=self.controller_id,
            payload=payload,
            laboratory_id=self.laboratory_id,
        )


def create_virtual_controller(
    controller_id: str,
    *,
    event_bus: Optional[EventBus] = None,
    laboratory_id: str = "",
) -> VirtualMicrocontroller:
    from .arduino_uno import VirtualArduinoUno
    from .esp32 import VirtualESP32
    from .stm32 import VirtualSTM32

    mapping = {
        "arduino-uno": VirtualArduinoUno,
        "arduino-mega": VirtualArduinoUno,
        "esp32": VirtualESP32,
        "esp8266": VirtualESP32,
        "raspberry-pi-pico": VirtualArduinoUno,
        "stm32": VirtualSTM32,
    }
    cls = mapping.get(controller_id)
    if cls is None:
        raise KeyError(f"unsupported virtual controller: {controller_id}")
    return cls(event_bus=event_bus, laboratory_id=laboratory_id)
