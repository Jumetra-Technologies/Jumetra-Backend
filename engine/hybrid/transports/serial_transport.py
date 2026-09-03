"""Serial hardware transport implementing HardwareTransport."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Optional

from engine.communication.serial_adapter import SerialAdapter, SerialAdapterError

from .hardware_transport import HardwareTransport, TransportKind

logger = logging.getLogger("hhip.hybrid.transports.serial")

AdapterFactory = Callable[[str], object]


class SerialHardwareTransport(HardwareTransport):
    """Managed serial link with optional heartbeat watchdog."""

    kind = TransportKind.SERIAL

    def __init__(
        self,
        port: str,
        *,
        baudrate: int = 115200,
        timeout: float = 0.3,
        heartbeat_timeout_s: float = 15.0,
        adapter_factory: Optional[AdapterFactory] = None,
        transport_factory: Optional[AdapterFactory] = None,
        **_kwargs: Any,
    ) -> None:
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.heartbeat_timeout_s = heartbeat_timeout_s
        factory = adapter_factory or transport_factory
        self._factory = factory or (
            lambda p: SerialAdapter(p, baudrate=baudrate, timeout=timeout)
        )
        self._adapter: Optional[object] = None
        self._last_heartbeat_ms: Optional[int] = None
        self._connected = False
        self._lock = threading.RLock()
        self._on_disconnect: Optional[Callable[[], None]] = None

    @property
    def endpoint(self) -> str:
        return self.port

    @property
    def is_connected(self) -> bool:
        with self._lock:
            if not self._connected or self._adapter is None:
                return False
            if self._last_heartbeat_ms is None:
                return True
            elapsed = (time.monotonic() * 1000) - self._last_heartbeat_ms
            return elapsed < self.heartbeat_timeout_s * 1000

    @property
    def last_heartbeat_ms(self) -> Optional[int]:
        return self._last_heartbeat_ms

    def set_disconnect_callback(self, callback: Callable[[], None]) -> None:
        self._on_disconnect = callback

    def connect(self) -> None:
        with self._lock:
            if self._connected:
                return
            self._adapter = self._factory(self.port)
            self._adapter.connect()  # type: ignore[attr-defined]
            self._connected = True
            self._last_heartbeat_ms = int(time.monotonic() * 1000)
            logger.info("[HYBRID] Serial transport connected on %s", self.port)

    def disconnect(self) -> None:
        with self._lock:
            if self._adapter is not None:
                try:
                    self._adapter.disconnect()  # type: ignore[attr-defined]
                except Exception:
                    pass
            self._adapter = None
            self._connected = False
            self._last_heartbeat_ms = None

    def send(self, message: dict[str, Any]) -> None:
        with self._lock:
            if not self._connected or self._adapter is None:
                raise SerialAdapterError(f"Transport not connected: {self.port}")
            self._adapter.send(message)  # type: ignore[attr-defined]

    def receive(self) -> Optional[dict[str, Any]]:
        with self._lock:
            if not self._connected or self._adapter is None:
                return None
            msg = self._adapter.receive()  # type: ignore[attr-defined]
            if msg is not None:
                self._touch_heartbeat(msg)
            elif not self.is_connected and self._on_disconnect:
                try:
                    self._on_disconnect()
                except Exception:
                    pass
            return msg

    def record_heartbeat(self) -> None:
        with self._lock:
            self._last_heartbeat_ms = int(time.monotonic() * 1000)

    def _touch_heartbeat(self, message: dict[str, Any]) -> None:
        msg_type = message.get("type", "")
        payload = message.get("payload") or {}
        event = payload.get("event", "")
        if msg_type in ("HEARTBEAT", "HELLO", "HELLO_ACK") or event in (
            "DEVICE_DISCOVERY",
            "GPIO_STATE",
        ):
            self.record_heartbeat()


# Backward-compatible alias used by Sprint 27 code paths
SerialTransport = SerialHardwareTransport
