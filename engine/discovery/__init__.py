"""Hardware discovery — USB serial port scanning and identification."""

from engine.discovery.models import DiscoveredDevice, DiscoveryStatus
from engine.discovery.service import HardwareDiscoveryService

__all__ = ["DiscoveredDevice", "DiscoveryStatus", "HardwareDiscoveryService"]
