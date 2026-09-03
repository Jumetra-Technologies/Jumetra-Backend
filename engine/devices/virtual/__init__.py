"""Virtual device package — generic software hardware for HHIP."""

from .base_device import DeviceStatus, VirtualDevice
from .virtual_button import VirtualButton
from .virtual_led import VirtualLED

__all__ = ["DeviceStatus", "VirtualDevice", "VirtualLED", "VirtualButton"]
