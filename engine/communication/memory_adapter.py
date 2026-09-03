"""In-memory transport adapter, used for simulation and interactive testing.

Implements the same connect()/disconnect()/send()/receive() shape as
SerialAdapter (engine.communication.serial_adapter), but moves
already-decoded message dicts through two in-process queues instead
of bytes over a real serial port.

This exists so `engine/main.py --simulate` can exercise the full
engine loop (registration, sequence tracking, HELLO/HEARTBEAT
handling) with no hardware and no OS-specific serial emulation —
unlike a pty-based approach, this works identically on Windows,
macOS, and Linux.
"""

from __future__ import annotations

import queue
from typing import Optional


class InMemoryAdapter:
    """One end of an in-process duplex channel of message dicts.

    Two InMemoryAdapter instances, created via make_adapter_pair(),
    are wired to each other: messages sent on one arrive via
    receive() on the other.
    """

    def __init__(
        self,
        name: str,
        outbox: "queue.Queue[dict]",
        inbox: "queue.Queue[dict]",
        timeout: float = 1.0,
    ) -> None:
        self.port = f"memory://{name}"
        self._outbox = outbox
        self._inbox = inbox
        self._timeout = timeout
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    def connect(self) -> None:
        self._connected = True

    def disconnect(self) -> None:
        self._connected = False

    def send(self, message: dict) -> None:
        if not self._connected:
            raise RuntimeError("Cannot send: InMemoryAdapter is not connected")
        self._outbox.put(message)

    def receive(self) -> Optional[dict]:
        """Return the next message, or None if none arrives within the timeout.

        Mirrors SerialAdapter.receive()'s timeout-returns-None
        behavior so HHIPEngine.run()'s loop doesn't need to know
        which transport it's talking to.
        """
        if not self._connected:
            raise RuntimeError("Cannot receive: InMemoryAdapter is not connected")
        try:
            return self._inbox.get(timeout=self._timeout)
        except queue.Empty:
            return None

    def __enter__(self) -> "InMemoryAdapter":
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.disconnect()


def make_adapter_pair(timeout: float = 1.0) -> tuple[InMemoryAdapter, InMemoryAdapter]:
    """Create two InMemoryAdapters wired to each other.

    engine_side.send(msg) becomes visible via device_side.receive(),
    and vice versa.
    """
    to_device: "queue.Queue[dict]" = queue.Queue()
    to_engine: "queue.Queue[dict]" = queue.Queue()
    engine_side = InMemoryAdapter("engine", outbox=to_device, inbox=to_engine, timeout=timeout)
    device_side = InMemoryAdapter("device", outbox=to_engine, inbox=to_device, timeout=timeout)
    return engine_side, device_side
