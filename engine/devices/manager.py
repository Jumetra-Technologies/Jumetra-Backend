"""Backward-compatible import path for DeviceManager."""

from .device_manager import DeviceManager, UnknownDeviceError, UnknownVirtualDeviceError

__all__ = ["DeviceManager", "UnknownDeviceError", "UnknownVirtualDeviceError"]
