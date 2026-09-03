"""Serial device adapter for hybrid bridge."""

from __future__ import annotations

from typing import Any, Optional

from engine.communication.memory_adapter import InMemoryAdapter
from engine.communication.serial_adapter import SerialAdapter

from ..modes import HybridDeviceMode
from .base import DeviceAdapter


class HybridSerialAdapter(DeviceAdapter):
    """Wraps HHIP serial or in-memory transport behind DeviceAdapter."""

    name = "serial"

    def __init__(self, transport: SerialAdapter | InMemoryAdapter) -> None:
        self._transport = transport

    @property
    def mode(self) -> HybridDeviceMode:
        return HybridDeviceMode.PHYSICAL

    @property
    def is_connected(self) -> bool:
        return self._transport.is_connected

    def connect(self) -> None:
        self._transport.connect()

    def disconnect(self) -> None:
        self._transport.disconnect()

    def is_available(self) -> bool:
        return self.is_connected

    def send(self, command: dict[str, Any]) -> None:
        self._transport.send(command)

    def receive(self) -> Optional[dict[str, Any]]:
        return self._transport.receive()

    @property
    def transport(self) -> SerialAdapter | InMemoryAdapter:
        return self._transport
