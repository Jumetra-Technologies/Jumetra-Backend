"""MQTT hardware transport (in-memory broker for tests / stub for production)."""

from __future__ import annotations

import logging
import queue
import threading
from typing import Any, Callable, Optional

from .hardware_transport import HardwareTransport, TransportKind

logger = logging.getLogger("hhip.hybrid.transports.mqtt")


class MqttHardwareTransport(HardwareTransport):
    """Queue-backed MQTT transport.

    Production deployments can inject a real client via ``client_factory``.
    By default this uses an in-process duplex queue so unit tests and demos
    work without a broker.
    """

    kind = TransportKind.MQTT

    def __init__(
        self,
        endpoint: str,
        *,
        topic_prefix: str = "hhip/device",
        device_id: str = "",
        inbox: Optional["queue.Queue[dict]"] = None,
        outbox: Optional["queue.Queue[dict]"] = None,
        client_factory: Optional[Callable[..., Any]] = None,
        timeout: float = 0.3,
        **_kwargs: Any,
    ) -> None:
        self._endpoint = endpoint
        self.topic_prefix = topic_prefix
        self.device_id = device_id or endpoint.split("/")[-1] or "mqtt-device"
        self.timeout = timeout
        self._inbox: "queue.Queue[dict]" = inbox or queue.Queue()
        self._outbox: "queue.Queue[dict]" = outbox or queue.Queue()
        self._client_factory = client_factory
        self._client: Any = None
        self._connected = False
        self._lock = threading.RLock()
        self._on_disconnect: Optional[Callable[[], None]] = None

    @property
    def endpoint(self) -> str:
        return self._endpoint

    @property
    def is_connected(self) -> bool:
        return self._connected

    def connect(self) -> None:
        with self._lock:
            if self._connected:
                return
            if self._client_factory is not None:
                self._client = self._client_factory(self._endpoint)
                if hasattr(self._client, "connect"):
                    self._client.connect()
            self._connected = True
            logger.info("[HYBRID] MQTT transport connected to %s", self._endpoint)

    def disconnect(self) -> None:
        with self._lock:
            if self._client is not None and hasattr(self._client, "disconnect"):
                try:
                    self._client.disconnect()
                except Exception:
                    pass
            self._client = None
            self._connected = False

    def send(self, message: dict[str, Any]) -> None:
        with self._lock:
            if not self._connected:
                raise RuntimeError(f"MQTT transport not connected: {self._endpoint}")
            if self._client is not None and hasattr(self._client, "publish"):
                topic = f"{self.topic_prefix}/{self.device_id}/cmd"
                self._client.publish(topic, message)
            else:
                self._outbox.put(message)

    def receive(self) -> Optional[dict[str, Any]]:
        with self._lock:
            if not self._connected:
                return None
            if self._client is not None and hasattr(self._client, "receive"):
                return self._client.receive()
            try:
                return self._inbox.get(timeout=self.timeout)
            except queue.Empty:
                return None

    def inject(self, message: dict[str, Any]) -> None:
        """Test helper — push a message as if received from the broker."""
        self._inbox.put(message)

    def drain_outbound(self) -> list[dict[str, Any]]:
        """Test helper — collect published messages."""
        items: list[dict[str, Any]] = []
        while not self._outbox.empty():
            items.append(self._outbox.get_nowait())
        return items
