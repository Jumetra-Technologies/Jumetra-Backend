"""Virtual Arduino Uno microcontroller."""

from __future__ import annotations

from .base import PinMode, VirtualMicrocontroller


class VirtualArduinoUno(VirtualMicrocontroller):
    controller_id = "arduino-uno"

    def _init_pins(self) -> None:
        for i in range(14):
            pin = f"D{i}"
            self._gpio[pin] = 0
            self._pin_modes[pin] = PinMode.INPUT
        for i in range(6):
            pin = f"A{i}"
            self._gpio[pin] = 0
            self._pin_modes[pin] = PinMode.ANALOG

    @property
    def digital_pin_count(self) -> int:
        return 14

    @property
    def analog_pin_count(self) -> int:
        return 6
