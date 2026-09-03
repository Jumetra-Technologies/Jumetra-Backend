"""Pin definition models for Component Engine v2."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional


class PinType(str, Enum):
    POWER = "POWER"
    GROUND = "GROUND"
    GPIO = "GPIO"
    PWM = "PWM"
    ADC = "ADC"
    DAC = "DAC"
    UART_TX = "UART_TX"
    UART_RX = "UART_RX"
    I2C_SDA = "I2C_SDA"
    I2C_SCL = "I2C_SCL"
    SPI_MOSI = "SPI_MOSI"
    SPI_MISO = "SPI_MISO"
    SPI_CLK = "SPI_CLK"
    SPI_CS = "SPI_CS"


class PinDirection(str, Enum):
    INPUT = "INPUT"
    OUTPUT = "OUTPUT"
    BIDIRECTIONAL = "BIDIRECTIONAL"
    POWER = "POWER"
    GROUND = "GROUND"


SUPPORTED_PIN_TYPES = {p.value for p in PinType}


@dataclass
class PinPosition:
    x: float = 0.0
    y: float = 0.0

    def to_dict(self) -> dict[str, float]:
        return {"x": self.x, "y": self.y}

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "PinPosition":
        data = data or {}
        return cls(x=float(data.get("x", 0)), y=float(data.get("y", 0)))


@dataclass
class PinDefinition:
    id: str
    name: str
    type: str = PinType.GPIO.value
    direction: str = PinDirection.BIDIRECTIONAL.value
    voltage: float = 3.3
    position: PinPosition = field(default_factory=PinPosition)
    capabilities: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.type = str(self.type).upper()
        self.direction = str(self.direction).upper()
        if self.type not in SUPPORTED_PIN_TYPES:
            # Allow aliasing common names
            aliases = {
                "VCC": PinType.POWER.value,
                "VDD": PinType.POWER.value,
                "GND": PinType.GROUND.value,
                "DIGITAL": PinType.GPIO.value,
                "SDA": PinType.I2C_SDA.value,
                "SCL": PinType.I2C_SCL.value,
                "MOSI": PinType.SPI_MOSI.value,
                "MISO": PinType.SPI_MISO.value,
                "SCK": PinType.SPI_CLK.value,
                "CLK": PinType.SPI_CLK.value,
                "CS": PinType.SPI_CS.value,
                "TX": PinType.UART_TX.value,
                "RX": PinType.UART_RX.value,
            }
            self.type = aliases.get(self.type, self.type)
        if not self.capabilities:
            self.capabilities = [self.type.lower()]

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.id:
            errors.append("pin id is required")
        if self.type not in SUPPORTED_PIN_TYPES:
            errors.append(f"unsupported pin type: {self.type}")
        if self.voltage < 0:
            errors.append(f"invalid voltage: {self.voltage}")
        return errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "direction": self.direction,
            "voltage": self.voltage,
            "position": self.position.to_dict(),
            "capabilities": list(self.capabilities),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PinDefinition":
        return cls(
            id=str(data.get("id") or data.get("name") or ""),
            name=str(data.get("name") or data.get("id") or ""),
            type=str(data.get("type") or PinType.GPIO.value),
            direction=str(data.get("direction") or PinDirection.BIDIRECTIONAL.value),
            voltage=float(data.get("voltage", 3.3)),
            position=PinPosition.from_dict(data.get("position") if isinstance(data.get("position"), dict) else None),
            capabilities=list(data.get("capabilities") or []),
        )
