"""Microcontroller controller models."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ControllerSpec:
    """Specification for a supported microcontroller board."""

    controller_id: str
    name: str
    family: str
    description: str
    voltage_v: float = 3.3
    clock_mhz: float = 16.0
    flash_kb: int = 32
    ram_kb: int = 2
    digital_pins: int = 14
    analog_pins: int = 6
    pwm_pins: int = 6
    supports_i2c: bool = True
    supports_spi: bool = True
    supports_onewire: bool = False
    supports_wifi: bool = False
    supports_bluetooth: bool = False
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ControllerSpec":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class CompatibilityResult:
    """Result of checking component ↔ controller compatibility."""

    component_id: str
    controller_id: str
    compatible: bool
    score: float
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
