"""Device bookkeeping for the HHIP engine."""

from .base import (
    Capability,
    Device as BaseDevice,
    DeviceLifecycleEvent,
    DeviceMode as AbstractionDeviceMode,
    DeviceStatus as VirtualDeviceStatus,
    PhysicalDevice,
    SimulatorDevice,
    capabilities_for,
)
from .device_manager import DeviceManager, UnknownDeviceError, UnknownVirtualDeviceError
from .device_identity import DeviceIdentityClaim
from .registry import Device, DeviceMode, DeviceRegistry, DeviceStatus
from .virtual import VirtualButton, VirtualDevice, VirtualLED

__all__ = [
    "AbstractionDeviceMode",
    "BaseDevice",
    "Capability",
    "Device",
    "DeviceLifecycleEvent",
    "DeviceManager",
    "DeviceIdentityClaim",
    "DeviceMode",
    "DeviceRegistry",
    "DeviceStatus",
    "PhysicalDevice",
    "SimulatorDevice",
    "UnknownDeviceError",
    "UnknownVirtualDeviceError",
    "VirtualButton",
    "VirtualDevice",
    "VirtualDeviceStatus",
    "VirtualLED",
    "capabilities_for",
]
