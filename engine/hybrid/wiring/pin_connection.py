"""Pin connection model — Sprint 30 interactive hybrid wiring."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class WireType(str, Enum):
    DIGITAL = "digital"
    ANALOG = "analog"
    PWM = "pwm"
    POWER = "power"
    GROUND = "ground"
    UART = "uart"
    SPI = "spi"
    I2C = "i2c"
    CAN = "can"
    USB = "usb"
    HYBRID = "hybrid"


class ConnectionDirection(str, Enum):
    SOURCE_TO_DEST = "source_to_dest"
    DEST_TO_SOURCE = "dest_to_source"
    BIDIRECTIONAL = "bidirectional"


class ConnectionStatus(str, Enum):
    ACTIVE = "active"
    WAITING = "waiting"
    INVALID = "invalid"
    DISABLED = "disabled"
    ERROR = "error"


WIRE_COLORS: dict[str, str] = {
    "power": "#dc2626",
    "ground": "#111827",
    "digital": "#2563eb",
    "analog": "#16a34a",
    "pwm": "#7c3aed",
    "uart": "#ea580c",
    "spi": "#ea580c",
    "i2c": "#ea580c",
    "can": "#ea580c",
    "usb": "#ea580c",
    "hybrid": "#2563eb",
    "communication": "#ea580c",
}


@dataclass
class PinEndpoint:
    """One end of a wire (device + pin + optional metadata)."""

    device_id: str
    pin: str
    device_kind: str = "unknown"
    pin_type: str = "GPIO"
    mode: str = "UNKNOWN"
    voltage: float = 3.3
    supports_input: bool = True
    supports_output: bool = True
    available: bool = True

    def key(self) -> str:
        return f"{self.device_id}:{self.pin}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "device_id": self.device_id,
            "pin": self.pin,
            "device_kind": self.device_kind,
            "pin_type": self.pin_type,
            "mode": self.mode,
            "voltage": self.voltage,
            "supports_input": self.supports_input,
            "supports_output": self.supports_output,
            "available": self.available,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PinEndpoint":
        return cls(
            device_id=str(data.get("device_id") or ""),
            pin=str(data.get("pin") or data.get("pin_id") or ""),
            device_kind=str(data.get("device_kind") or "unknown"),
            pin_type=str(data.get("pin_type") or data.get("type") or "GPIO").upper(),
            mode=str(data.get("mode") or "UNKNOWN"),
            voltage=float(data.get("voltage") or 3.3),
            supports_input=bool(data.get("supports_input", True)),
            supports_output=bool(data.get("supports_output", True)),
            available=bool(data.get("available", True)),
        )


@dataclass
class PinConnection:
    """Full engineering wire between two pins."""

    connection_id: str
    source_device: str
    source_pin: str
    destination_device: str
    destination_pin: str
    wire_type: str = WireType.DIGITAL.value
    wire_color: str = WIRE_COLORS["digital"]
    direction: str = ConnectionDirection.BIDIRECTIONAL.value
    created_at: int = field(default_factory=lambda: int(time.time() * 1000))
    status: str = ConnectionStatus.ACTIVE.value
    latency_ms: float = 0.0
    transport: str = ""
    workspace_id: str = ""
    source_kind: str = "unknown"
    destination_kind: str = "unknown"
    source_voltage: float = 3.3
    destination_voltage: float = 3.3
    valid: bool = True
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    routing: list[dict[str, float]] = field(default_factory=list)
    hybrid_connection_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        source: PinEndpoint,
        destination: PinEndpoint,
        wire_type: str = "digital",
        workspace_id: str = "",
        transport: str = "",
        direction: str = ConnectionDirection.BIDIRECTIONAL.value,
        connection_id: str = "",
    ) -> "PinConnection":
        wt = (wire_type or "digital").lower()
        return cls(
            connection_id=connection_id or f"WC_{uuid.uuid4().hex[:10]}",
            source_device=source.device_id,
            source_pin=source.pin,
            destination_device=destination.device_id,
            destination_pin=destination.pin,
            wire_type=wt,
            wire_color=WIRE_COLORS.get(wt, WIRE_COLORS["digital"]),
            direction=direction,
            transport=transport,
            workspace_id=workspace_id,
            source_kind=source.device_kind,
            destination_kind=destination.device_kind,
            source_voltage=source.voltage,
            destination_voltage=destination.voltage,
            status=(
                ConnectionStatus.WAITING.value
                if (not source.available or not destination.available)
                else ConnectionStatus.ACTIVE.value
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "connection_id": self.connection_id,
            "source_device": self.source_device,
            "source_pin": self.source_pin,
            "destination_device": self.destination_device,
            "destination_pin": self.destination_pin,
            "wire_type": self.wire_type,
            "wire_color": self.wire_color,
            "direction": self.direction,
            "created_at": self.created_at,
            "status": self.status,
            "latency": self.latency_ms,
            "latency_ms": self.latency_ms,
            "transport": self.transport,
            "workspace_id": self.workspace_id,
            "source_kind": self.source_kind,
            "destination_kind": self.destination_kind,
            "source_voltage": self.source_voltage,
            "destination_voltage": self.destination_voltage,
            "valid": self.valid,
            "issues": list(self.issues),
            "warnings": list(self.warnings),
            "suggestions": list(self.suggestions),
            "routing": list(self.routing),
            "hybrid_connection_id": self.hybrid_connection_id,
            "metadata": dict(self.metadata),
            "source": self.source_device,
            "target": self.destination_device,
            "source_handle": self.source_pin,
            "target_handle": self.destination_pin,
            "protocol": self.wire_type,
            "color": self.wire_color,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PinConnection":
        return cls(
            connection_id=str(data.get("connection_id") or f"WC_{uuid.uuid4().hex[:8]}"),
            source_device=str(data.get("source_device") or data.get("source") or ""),
            source_pin=str(data.get("source_pin") or data.get("source_handle") or ""),
            destination_device=str(data.get("destination_device") or data.get("target") or ""),
            destination_pin=str(
                data.get("destination_pin") or data.get("target_handle") or ""
            ),
            wire_type=str(data.get("wire_type") or data.get("protocol") or "digital").lower(),
            wire_color=str(data.get("wire_color") or data.get("color") or WIRE_COLORS["digital"]),
            direction=str(data.get("direction") or ConnectionDirection.BIDIRECTIONAL.value),
            created_at=int(data.get("created_at") or time.time() * 1000),
            status=str(data.get("status") or ConnectionStatus.ACTIVE.value),
            latency_ms=float(data.get("latency_ms") or data.get("latency") or 0.0),
            transport=str(data.get("transport") or ""),
            workspace_id=str(data.get("workspace_id") or ""),
            source_kind=str(data.get("source_kind") or "unknown"),
            destination_kind=str(data.get("destination_kind") or "unknown"),
            source_voltage=float(data.get("source_voltage") or 3.3),
            destination_voltage=float(data.get("destination_voltage") or 3.3),
            valid=bool(data.get("valid", True)),
            issues=list(data.get("issues") or []),
            warnings=list(data.get("warnings") or []),
            suggestions=list(data.get("suggestions") or []),
            routing=list(data.get("routing") or []),
            hybrid_connection_id=str(data.get("hybrid_connection_id") or ""),
            metadata=dict(data.get("metadata") or {}),
        )

    def endpoints(self) -> tuple[str, str]:
        return (
            f"{self.source_device}:{self.source_pin}",
            f"{self.destination_device}:{self.destination_pin}",
        )
