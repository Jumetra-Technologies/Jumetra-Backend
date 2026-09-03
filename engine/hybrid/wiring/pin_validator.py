"""Pin / wire validation rules for interactive hybrid wiring."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .pin_connection import PinEndpoint, WireType


POWER_TYPES = frozenset({"POWER", "VCC", "VDD", "3V3", "5V", "VIN"})
GROUND_TYPES = frozenset({"GROUND", "GND", "AGND"})
COMM_TYPES = frozenset({"UART", "SPI", "I2C", "CAN", "USB"})
OUTPUT_ONLY_HINTS = frozenset({"TX", "SDO", "MOSI", "SDA_OUT"})
INPUT_ONLY_HINTS = frozenset({"RX", "SDI", "MISO"})


@dataclass
class ValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    wire_type: str = WireType.DIGITAL.value

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "valid": self.ok,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "suggestions": list(self.suggestions),
            "wire_type": self.wire_type,
        }


class PinValidator:
    """Reject illegal wires; warn on voltage / protocol mismatches."""

    def validate(
        self,
        source: PinEndpoint,
        destination: PinEndpoint,
        *,
        requested_wire_type: str = "",
    ) -> ValidationResult:
        result = ValidationResult(ok=True)
        src_t = source.pin_type.upper()
        dst_t = destination.pin_type.upper()
        src_name = source.pin.upper()
        dst_name = destination.pin.upper()

        if source.device_id == destination.device_id and source.pin == destination.pin:
            result.errors.append("Cannot connect a pin to itself")
            result.ok = False
            return result

        # GPIO → 5V / POWER reject
        if self._is_signal(src_t) and self._is_power(dst_t, dst_name):
            result.errors.append(f"Reject: {source.pin} ({src_t}) → power rail ({destination.pin})")
            result.ok = False
        if self._is_signal(dst_t) and self._is_power(src_t, src_name):
            # Power → GPIO is allowed for supply; warn only if both power? handled below
            if self._is_signal(dst_t) and not destination.supports_input:
                result.errors.append(f"Reject: power → non-input pin {destination.pin}")
                result.ok = False

        if self._is_power(src_t, src_name) and self._is_ground(dst_t, dst_name):
            result.errors.append("Reject: power → ground short")
            result.ok = False
        if self._is_ground(src_t, src_name) and self._is_power(dst_t, dst_name):
            result.errors.append("Reject: ground → power short")
            result.ok = False

        # UART TX → UART TX
        if self._is_uart_tx(src_name, src_t) and self._is_uart_tx(dst_name, dst_t):
            result.errors.append("Reject: UART TX → UART TX")
            result.ok = False
        if self._is_uart_rx(src_name, src_t) and self._is_uart_rx(dst_name, dst_t):
            result.errors.append("Reject: UART RX → UART RX")
            result.ok = False

        # Output → Output
        if (
            source.supports_output
            and not source.supports_input
            and destination.supports_output
            and not destination.supports_input
            and self._is_signal(src_t)
            and self._is_signal(dst_t)
        ):
            result.errors.append("Reject: output → output")
            result.ok = False

        # Voltage warn 3.3 ↔ 5
        if abs(source.voltage - destination.voltage) >= 1.0:
            result.warnings.append(
                f"Voltage mismatch: {source.voltage}V ↔ {destination.voltage}V"
            )
            result.suggestions.append("Use a level shifter")

        # Protocol family checks
        inferred = self._infer_wire_type(source, destination, requested_wire_type)
        result.wire_type = inferred

        if src_t in COMM_TYPES and dst_t in COMM_TYPES and src_t != dst_t:
            result.warnings.append(f"Protocol mismatch: {src_t} ↔ {dst_t}")
            result.suggestions.append(f"Prefer matching {src_t} peers or a bridge")

        if src_t == "PWM" and dst_t == "ADC":
            result.warnings.append("PWM → ADC may need filtering / RC network")
        if src_t == "DAC" and dst_t not in ("ADC", "ANALOG", "GPIO"):
            result.warnings.append("DAC typically drives analog / ADC inputs")

        # SPI / I2C / UART / CAN / USB accepted when inferred
        if inferred in {"spi", "i2c", "uart", "can", "usb", "pwm", "analog", "digital"}:
            pass

        if not source.available or not destination.available:
            result.warnings.append("Waiting for hardware on one or both endpoints")

        return result

    def compatible(
        self,
        source: PinEndpoint,
        destination: PinEndpoint,
    ) -> bool:
        return self.validate(source, destination).ok

    @staticmethod
    def _is_power(pin_type: str, name: str) -> bool:
        return pin_type in POWER_TYPES or name in POWER_TYPES or name in {"5V", "3V3", "VIN"}

    @staticmethod
    def _is_ground(pin_type: str, name: str) -> bool:
        return pin_type in GROUND_TYPES or name in GROUND_TYPES or "GND" in name

    @staticmethod
    def _is_signal(pin_type: str) -> bool:
        return pin_type in {
            "GPIO", "ADC", "DAC", "PWM", "UART", "SPI", "I2C", "CAN", "DIGITAL", "ANALOG"
        }

    @staticmethod
    def _is_uart_tx(name: str, pin_type: str) -> bool:
        return pin_type == "UART" and ("TX" in name or name.endswith("TX"))

    @staticmethod
    def _is_uart_rx(name: str, pin_type: str) -> bool:
        return pin_type == "UART" and ("RX" in name or name.endswith("RX"))

    def _infer_wire_type(
        self,
        source: PinEndpoint,
        destination: PinEndpoint,
        requested: str,
    ) -> str:
        if requested:
            return requested.lower()
        src_t = source.pin_type.upper()
        dst_t = destination.pin_type.upper()
        if self._is_power(src_t, source.pin.upper()) or self._is_power(dst_t, destination.pin.upper()):
            return WireType.POWER.value
        if self._is_ground(src_t, source.pin.upper()) or self._is_ground(dst_t, destination.pin.upper()):
            return WireType.GROUND.value
        for proto in ("UART", "SPI", "I2C", "CAN", "USB", "PWM"):
            if src_t == proto or dst_t == proto:
                return proto.lower()
        if src_t in ("ADC", "DAC", "ANALOG") or dst_t in ("ADC", "DAC", "ANALOG"):
            return WireType.ANALOG.value
        kinds = {source.device_kind, destination.device_kind}
        if "physical" in kinds and ("virtual" in kinds or "simulated" in kinds):
            return WireType.HYBRID.value
        return WireType.DIGITAL.value
