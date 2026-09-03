"""Virtual STM32 microcontroller."""

from __future__ import annotations

from .base import PinMode, VirtualMicrocontroller


class VirtualSTM32(VirtualMicrocontroller):
    controller_id = "stm32"

    def _init_pins(self) -> None:
        for port in ("A", "B", "C"):
            for i in range(16):
                pin = f"P{port}{i}"
                self._gpio[pin] = 0
                self._pin_modes[pin] = PinMode.INPUT

    @property
    def digital_pin_count(self) -> int:
        return 48

    @property
    def analog_pin_count(self) -> int:
        return 10
