"""Device adapter layer — common transport interface for hybrid devices."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional

from ..modes import HybridDeviceMode


class DeviceAdapter(ABC):
    """Common interface for all hybrid device transports."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Adapter identifier."""

    @property
    @abstractmethod
    def mode(self) -> HybridDeviceMode:
        """Primary device mode served by this adapter."""

    @abstractmethod
    def connect(self) -> None:
        """Establish connection to the device backend."""

    @abstractmethod
    def disconnect(self) -> None:
        """Release connection resources."""

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """Return True when the adapter is connected."""

    @abstractmethod
    def is_available(self) -> bool:
        """Return True when the device/backend is reachable."""

    @abstractmethod
    def send(self, command: dict[str, Any]) -> None:
        """Send a command to the device."""

    @abstractmethod
    def receive(self) -> Optional[dict[str, Any]]:
        """Receive the next message or command result."""

    def health(self) -> dict[str, Any]:
        return {
            "adapter": self.name,
            "mode": self.mode.value,
            "connected": self.is_connected,
            "available": self.is_available(),
        }
