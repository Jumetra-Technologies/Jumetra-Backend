"""Physical microcontroller representation for the hybrid device layer.

Sprint 28: wraps universal :class:`HardwareDevice` while keeping the
Sprint 27 ``PhysicalDevice`` API for backward compatibility.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from engine.hybrid.hardware import HardwareDevice, HardwarePin, get_profile_registry


@dataclass
class PhysicalPin:
    pin_id: str
    name: str
    number: int | str
    interfaces: list[str] = field(default_factory=list)
    signal: str = "bidirectional"
    voltage_v: float = 3.3
    state: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "pin_id": self.pin_id,
            "name": self.name,
            "number": self.number,
            "interfaces": list(self.interfaces),
            "signal": self.signal,
            "voltage_v": self.voltage_v,
            "state": self.state,
        }

    @classmethod
    def from_hardware(cls, pin: HardwarePin) -> "PhysicalPin":
        return cls(
            pin_id=pin.pin_id,
            name=pin.name,
            number=pin.number,
            interfaces=list(pin.interfaces),
            signal=pin.signal,
            voltage_v=pin.voltage_v,
            state=pin.state,
        )


@dataclass
class PhysicalDevice:
    """A connected physical board with pin map and capabilities."""

    device_id: str
    board_type: str
    port: str
    label: str = ""
    firmware_version: str = ""
    capabilities: list[str] = field(default_factory=list)
    pins: dict[str, PhysicalPin] = field(default_factory=dict)
    connected: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
    # Sprint 28 universal fields
    vendor: str = ""
    manufacturer: str = ""
    model: str = ""
    category: str = "microcontroller"
    interfaces: list[str] = field(default_factory=list)
    transport: str = "serial"
    connection_state: str = "disconnected"
    profile_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "device_id": self.device_id,
            "board_type": self.board_type,
            "port": self.port,
            "endpoint": self.port,
            "label": self.label or self.model or self.board_type,
            "firmware_version": self.firmware_version,
            "capabilities": list(self.capabilities),
            "pins": [p.to_dict() for p in self.pins.values()],
            "connected": self.connected,
            "connection_state": self.connection_state or ("connected" if self.connected else "disconnected"),
            "vendor": self.vendor,
            "manufacturer": self.manufacturer or self.vendor,
            "model": self.model or self.label or self.board_type,
            "category": self.category,
            "interfaces": list(self.interfaces),
            "transport": self.transport,
            "communication_method": self.transport,
            "profile_id": self.profile_id,
            "metadata": dict(self.metadata),
        }

    def list_pins(self) -> list[dict[str, Any]]:
        return [p.to_dict() for p in self.pins.values()]

    def get_pin(self, pin_id: str) -> Optional[PhysicalPin]:
        return self.pins.get(pin_id)

    def update_pin_state(self, pin_id: str, value: int) -> None:
        pin = self.pins.get(pin_id)
        if pin is not None:
            pin.state = int(value)

    @classmethod
    def from_hardware(cls, device: HardwareDevice) -> "PhysicalDevice":
        pins = {pid: PhysicalPin.from_hardware(p) for pid, p in device.pins.items()}
        caps = [c.name if hasattr(c, "name") else str(c) for c in device.capabilities]
        return cls(
            device_id=device.device_id,
            board_type=device.board_type,
            port=device.endpoint,
            label=device.label,
            firmware_version=device.firmware_version,
            capabilities=caps,
            pins=pins,
            connected=device.connected,
            metadata=dict(device.metadata),
            vendor=device.vendor,
            manufacturer=device.manufacturer or device.vendor,
            model=device.model,
            category=device.category,
            interfaces=list(device.interfaces),
            transport=device.transport,
            connection_state=device.connection_state.value,
            profile_id=device.profile_id,
        )

    @classmethod
    def from_discovery(
        cls,
        *,
        device_id: str,
        board_type: str,
        port: str,
        label: str = "",
        firmware_version: str = "",
        capabilities: Optional[list[str]] = None,
        pin_specs: Optional[list[dict[str, Any]]] = None,
        transport: str = "",
        vendor: str = "",
        manufacturer: str = "",
        profiles_dir: Any = None,
    ) -> "PhysicalDevice":
        hw = HardwareDevice.from_discovery(
            device_id=device_id,
            board_type=board_type,
            port=port,
            label=label,
            firmware_version=firmware_version,
            capabilities=capabilities,
            pin_specs=pin_specs,
            transport=transport,
            vendor=vendor,
            manufacturer=manufacturer,
            profiles_dir=profiles_dir,
        )
        return cls.from_hardware(hw)


def _default_pins_for_board(board_type: str) -> list[dict[str, Any]]:
    profile = get_profile_registry().resolve_board_type(board_type)
    return list(profile.pins)
