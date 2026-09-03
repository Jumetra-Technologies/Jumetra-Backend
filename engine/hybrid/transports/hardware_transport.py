"""Abstract hardware transport interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Callable, Optional


class TransportKind(str, Enum):
    SERIAL = "serial"
    MQTT = "mqtt"
    SSH = "ssh"
    MEMORY = "memory"


class HardwareTransport(ABC):
    """Transport-agnostic duplex channel for HHIP hybrid devices."""

    kind: TransportKind = TransportKind.SERIAL

    @property
    @abstractmethod
    def endpoint(self) -> str:
        """Human-readable endpoint (COM port, host, broker URL)."""

    @property
    @abstractmethod
    def is_connected(self) -> bool: ...

    @abstractmethod
    def connect(self) -> None: ...

    @abstractmethod
    def disconnect(self) -> None: ...

    @abstractmethod
    def send(self, message: dict[str, Any]) -> None: ...

    @abstractmethod
    def receive(self) -> Optional[dict[str, Any]]: ...

    def set_disconnect_callback(self, callback: Callable[[], None]) -> None:
        self._on_disconnect = callback  # type: ignore[attr-defined]

    def record_heartbeat(self) -> None:
        """Optional heartbeat touch — serial transports override."""
        return

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value if isinstance(self.kind, TransportKind) else str(self.kind),
            "endpoint": self.endpoint,
            "connected": self.is_connected,
        }


def create_transport(
    kind: str,
    endpoint: str,
    *,
    transport_factory: Optional[Callable[[str], object]] = None,
    **kwargs: Any,
) -> HardwareTransport:
    """Factory for named transports."""
    k = (kind or "serial").lower()
    adapter_factory = kwargs.pop("adapter_factory", None) or transport_factory
    if k in ("serial", "usb", "com", "memory"):
        from .serial_transport import SerialHardwareTransport

        return SerialHardwareTransport(endpoint, adapter_factory=adapter_factory, **kwargs)
    if k == "mqtt":
        from .mqtt_transport import MqttHardwareTransport

        return MqttHardwareTransport(endpoint, **kwargs)
    if k == "ssh":
        from .ssh_transport import SshHardwareTransport

        return SshHardwareTransport(endpoint, **kwargs)
    raise ValueError(f"unsupported transport kind: {kind}")
