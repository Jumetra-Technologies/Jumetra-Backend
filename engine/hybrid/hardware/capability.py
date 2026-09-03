"""Capability model for universal hardware devices."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class CapabilityKind(str, Enum):
    GPIO = "gpio"
    PWM = "pwm"
    ADC = "adc"
    DAC = "dac"
    I2C = "i2c"
    SPI = "spi"
    UART = "uart"
    WIFI = "wifi"
    BLUETOOTH = "bluetooth"
    CAMERA = "camera"
    SSH = "ssh"
    MQTT = "mqtt"
    CAN = "can"
    USB = "usb"


@dataclass
class Capability:
    """A named hardware capability with optional parameters."""

    name: str
    kind: str = ""
    description: str = ""
    params: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.kind:
            self.kind = self.name.lower()

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "description": self.description,
            "params": dict(self.params),
        }

    @classmethod
    def from_dict(cls, data: Any) -> "Capability":
        if isinstance(data, str):
            return cls(name=data, kind=data.lower())
        if isinstance(data, dict):
            return cls(
                name=str(data.get("name") or data.get("kind") or "unknown"),
                kind=str(data.get("kind") or data.get("name") or "").lower(),
                description=str(data.get("description") or ""),
                params=dict(data.get("params") or {}),
            )
        return cls(name=str(data))

    @classmethod
    def from_list(cls, items: Optional[list[Any]]) -> list["Capability"]:
        return [cls.from_dict(item) for item in (items or [])]
