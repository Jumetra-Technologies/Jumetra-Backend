"""SSH hardware transport for Raspberry Pi and other Linux SBCs."""

from __future__ import annotations

import logging
import queue
import threading
from typing import Any, Callable, Optional

from .hardware_transport import HardwareTransport, TransportKind

logger = logging.getLogger("hhip.hybrid.transports.ssh")


class SshHardwareTransport(HardwareTransport):
    """SSH-backed transport for remote agents (e.g. Raspberry Pi).

    Without a real SSH client this uses an in-process message queue so
    HHIP can unit-test Pi agent flows. Inject ``session_factory`` to
    attach paramiko / asyncssh in production.
    """

    kind = TransportKind.SSH

    def __init__(
        self,
        endpoint: str,
        *,
        username: str = "pi",
        port: int = 22,
        inbox: Optional["queue.Queue[dict]"] = None,
        outbox: Optional["queue.Queue[dict]"] = None,
        session_factory: Optional[Callable[..., Any]] = None,
        timeout: float = 0.3,
        **_kwargs: Any,
    ) -> None:
        self._endpoint = endpoint
        self.username = username
        self.ssh_port = port
        self.timeout = timeout
        self._inbox: "queue.Queue[dict]" = inbox or queue.Queue()
        self._outbox: "queue.Queue[dict]" = outbox or queue.Queue()
        self._session_factory = session_factory
        self._session: Any = None
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
            if self._session_factory is not None:
                self._session = self._session_factory(
                    self._endpoint, username=self.username, port=self.ssh_port
                )
                if hasattr(self._session, "connect"):
                    self._session.connect()
            self._connected = True
            logger.info(
                "[HYBRID] SSH transport connected to %s@%s:%s",
                self.username,
                self._endpoint,
                self.ssh_port,
            )

    def disconnect(self) -> None:
        with self._lock:
            if self._session is not None and hasattr(self._session, "close"):
                try:
                    self._session.close()
                except Exception:
                    pass
            self._session = None
            self._connected = False

    def send(self, message: dict[str, Any]) -> None:
        with self._lock:
            if not self._connected:
                raise RuntimeError(f"SSH transport not connected: {self._endpoint}")
            if self._session is not None and hasattr(self._session, "send"):
                self._session.send(message)
            else:
                self._outbox.put(message)

    def receive(self) -> Optional[dict[str, Any]]:
        with self._lock:
            if not self._connected:
                return None
            if self._session is not None and hasattr(self._session, "receive"):
                return self._session.receive()
            try:
                return self._inbox.get(timeout=self.timeout)
            except queue.Empty:
                return None

    def execute(self, command: str) -> dict[str, Any]:
        """Run a remote shell command when a real session is available."""
        if self._session is not None and hasattr(self._session, "exec"):
            return self._session.exec(command)
        return {"ok": True, "command": command, "stdout": "", "simulated": True}

    def inject(self, message: dict[str, Any]) -> None:
        self._inbox.put(message)

    def drain_outbound(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        while not self._outbox.empty():
            items.append(self._outbox.get_nowait())
        return items
