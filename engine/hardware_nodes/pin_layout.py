"""Live pin state and layout models for hardware nodes."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class PinKind(str, Enum):
    GPIO = "GPIO"
    ADC = "ADC"
    DAC = "DAC"
    PWM = "PWM"
    UART = "UART"
    SPI = "SPI"
    I2C = "I2C"
    POWER = "POWER"
    GROUND = "GROUND"


class PinLogicState(str, Enum):
    HIGH = "HIGH"
    LOW = "LOW"
    PWM = "PWM"
    FLOATING = "FLOATING"
    UNKNOWN = "UNKNOWN"


@dataclass
class LivePinState:
    """Realtime electrical / logic state for a single pin."""

    logic: PinLogicState = PinLogicState.UNKNOWN
    value: int = 0
    voltage: float = 0.0
    frequency_hz: float = 0.0
    duty_cycle: float = 0.0
    timestamp_ms: int = field(default_factory=lambda: int(time.time() * 1000))

    def to_dict(self) -> dict[str, Any]:
        return {
            "logic": self.logic.value,
            "value": self.value,
            "voltage": self.voltage,
            "frequency_hz": self.frequency_hz,
            "duty_cycle": self.duty_cycle,
            "timestamp_ms": self.timestamp_ms,
            "state": self.logic.value,  # alias for UI
        }

    @classmethod
    def from_gpio(cls, value: int, *, voltage_v: float = 3.3) -> "LivePinState":
        high = bool(value)
        return cls(
            logic=PinLogicState.HIGH if high else PinLogicState.LOW,
            value=1 if high else 0,
            voltage=voltage_v if high else 0.0,
            timestamp_ms=int(time.time() * 1000),
        )


@dataclass
class HardwarePinDef:
    """Static pin definition with live state."""

    name: str
    number: int | str
    pin_type: str  # GPIO, ADC, ...
    supports_input: bool = True
    supports_output: bool = True
    voltage: float = 3.3
    x: float = 0.0  # 0..1 normalized for silhouette
    y: float = 0.0
    side: str = "left"
    interfaces: list[str] = field(default_factory=list)
    state: LivePinState = field(default_factory=LivePinState)

    @property
    def pin_id(self) -> str:
        return self.name

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "pin_id": self.name,
            "number": self.number,
            "type": self.pin_type,
            "pin_type": self.pin_type,
            "supports_input": self.supports_input,
            "supports_output": self.supports_output,
            "voltage": self.voltage,
            "x": self.x,
            "y": self.y,
            "side": self.side,
            "interfaces": list(self.interfaces) or [self.pin_type.lower()],
            "state": self.state.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HardwarePinDef":
        state_raw = data.get("state")
        state = LivePinState()
        if isinstance(state_raw, dict):
            logic = str(state_raw.get("logic") or state_raw.get("state") or "UNKNOWN")
            try:
                state.logic = PinLogicState(logic)
            except ValueError:
                state.logic = PinLogicState.UNKNOWN
            state.value = int(state_raw.get("value") or 0)
            state.voltage = float(state_raw.get("voltage") or 0.0)
            state.frequency_hz = float(state_raw.get("frequency_hz") or 0.0)
            state.duty_cycle = float(state_raw.get("duty_cycle") or 0.0)
            state.timestamp_ms = int(state_raw.get("timestamp_ms") or time.time() * 1000)
        pin_type = str(data.get("type") or data.get("pin_type") or "GPIO").upper()
        return cls(
            name=str(data.get("name") or data.get("pin_id") or ""),
            number=data.get("number", 0),
            pin_type=pin_type,
            supports_input=bool(data.get("supports_input", True)),
            supports_output=bool(data.get("supports_output", pin_type not in ("POWER", "GROUND", "ADC"))),
            voltage=float(data.get("voltage") or 3.3),
            x=float(data.get("x") or 0.0),
            y=float(data.get("y") or 0.0),
            side=str(data.get("side") or "left"),
            interfaces=list(data.get("interfaces") or []),
            state=state,
        )


# UI color map (documented for dashboard)
PIN_COLORS: dict[str, str] = {
    "GPIO": "#2563eb",
    "ADC": "#16a34a",
    "DAC": "#15803d",
    "PWM": "#7c3aed",
    "UART": "#ea580c",
    "SPI": "#06b6d4",
    "I2C": "#ca8a04",
    "POWER": "#dc2626",
    "GROUND": "#374151",
}
