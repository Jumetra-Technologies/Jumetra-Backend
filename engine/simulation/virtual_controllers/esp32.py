"""Virtual ESP32 microcontroller."""

from __future__ import annotations

from .base import PinMode, VirtualMicrocontroller


class VirtualESP32(VirtualMicrocontroller):
    controller_id = "esp32"

    def _init_pins(self) -> None:
        for i in range(34):
            pin = f"GPIO{i}"
            self._gpio[pin] = 0
            self._pin_modes[pin] = PinMode.INPUT

    @property
    def digital_pin_count(self) -> int:
        return 34

    @property
    def analog_pin_count(self) -> int:
        return 18
