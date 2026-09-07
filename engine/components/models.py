"""Hardware component data models."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class ComponentCategory(str, Enum):
    SENSOR = "sensor"
    ACTUATOR = "actuator"
    DISPLAY = "display"
    MODULE = "module"


class InterfaceType(str, Enum):
    DIGITAL = "digital"
    ANALOG = "analog"
    I2C = "i2c"
    SPI = "spi"
    ONEWIRE = "onewire"
    PWM = "pwm"
    UART = "uart"


@dataclass
class PinRequirement:
    """Pin requirements for a component connection."""

    count: int = 1
    interfaces: list[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ComponentSpec:
    """Specification for a hardware component in the HHIP catalog."""

    component_id: str
    name: str
    category: str
    description: str
    manufacturer: str = "Generic"
    interfaces: list[str] = field(default_factory=list)
    voltage_v: float = 3.3
    current_ma: float = 0.0
    pins: PinRequirement = field(default_factory=PinRequirement)
    libraries: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    datasheet_url: str = ""
    version: str = "1.0.0"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["pins"] = self.pins.to_dict() if isinstance(self.pins, PinRequirement) else self.pins
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ComponentSpec":
        pins_data = data.get("pins") or {}
        pins = (
            PinRequirement(**pins_data)
            if isinstance(pins_data, dict)
            else PinRequirement()
        )
        return cls(
            component_id=str(data["component_id"]),
            name=str(data["name"]),
            category=str(data.get("category", "module")),
            description=str(data.get("description", "")),
            manufacturer=str(data.get("manufacturer", "Generic")),
            interfaces=list(data.get("interfaces") or []),
            voltage_v=float(data.get("voltage_v", 3.3)),
            current_ma=float(data.get("current_ma", 0.0)),
            pins=pins,
            libraries=list(data.get("libraries") or []),
            tags=list(data.get("tags") or []),
            datasheet_url=str(data.get("datasheet_url", "")),
            version=str(data.get("version", "1.0.0")),
        )


@dataclass
class ComponentSearchResult:
    """Search result with optional compatibility hint."""

    component: ComponentSpec
    score: float = 1.0
    compatible_controllers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "component": self.component.to_dict(),
            "score": self.score,
            "compatible_controllers": list(self.compatible_controllers),
        }
