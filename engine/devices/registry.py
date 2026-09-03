"""In-memory registry of devices known to the HHIP engine.

Deliberately simple for PoC-01: a dict keyed by device_id, no
persistence, no locking. This establishes the boundary that a future
"Device Manager" (with virtual/simulated device support, persistence,
and registration events) will build on.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("hhip.devices.registry")


class DeviceMode:
    PHYSICAL = "physical"
    VIRTUAL = "virtual"
    SIMULATED = "simulated"


class DeviceStatus:
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"


class UnknownDeviceError(Exception):
    """Raised when an operation references a device_id that isn't registered."""


def _now_ms() -> int:
    return int(time.time() * 1000)


@dataclass
class Device:
    device_id: str
    device_type: str
    mode: str = DeviceMode.PHYSICAL
    status: str = DeviceStatus.CONNECTED
    registered_at: int = field(default_factory=_now_ms)
    last_seen: int = field(default_factory=_now_ms)

    def to_dict(self) -> dict:
        return {
            "device_id": self.device_id,
            "device_type": self.device_type,
            "mode": self.mode,
            "status": self.status,
            "registered_at": self.registered_at,
            "last_seen": self.last_seen,
        }


class DeviceRegistry:
    """Tracks devices currently known to the HHIP engine."""

    def __init__(self) -> None:
        self._devices: dict[str, Device] = {}

    def register(
        self,
        device_id: str,
        device_type: str,
        mode: str = DeviceMode.PHYSICAL,
        status: str = DeviceStatus.CONNECTED,
    ) -> Device:
        """Register a device, or refresh it if already registered.

        A device sending another HELLO after a reconnect is a normal
        event, not an error, so re-registering updates status/last_seen
        in place rather than raising.
        """
        existing = self._devices.get(device_id)
        if existing is not None:
            existing.status = status
            existing.last_seen = _now_ms()
            logger.debug("Device re-registered: %s", device_id)
            return existing

        device = Device(device_id=device_id, device_type=device_type, mode=mode, status=status)
        self._devices[device_id] = device
        logger.debug("Device registered: %s (%s, %s)", device_id, device_type, mode)
        return device

    def get(self, device_id: str) -> Optional[Device]:
        """Return the Device for device_id, or None if not registered."""
        return self._devices.get(device_id)

    def remove(self, device_id: str) -> None:
        """Remove a device from the registry.

        Raises UnknownDeviceError if device_id was never registered.
        """
        if device_id not in self._devices:
            raise UnknownDeviceError(f"Unknown device_id: {device_id!r}")
        del self._devices[device_id]
        logger.debug("Device removed: %s", device_id)

    def all_devices(self) -> list[Device]:
        """Return all currently registered devices."""
        return list(self._devices.values())

    def touch(self, device_id: str) -> None:
        """Update last_seen for a device, e.g. on receiving a HEARTBEAT."""
        device = self._devices.get(device_id)
        if device is None:
            raise UnknownDeviceError(f"Unknown device_id: {device_id!r}")
        device.last_seen = _now_ms()

    def __contains__(self, device_id: str) -> bool:
        return device_id in self._devices

    def __len__(self) -> int:
        return len(self._devices)
