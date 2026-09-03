"""Virtual (software-only) HHIP devices — compatibility package.

Canonical location: ``engine.devices.virtual``.
"""

from engine.devices.virtual import DeviceStatus, VirtualButton, VirtualDevice, VirtualLED

__all__ = ["DeviceStatus", "VirtualDevice", "VirtualLED", "VirtualButton"]
