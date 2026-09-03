"""Serial transport adapter.

Wraps PySerial behind a small connect()/disconnect()/send()/receive()
interface so the rest of the HHIP engine never touches a
serial.Serial object directly. This keeps the engine transport
agnostic: a future MQTT, WebSocket, or BLE adapter can implement the
same shape without the engine caring which one it's talking to.

Framing: newline-delimited JSON. send() appends '\\n'; receive()
reads up to the next '\\n'.
"""

from __future__ import annotations

import logging
from typing import Optional

import serial
from serial import SerialException

from ..protocol.messages import ProtocolError, decode_message, encode_message

logger = logging.getLogger("hhip.communication.serial")

DEFAULT_BAUDRATE = 115200
DEFAULT_TIMEOUT = 1.0  # seconds; read timeout for receive()


class SerialAdapterError(Exception):
    """Raised for connection/IO failures on the serial adapter.

    Deliberately distinct from ProtocolError (protocol.messages),
    which is about message shape, not transport failures.
    """


class SerialAdapter:
    """Thin, testable wrapper around pyserial.

    Example:
        adapter = SerialAdapter("COM8")
        adapter.connect()
        adapter.send(message_dict)
        incoming = adapter.receive()  # dict, or None on timeout
        adapter.disconnect()

    Can also be used as a context manager:
        with SerialAdapter("COM8") as adapter:
            ...
    """

    def __init__(
        self,
        port: str,
        baudrate: int = DEFAULT_BAUDRATE,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self._serial: Optional[serial.Serial] = None

    @property
    def is_connected(self) -> bool:
        return self._serial is not None and self._serial.is_open

    def connect(self) -> None:
        """Open the serial port. No-op if already connected."""
        if self.is_connected:
            return
        try:
            self._serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=self.timeout,
            )
        except SerialException as exc:
            raise SerialAdapterError(
                f"Failed to open serial port {self.port!r}: {exc}"
            ) from exc
        logger.debug("Opened serial port %s @ %d baud", self.port, self.baudrate)

    def disconnect(self) -> None:
        """Close the serial port. Safe to call even if not connected."""
        if self._serial is not None:
            try:
                self._serial.close()
            except SerialException as exc:
                logger.warning("Error while closing serial port %s: %s", self.port, exc)
            finally:
                self._serial = None
                logger.debug("Closed serial port %s", self.port)

    def send(self, message: dict) -> None:
        """Encode and write a single HHIP message, newline-terminated."""
        if not self.is_connected:
            raise SerialAdapterError("Cannot send: serial adapter is not connected")
        line = encode_message(message) + "\n"  # ProtocolError propagates as-is
        try:
            self._serial.write(line.encode("utf-8"))
            self._serial.flush()
        except SerialException as exc:
            raise SerialAdapterError(
                f"Failed to write to serial port {self.port!r}: {exc}"
            ) from exc

    def receive(self) -> Optional[dict]:
        """Read one line and decode it as an HHIP message dict.

        Returns None if the read timed out (no complete line) or the
        line was blank. Raises ProtocolError if a non-blank line was
        received but is not valid JSON. This does NOT run full
        protocol validation (missing fields, unknown type, etc.) —
        callers should run validate_message() on the result.
        """
        if not self.is_connected:
            raise SerialAdapterError("Cannot receive: serial adapter is not connected")
        try:
            raw = self._serial.readline()
        except SerialException as exc:
            raise SerialAdapterError(
                f"Failed to read from serial port {self.port!r}: {exc}"
            ) from exc

        if not raw:
            return None  # read timeout, nothing available

        try:
            line = raw.decode("utf-8", errors="replace")
        except UnicodeDecodeError:
            logger.warning("Received non-UTF-8 bytes on %s; dropping line", self.port)
            return None

        if not line.strip():
            return None

        return decode_message(line)  # ProtocolError propagates as-is

    def __enter__(self) -> "SerialAdapter":
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.disconnect()
