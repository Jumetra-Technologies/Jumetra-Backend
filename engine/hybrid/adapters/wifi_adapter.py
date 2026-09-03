"""WiFi device adapter stub for hybrid bridge."""

from __future__ import annotations

from typing import Any, Optional

from ..modes import HybridDeviceMode
from .base import DeviceAdapter


class HybridWifiAdapter(DeviceAdapter):
    """Stub WiFi transport — HTTP/WebSocket backend to be wired in a later sprint."""

    name = "wifi"

    def __init__(self, host: str = "192.168.4.1", port: int = 8080) -> None:
        self.host = host
        self.port = port
        self._connected = False
        self._inbox: list[dict[str, Any]] = []

    @property
    def mode(self) -> HybridDeviceMode:
        return HybridDeviceMode.PHYSICAL

    @property
    def is_connected(self) -> bool:
        return self._connected

    def connect(self) -> None:
        self._connected = True

    def disconnect(self) -> None:
        self._connected = False
        self._inbox.clear()

    def is_available(self) -> bool:
        return self._connected

    def send(self, command: dict[str, Any]) -> None:
        if not self._connected:
            raise RuntimeError("wifi adapter not connected")
        self._inbox.append({"echo": command, "transport": "wifi"})

    def receive(self) -> Optional[dict[str, Any]]:
        return self._inbox.pop(0) if self._inbox else None
