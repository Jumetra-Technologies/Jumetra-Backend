"""Data-driven device capability profiles.

Capabilities are looked up by ``device_type`` key — never by branching
on concrete device classes. Unknown types get an empty capability set.
"""

from __future__ import annotations

from enum import Enum
from typing import Iterable


class Capability(Enum):
    """Atomic operations a device may advertise."""

    ON = "ON"
    OFF = "OFF"
    BRIGHTNESS = "BRIGHTNESS"
    COLOR = "COLOR"
    PRESS = "PRESS"
    RELEASE = "RELEASE"
    TOGGLE = "TOGGLE"
    ROTATE = "ROTATE"
    POSITION = "POSITION"
    READ = "READ"
    CALIBRATE = "CALIBRATE"
    WRITE = "WRITE"
    CONNECT = "CONNECT"
    DISCONNECT = "DISCONNECT"


# Profiles keyed by device_type string (e.g. "LED", "SERVO").
CAPABILITY_PROFILES: dict[str, frozenset[Capability]] = {
    "LED": frozenset(
        {Capability.ON, Capability.OFF, Capability.BRIGHTNESS, Capability.COLOR, Capability.TOGGLE}
    ),
    "BUTTON": frozenset({Capability.PRESS, Capability.RELEASE, Capability.TOGGLE}),
    "SERVO": frozenset({Capability.ROTATE, Capability.POSITION}),
    "SENSOR": frozenset({Capability.READ, Capability.CALIBRATE}),
    "MOTOR": frozenset({Capability.ON, Capability.OFF, Capability.ROTATE}),
    "PUMP": frozenset({Capability.ON, Capability.OFF}),
    "LCD": frozenset({Capability.WRITE, Capability.READ}),
    "CAMERA": frozenset({Capability.READ}),
    "RFID": frozenset({Capability.READ}),
    "GPS": frozenset({Capability.READ, Capability.CALIBRATE}),
    "SIMULATOR": frozenset({Capability.CONNECT, Capability.DISCONNECT, Capability.READ}),
    "ESP32": frozenset({Capability.CONNECT, Capability.DISCONNECT, Capability.READ, Capability.WRITE}),
}


def capabilities_for(device_type: str) -> frozenset[Capability]:
    """Return the capability set for ``device_type`` (empty if unknown)."""
    return CAPABILITY_PROFILES.get(device_type, frozenset())


def capability_values(capabilities: Iterable[Capability]) -> list[str]:
    """Serialize capabilities to a sorted list of string values."""
    return sorted(c.value for c in capabilities)
