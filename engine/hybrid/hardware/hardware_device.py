"""Universal hardware device abstraction for HHIP hybrid layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from .capability import Capability
from .profile import HardwareProfile, get_profile_registry


class ConnectionState(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    BUSY = "busy"
    ERROR = "error"


@dataclass
class HardwarePin:
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
    def from_dict(cls, data: dict[str, Any]) -> "HardwarePin":
        ifaces = data.get("interfaces") or ["gpio"]
        if isinstance(ifaces, str):
            ifaces = [s.strip() for s in ifaces.split(",") if s.strip()]
        return cls(
            pin_id=str(data.get("pin_id") or data.get("id") or ""),
            name=str(data.get("name") or data.get("pin_id") or ""),
            number=data.get("number", data.get("pin_id", 0)),
            interfaces=list(ifaces),
            signal=str(data.get("signal") or "bidirectional"),
            voltage_v=float(data.get("voltage_v") or 3.3),
            state=int(data.get("state") or 0),
        )


@dataclass
class HardwareDevice:
    """Universal representation of any physical hardware connected to HHIP."""

    device_id: str
    vendor: str
    model: str
    category: str
    board_type: str
    capabilities: list[Capability] = field(default_factory=list)
    pins: dict[str, HardwarePin] = field(default_factory=dict)
    interfaces: list[str] = field(default_factory=list)
    connection_state: ConnectionState = ConnectionState.DISCONNECTED
    transport: str = "serial"
    endpoint: str = ""  # COM port, mqtt topic host, ssh host, etc.
    label: str = ""
    firmware_version: str = ""
    manufacturer: str = ""
    profile_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    # Backward-compatible aliases used by Sprint 27 PhysicalDevice consumers
    @property
    def port(self) -> str:
        return self.endpoint

    @property
    def connected(self) -> bool:
        return self.connection_state == ConnectionState.CONNECTED

    @connected.setter
    def connected(self, value: bool) -> None:
        self.connection_state = (
            ConnectionState.CONNECTED if value else ConnectionState.DISCONNECTED
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "device_id": self.device_id,
            "vendor": self.vendor,
            "manufacturer": self.manufacturer or self.vendor,
            "model": self.model,
            "category": self.category,
            "board_type": self.board_type,
            "label": self.label or self.model,
            "capabilities": [c.name if isinstance(c, Capability) else str(c) for c in self.capabilities],
            "capability_details": [
                c.to_dict() if isinstance(c, Capability) else {"name": str(c)} for c in self.capabilities
            ],
            "pins": [p.to_dict() for p in self.pins.values()],
            "interfaces": list(self.interfaces),
            "connection_state": self.connection_state.value,
            "connected": self.connected,
            "transport": self.transport,
            "communication_method": self.transport,
            "endpoint": self.endpoint,
            "port": self.endpoint,
            "firmware_version": self.firmware_version,
            "profile_id": self.profile_id,
            "metadata": dict(self.metadata),
        }

    def list_pins(self) -> list[dict[str, Any]]:
        return [p.to_dict() for p in self.pins.values()]

    def get_pin(self, pin_id: str) -> Optional[HardwarePin]:
        return self.pins.get(pin_id)

    def update_pin_state(self, pin_id: str, value: int) -> None:
        pin = self.pins.get(pin_id)
        if pin is not None:
            pin.state = int(value)

    @classmethod
    def from_profile(
        cls,
        profile: HardwareProfile,
        *,
        device_id: str,
        endpoint: str = "",
        transport: str = "",
        firmware_version: str = "",
        label: str = "",
        metadata: Optional[dict[str, Any]] = None,
    ) -> "HardwareDevice":
        pins: dict[str, HardwarePin] = {}
        for spec in profile.pins:
            pin = HardwarePin.from_dict(spec)
            if pin.pin_id:
                pins[pin.pin_id] = pin
        return cls(
            device_id=device_id,
            vendor=profile.vendor,
            model=profile.model,
            category=profile.category,
            board_type=profile.board_type,
            capabilities=list(profile.capabilities),
            pins=pins,
            interfaces=list(profile.interfaces),
            connection_state=ConnectionState.CONNECTED,
            transport=transport or profile.default_transport,
            endpoint=endpoint,
            label=label or profile.label,
            firmware_version=firmware_version,
            manufacturer=profile.vendor,
            profile_id=profile.profile_id,
            metadata=dict(metadata or {}),
        )

    @classmethod
    def from_discovery(
        cls,
        *,
        device_id: str,
        board_type: str,
        port: str = "",
        endpoint: str = "",
        label: str = "",
        firmware_version: str = "",
        capabilities: Optional[list[Any]] = None,
        pin_specs: Optional[list[dict[str, Any]]] = None,
        transport: str = "",
        vendor: str = "",
        manufacturer: str = "",
        profiles_dir: Any = None,
    ) -> "HardwareDevice":
        registry = get_profile_registry(profiles_dir)
        profile = registry.resolve_board_type(board_type)
        device = cls.from_profile(
            profile,
            device_id=device_id,
            endpoint=endpoint or port,
            transport=transport or profile.default_transport,
            firmware_version=firmware_version,
            label=label,
        )
        if vendor:
            device.vendor = vendor
            device.manufacturer = manufacturer or vendor
        elif manufacturer:
            device.manufacturer = manufacturer
            device.vendor = manufacturer
        if capabilities:
            device.capabilities = Capability.from_list(capabilities)
        if pin_specs:
            device.pins = {}
            for spec in pin_specs:
                pin = HardwarePin.from_dict(spec)
                if pin.pin_id:
                    device.pins[pin.pin_id] = pin
        device.connected = True
        return device

    @classmethod
    def from_physical_dict(cls, data: dict[str, Any]) -> "HardwareDevice":
        """Adapt a Sprint 27 PhysicalDevice dict into HardwareDevice."""
        return cls.from_discovery(
            device_id=str(data.get("device_id") or "device"),
            board_type=str(data.get("board_type") or "unknown"),
            port=str(data.get("port") or data.get("endpoint") or ""),
            label=str(data.get("label") or ""),
            firmware_version=str(data.get("firmware_version") or ""),
            capabilities=data.get("capabilities"),
            pin_specs=data.get("pins"),
            transport=str(data.get("transport") or data.get("communication_method") or "serial"),
            vendor=str(data.get("vendor") or data.get("manufacturer") or ""),
            manufacturer=str(data.get("manufacturer") or data.get("vendor") or ""),
        )
