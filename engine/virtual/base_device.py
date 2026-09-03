"""Compatibility re-exports — prefer ``engine.devices.virtual``."""

from engine.devices.virtual.base_device import DeviceStatus, VirtualDevice

__all__ = ["DeviceStatus", "VirtualDevice"]
