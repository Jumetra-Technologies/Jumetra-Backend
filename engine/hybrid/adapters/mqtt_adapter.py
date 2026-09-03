"""MQTT device adapter stub for hybrid bridge."""

from __future__ import annotations

from typing import Any, Optional

from ..modes import HybridDeviceMode
from .base import DeviceAdapter


class HybridMqttAdapter(DeviceAdapter):
    """Stub MQTT transport — topic pub/sub to be wired in a later sprint."""

    name = "mqtt"

    def __init__(self, broker: str = "localhost", topic_prefix: str = "hhip") -> None:
        self.broker = broker
        self.topic_prefix = topic_prefix
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
            raise RuntimeError("mqtt adapter not connected")
        topic = command.get("topic", f"{self.topic_prefix}/command")
        self._inbox.append({"topic": topic, "payload": command, "transport": "mqtt"})

    def receive(self) -> Optional[dict[str, Any]]:
        return self._inbox.pop(0) if self._inbox else None
