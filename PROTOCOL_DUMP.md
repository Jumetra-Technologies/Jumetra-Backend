# Protocol source dump — from `C:\Users\BYU\Jumetra-Backend`

## 1. Protocol / handshake / agent source (Python)

## `engine\protocol\__init__.py`

```python
"""HHIP wire protocol package."""
```

## `engine\protocol\messages.py`

```python
"""HHIP Protocol Version 1.

Newline-delimited JSON message protocol used between the HHIP engine
and any connected device (physical or, eventually, virtual/simulated).

This module has no knowledge of serial ports, sockets, or any other
transport. It only deals with message *shape*: creating, encoding,
decoding, and validating dictionaries that conform to the HHIP wire
format.

Deliberately built on the standard library only (json, uuid, time,
dataclasses) — no Pydantic or similar, per the current engineering
constraints for this phase.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

PROTOCOL_VERSION = 1


class MessageType:
    """All message types defined by HHIP Protocol Version 1.

    Only HELLO, HELLO_ACK, HEARTBEAT, and ACK are exercised by PoC-01.
    The rest are declared now so the wire format and validation logic
    are stable as later phases start using them.
    """

    HELLO = "HELLO"
    HELLO_ACK = "HELLO_ACK"
    HEARTBEAT = "HEARTBEAT"
    READ = "READ"
    WRITE = "WRITE"
    STATE_UPDATE = "STATE_UPDATE"
    EVENT = "EVENT"
    ACK = "ACK"
    ERROR = "ERROR"
    DISCONNECT = "DISCONNECT"
    # Sprint 10: physical sync measurement (no clock correction).
    SYNC_REQUEST = "SYNC_REQUEST"
    SYNC_RESPONSE = "SYNC_RESPONSE"
    # Sprint 16: physical correction bridge (software clock model only).
    SYNC_CORRECTION_REQUEST = "SYNC_CORRECTION_REQUEST"
    SYNC_CORRECTION_RESPONSE = "SYNC_CORRECTION_RESPONSE"


ALL_MESSAGE_TYPES = {
    MessageType.HELLO,
    MessageType.HELLO_ACK,
    MessageType.HEARTBEAT,
    MessageType.READ,
    MessageType.WRITE,
    MessageType.STATE_UPDATE,
    MessageType.EVENT,
    MessageType.ACK,
    MessageType.ERROR,
    MessageType.DISCONNECT,
    MessageType.SYNC_REQUEST,
    MessageType.SYNC_RESPONSE,
    MessageType.SYNC_CORRECTION_REQUEST,
    MessageType.SYNC_CORRECTION_RESPONSE,
}

# Subset of message types required for PoC-01. Kept separate from
# ALL_MESSAGE_TYPES so the engine can (optionally) reject message types
# that are defined in the protocol but not yet supported by this phase.
POC01_MESSAGE_TYPES = {
    MessageType.HELLO,
    MessageType.HELLO_ACK,
    MessageType.HEARTBEAT,
    MessageType.ACK,
}


class ErrorCode:
    """Initial HHIP error categories."""

    INVALID_MESSAGE = "INVALID_MESSAGE"
    INVALID_VERSION = "INVALID_VERSION"
    UNKNOWN_DEVICE = "UNKNOWN_DEVICE"
    INVALID_STATE = "INVALID_STATE"
    TIMEOUT = "TIMEOUT"
    DUPLICATE_MESSAGE = "DUPLICATE_MESSAGE"
    SEQUENCE_ERROR = "SEQUENCE_ERROR"
    UNAUTHORIZED = "UNAUTHORIZED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


REQUIRED_FIELDS = {
    "version",
    "message_id",
    "type",
    "source",
    "target",
    "sequence",
    "timestamp",
    "payload",
}


class ProtocolError(Exception):
    """Raised when a message cannot be encoded or decoded at all.

    Distinct from validation errors (see validate_message), which
    describe a *structurally decodable* message that violates the
    protocol's rules.
    """


def new_message_id() -> str:
    """Generate a unique message id (used for tracing/dedup/acks)."""
    return uuid.uuid4().hex


def current_timestamp_ms() -> int:
    """Current wall-clock time in milliseconds since the epoch."""
    return int(time.time() * 1000)


@dataclass
class Message:
    """In-memory representation of an HHIP protocol message.

    Prefer create_message()/encode_message() for most call sites;
    this dataclass exists for callers that want a typed object
    instead of a raw dict (e.g. future State Manager / Message
    Router components).
    """

    type: str
    source: str
    target: str
    sequence: int
    payload: dict = field(default_factory=dict)
    version: int = PROTOCOL_VERSION
    message_id: str = field(default_factory=new_message_id)
    timestamp: int = field(default_factory=current_timestamp_ms)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "message_id": self.message_id,
            "type": self.type,
            "source": self.source,
            "target": self.target,
            "sequence": self.sequence,
            "timestamp": self.timestamp,
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Message":
        return cls(
            type=data["type"],
            source=data["source"],
            target=data["target"],
            sequence=data["sequence"],
            payload=data.get("payload", {}),
            version=data.get("version", PROTOCOL_VERSION),
            message_id=data.get("message_id") or new_message_id(),
            timestamp=(
                data["timestamp"] if data.get("timestamp") is not None else current_timestamp_ms()
            ),
        )


def create_message(
    type_: str,
    source: str,
    target: str,
    sequence: int,
    payload: Optional[dict] = None,
    version: int = PROTOCOL_VERSION,
    message_id: Optional[str] = None,
    timestamp: Optional[int] = None,
) -> dict[str, Any]:
    """Build a new HHIP message as a plain dict, ready to encode/send.

    This is the primary entry point most code should use.
    """
    message = Message(
        type=type_,
        source=source,
        target=target,
        sequence=sequence,
        payload=payload if payload is not None else {},
        version=version,
        message_id=message_id or new_message_id(),
        timestamp=timestamp if timestamp is not None else current_timestamp_ms(),
    )
    return message.to_dict()


def encode_message(message: dict) -> str:
    """Encode a message dict into a single-line JSON string.

    Does not append a newline; transport code (e.g. the serial
    adapter) is responsible for framing (appending '\\n').
    """
    try:
        return json.dumps(message, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ProtocolError(f"Failed to encode message: {exc}") from exc


def decode_message(line: str) -> dict[str, Any]:
    """Decode a single line of newline-delimited JSON into a dict.

    Raises ProtocolError if the line is empty, not valid JSON, or not
    a JSON object. Does NOT perform protocol-level validation (missing
    fields, unknown type, etc.) — use validate_message() for that.
    """
    stripped = line.strip()
    if not stripped:
        raise ProtocolError("Empty line cannot be decoded as a message")
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise ProtocolError(f"Invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ProtocolError("Decoded message must be a JSON object")
    return data


def validate_message(message: dict) -> list[str]:
    """Validate a decoded message dict against HHIP Protocol Version 1.

    Returns a list of human-readable error strings. An empty list
    means the message is valid. This never raises — callers decide
    how to react (e.g. send back an ERROR message with
    ErrorCode.INVALID_MESSAGE).
    """
    errors: list[str] = []

    missing = REQUIRED_FIELDS - message.keys()
    if missing:
        errors.append(f"Missing required fields: {sorted(missing)}")
        # Further checks would likely KeyError, so stop here.
        return errors

    if message["version"] != PROTOCOL_VERSION:
        errors.append(
            f"Unsupported protocol version: {message['version']!r} "
            f"(expected {PROTOCOL_VERSION})"
        )

    if message["type"] not in ALL_MESSAGE_TYPES:
        errors.append(f"Unknown message type: {message['type']!r}")

    if not isinstance(message["source"], str) or not message["source"]:
        errors.append("'source' must be a non-empty string")

    if not isinstance(message["target"], str) or not message["target"]:
        errors.append("'target' must be a non-empty string")

    # bool is a subclass of int in Python; explicitly exclude it.
    if isinstance(message["sequence"], bool) or not isinstance(message["sequence"], int):
        errors.append("'sequence' must be an integer")

    if isinstance(message["timestamp"], bool) or not isinstance(message["timestamp"], int):
        errors.append("'timestamp' must be an integer (milliseconds since epoch)")

    if not isinstance(message["payload"], dict):
        errors.append("'payload' must be a JSON object")

    if not isinstance(message["message_id"], str) or not message["message_id"]:
        errors.append("'message_id' must be a non-empty string")

    return errors


def is_valid(message: dict) -> bool:
    """Convenience wrapper: True if validate_message() found no errors."""
    return not validate_message(message)
```

## `engine\protocol\reliability.py`

```python
"""Wire reliability — timeout, retry, and exponential backoff."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Optional


@dataclass
class WireReliabilityConfig:
    """Configuration for correction wire operations."""

    timeout_ms: int = 5_000
    max_retries: int = 3
    initial_backoff_ms: int = 100
    backoff_multiplier: float = 2.0
    max_backoff_ms: int = 2_000

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "WireReliabilityConfig":
        return cls(
            timeout_ms=int(data.get("timeout_ms", 5_000)),
            max_retries=int(data.get("max_retries", 3)),
            initial_backoff_ms=int(data.get("initial_backoff_ms", 100)),
            backoff_multiplier=float(data.get("backoff_multiplier", 2.0)),
            max_backoff_ms=int(data.get("max_backoff_ms", 2_000)),
        )


@dataclass
class WireAttempt:
    """One wire send attempt for a correction transaction."""

    transaction_id: str
    attempt: int
    sent_at: int
    next_retry_at: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class WireReliabilityPolicy:
    """Timeout detection, retry eligibility, and backoff delays."""

    def __init__(self, config: Optional[WireReliabilityConfig] = None) -> None:
        self.config = config or WireReliabilityConfig()

    def is_timed_out(self, sent_at: int, now_ms: int) -> bool:
        if sent_at <= 0:
            return False
        return (now_ms - sent_at) >= self.config.timeout_ms

    def should_retry(self, attempt: int) -> bool:
        """Return True if another attempt is allowed (attempt is 0-based)."""
        return attempt < self.config.max_retries

    def backoff_delay_ms(self, attempt: int) -> int:
        """Exponential backoff for retry ``attempt`` (0-based)."""
        if attempt <= 0:
            return 0
        delay = int(
            self.config.initial_backoff_ms
            * (self.config.backoff_multiplier ** (attempt - 1))
        )
        return min(delay, self.config.max_backoff_ms)

    def next_retry_at(self, sent_at: int, attempt: int) -> int:
        return sent_at + self.config.timeout_ms + self.backoff_delay_ms(attempt + 1)

    def record_attempt(self, transaction_id: str, attempt: int, sent_at: int) -> WireAttempt:
        return WireAttempt(
            transaction_id=transaction_id,
            attempt=attempt,
            sent_at=sent_at,
            next_retry_at=self.next_retry_at(sent_at, attempt),
        )
```

## `engine\protocol\sync_wire.py`

```python
"""Wire ↔ Event mapping helpers for SYNC_* messages (no transport imports).

Keeps SynchronizationManager free of serial/protocol envelope details.
"""

from __future__ import annotations

from typing import Any, Mapping, MutableMapping, Optional


def normalize_sync_response_payload(
    payload: Mapping[str, Any],
    *,
    wire_message: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """Normalize a wire SYNC_RESPONSE payload for SynchronizationManager.

    Ensures ``request_id``, ``request_time``, ``device_timestamp``, and
    Sprint 8-compatible ``server_timestamp`` (device clock sample) are set.
    """
    out: dict[str, Any] = dict(payload)

    if out.get("request_id") is None and wire_message is not None:
        # Some firmwares only put ids on the envelope.
        out["request_id"] = wire_message.get("message_id")

    host_ts = out.get("server_timestamp_host")
    if host_ts is None:
        host_ts = out.get("request_time")
    if host_ts is not None:
        out.setdefault("request_time", host_ts)

    device_ts = out.get("device_timestamp")
    if device_ts is None:
        # Sprint 8 / firmware compat: server_timestamp held the device sample.
        device_ts = out.get("server_timestamp")
    if device_ts is not None:
        out["device_timestamp"] = device_ts
        out["server_timestamp"] = device_ts

    if out.get("device_id") is None and wire_message is not None:
        out["device_id"] = wire_message.get("source")

    if out.get("correlation_id") is None and wire_message is not None:
        # Prefer payload; fall back to nothing (manager matches on request_id).
        pass

    return out


def event_payload_from_wire_sync_response(message: Mapping[str, Any]) -> dict[str, Any]:
    """Build an Event payload from a decoded SYNC_RESPONSE wire message."""
    payload = message.get("payload") or {}
    if not isinstance(payload, dict):
        payload = {"value": payload}
    return normalize_sync_response_payload(payload, wire_message=message)


def apply_sync_response_normalization(event_payload: MutableMapping[str, Any]) -> None:
    """In-place normalize for an Event that already carries a sync payload."""
    normalized = normalize_sync_response_payload(event_payload)
    event_payload.clear()
    event_payload.update(normalized)
```

## `engine\protocol\correction.py`

```python
"""SYNC_CORRECTION_REQUEST / SYNC_CORRECTION_RESPONSE protocol messages."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Optional


def _new_transaction_id() -> str:
    return f"corr_{uuid.uuid4().hex[:12]}"


@dataclass
class SyncCorrectionRequest:
    """Host → device bounded correction command."""

    transaction_id: str
    device_id: str
    correction_step: float
    timestamp: int
    sequence_number: int = 0
    correlation_id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), separators=(",", ":"))

    def to_event_payload(self) -> dict[str, Any]:
        return {
            "transaction_id": self.transaction_id,
            "device_id": self.device_id,
            "correction_step": self.correction_step,
            "timestamp": self.timestamp,
            "sequence_number": self.sequence_number,
            "correlation_id": self.correlation_id,
        }

    def to_wire_payload(self) -> dict[str, Any]:
        return self.to_event_payload()

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SyncCorrectionRequest":
        return cls(
            transaction_id=str(data.get("transaction_id") or _new_transaction_id()),
            device_id=str(data["device_id"]),
            correction_step=float(data["correction_step"]),
            timestamp=int(data["timestamp"]),
            sequence_number=int(data.get("sequence_number", 0)),
            correlation_id=data.get("correlation_id"),
        )

    @classmethod
    def from_json(cls, raw: str) -> "SyncCorrectionRequest":
        return cls.from_dict(json.loads(raw))

    @classmethod
    def create(
        cls,
        device_id: str,
        correction_step: float,
        timestamp: int,
        *,
        sequence_number: int = 0,
        correlation_id: Optional[str] = None,
    ) -> "SyncCorrectionRequest":
        return cls(
            transaction_id=_new_transaction_id(),
            device_id=device_id,
            correction_step=float(correction_step),
            timestamp=int(timestamp),
            sequence_number=sequence_number,
            correlation_id=correlation_id,
        )


@dataclass
class SyncCorrectionResponse:
    """Device → host correction acknowledgement."""

    transaction_id: str
    device_id: str
    correction_step: float
    timestamp: int
    applied: bool = True
    accumulated_correction: float = 0.0
    software_clock_offset: float = 0.0
    sequence_number: int = 0
    correlation_id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), separators=(",", ":"))

    def to_event_payload(self) -> dict[str, Any]:
        return self.to_dict()

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SyncCorrectionResponse":
        return cls(
            transaction_id=str(data["transaction_id"]),
            device_id=str(data.get("device_id") or data.get("source") or ""),
            correction_step=float(data.get("correction_step", 0.0)),
            timestamp=int(data.get("timestamp", 0)),
            applied=bool(data.get("applied", True)),
            accumulated_correction=float(data.get("accumulated_correction", 0.0)),
            software_clock_offset=float(data.get("software_clock_offset", 0.0)),
            sequence_number=int(data.get("sequence_number", 0)),
            correlation_id=data.get("correlation_id"),
        )

    @classmethod
    def from_json(cls, raw: str) -> "SyncCorrectionResponse":
        return cls.from_dict(json.loads(raw))
```

## `engine\protocol\correction_wire.py`

```python
"""Wire helpers for SYNC_CORRECTION_* messages."""

from __future__ import annotations

from typing import Any, Mapping

from .correction import SyncCorrectionRequest, SyncCorrectionResponse


def event_payload_from_wire_correction_response(
    message: Mapping[str, Any],
) -> dict[str, Any]:
    """Build normalized payload from a wire SYNC_CORRECTION_RESPONSE."""
    payload = message.get("payload") or {}
    if not isinstance(payload, dict):
        payload = {"value": payload}
    out = dict(payload)
    out.setdefault("device_id", message.get("source"))
    out.setdefault("timestamp", message.get("timestamp"))
    if out.get("transaction_id") is None:
        out["transaction_id"] = message.get("message_id")
    return out


def build_wire_correction_request(
    request: SyncCorrectionRequest,
    *,
    source: str = "hhip",
    sequence: int = 1,
    message_id: str | None = None,
) -> dict[str, Any]:
    """Build HHIP Protocol v1 envelope for SYNC_CORRECTION_REQUEST."""
    return {
        "version": 1,
        "type": "SYNC_CORRECTION_REQUEST",
        "source": source,
        "target": request.device_id,
        "sequence": sequence,
        "timestamp": request.timestamp,
        "message_id": message_id or request.transaction_id,
        "payload": request.to_wire_payload(),
    }


def build_wire_correction_response(
    response: SyncCorrectionResponse,
    *,
    target: str = "hhip",
    sequence: int = 1,
    message_id: str | None = None,
) -> dict[str, Any]:
    """Build HHIP Protocol v1 envelope for SYNC_CORRECTION_RESPONSE."""
    return {
        "version": 1,
        "type": "SYNC_CORRECTION_RESPONSE",
        "source": response.device_id,
        "target": target,
        "sequence": sequence,
        "timestamp": response.timestamp,
        "message_id": message_id or f"{response.transaction_id}-resp",
        "payload": response.to_event_payload(),
    }
```

## `engine\discovery\handshake.py`

```python
"""HHIP HELLO handshake for discovered serial devices."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol

from engine.protocol.messages import MessageType, create_message, validate_message

HHIP_DISCOVERY_SOURCE = "hhip-discovery"


class Transport(Protocol):
    port: str

    def connect(self) -> None: ...
    def disconnect(self) -> None: ...
    def send(self, message: dict) -> None: ...
    def receive(self) -> Optional[dict]: ...


@dataclass
class HandshakeResult:
    success: bool
    hhip_firmware: bool = False
    device_id: Optional[str] = None
    device_type: Optional[str] = None
    firmware_version: Optional[str] = None
    capabilities: list[str] = field(default_factory=list)
    raw_messages: list[dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None


def _parse_capabilities(payload: dict[str, Any]) -> list[str]:
    caps = payload.get("capabilities") or payload.get("supported_capabilities") or []
    if isinstance(caps, str):
        return [c.strip() for c in caps.split(",") if c.strip()]
    if isinstance(caps, list):
        return [str(c) for c in caps]
    return []


def perform_handshake(
    transport: Transport,
    *,
    listen_ms: int = 400,
    timeout_s: float = 1.2,
    sequence: int = 1,
) -> HandshakeResult:
    """Attempt HHIP handshake on an open transport.

    1. Listen briefly for a spontaneous device HELLO.
    2. Send HELLO from HHIP discovery.
    3. Wait for HELLO_ACK or HELLO response.
    """
    raw_messages: list[dict] = []
    deadline = time.monotonic() + timeout_s

    def _poll_until(deadline_at: float) -> Optional[dict]:
        while time.monotonic() < deadline_at:
            try:
                msg = transport.receive()
            except Exception as exc:  # noqa: BLE001
                return None
            if msg is not None:
                raw_messages.append(msg)
                return msg
            time.sleep(0.05)
        return None

    # Phase 1 — device may announce on boot
    boot_msg = _poll_until(time.monotonic() + listen_ms / 1000.0)
    if boot_msg:
        parsed = _handle_inbound(boot_msg, transport, sequence)
        if parsed.success:
            parsed.raw_messages = raw_messages
            return parsed

    # Phase 2 — HHIP initiates HELLO
    hello = create_message(
        type_=MessageType.HELLO,
        source=HHIP_DISCOVERY_SOURCE,
        target="device",
        sequence=sequence,
        payload={"probe": True, "client": "hhip-discovery"},
    )
    try:
        transport.send(hello)
    except Exception as exc:  # noqa: BLE001
        return HandshakeResult(success=False, error=str(exc), raw_messages=raw_messages)

    ack_msg = _poll_until(deadline)
    if ack_msg is None:
        return HandshakeResult(
            success=False,
            hhip_firmware=False,
            error="Handshake timeout",
            raw_messages=raw_messages,
        )

    parsed = _handle_inbound(ack_msg, transport, sequence + 1)
    parsed.raw_messages = raw_messages
    return parsed


def _handle_inbound(message: dict, transport: Transport, ack_sequence: int) -> HandshakeResult:
    errors = validate_message(message)
    if errors:
        return HandshakeResult(success=False, error="; ".join(errors))

    msg_type = message.get("type")
    payload = message.get("payload") or {}
    source = message.get("source") or payload.get("device_id")

    if msg_type == MessageType.HELLO:
        device_id = str(source or payload.get("device_id") or "device")
        device_type = str(payload.get("device_type") or "unknown")
        firmware = payload.get("firmware_version")
        caps = _parse_capabilities(payload)
        _send_hello_ack(transport, device_id, ack_sequence)
        return HandshakeResult(
            success=True,
            hhip_firmware=True,
            device_id=device_id,
            device_type=device_type,
            firmware_version=str(firmware) if firmware is not None else None,
            capabilities=caps,
        )

    if msg_type == MessageType.HELLO_ACK:
        device_id = str(payload.get("device_id") or source or "device")
        device_type = str(payload.get("device_type") or payload.get("board_type") or "unknown")
        firmware = payload.get("firmware_version")
        caps = _parse_capabilities(payload)
        return HandshakeResult(
            success=True,
            hhip_firmware=True,
            device_id=device_id,
            device_type=device_type,
            firmware_version=str(firmware) if firmware is not None else None,
            capabilities=caps,
        )

    return HandshakeResult(success=False, error=f"Unexpected message type: {msg_type}")


def _send_hello_ack(transport: Transport, device_id: str, sequence: int) -> None:
    ack = create_message(
        type_=MessageType.HELLO_ACK,
        source=HHIP_DISCOVERY_SOURCE,
        target=device_id,
        sequence=sequence,
        payload={"engine_version": "discovery-1.0", "status": "ok"},
    )
    try:
        transport.send(ack)
    except Exception:
        pass
```

## `engine\discovery\identify.py`

```python
"""USB VID/PID and description heuristics for board identification."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class BoardSignature:
    board_type: str
    label: str
    vid: Optional[int] = None
    pid: Optional[int] = None
    description_contains: tuple[str, ...] = ()
    manufacturer_contains: tuple[str, ...] = ()


# Well-known USB identities for supported boards.
BOARD_SIGNATURES: list[BoardSignature] = [
    BoardSignature("arduino-uno", "Arduino Uno R3", 0x2341, 0x0043),
    BoardSignature("arduino-uno", "Arduino Uno R3", 0x2341, 0x0001),
    BoardSignature("arduino-mega", "Arduino Mega 2560", 0x2341, 0x0010),
    BoardSignature("arduino-mega", "Arduino Mega 2560", 0x2341, 0x0042),
    BoardSignature("arduino-nano", "Arduino Nano", 0x2341, 0x0050),
    BoardSignature("esp32", "ESP32 DevKit", 0x10C4, 0xEA60, ("CP210", "USB to UART")),
    BoardSignature("esp32", "ESP32 DevKit", 0x1A86, 0x55D4, ("CH340", "USB-SERIAL")),
    BoardSignature("esp32", "ESP32 DevKit", 0x303A, 0x1001, ("Espressif", "JTAG")),
    BoardSignature("esp8266", "ESP8266", 0x1A86, 0x7523, ("CH340",)),
    BoardSignature("esp8266", "ESP8266", 0x10C4, 0xEA60, ("CP210",)),
    BoardSignature("stm32", "STM32 Blue Pill", 0x0483, 0x5740),
    BoardSignature("stm32", "STM32", 0x0483, 0x3748, ("STM32",)),
    BoardSignature("stm32", "STM32", 0x1EAF, 0x0003, ("LeafLabs", "Maple")),
    BoardSignature("raspberry-pi-pico", "Raspberry Pi Pico", 0x2E8A, 0x0005),
    BoardSignature("raspberry-pi-pico", "Raspberry Pi Pico", 0x2E8A, 0x000A),
    # CH340 clones often used for Arduino Nano / Uno clones
    BoardSignature("arduino-nano", "Arduino Nano (CH340)", 0x1A86, 0x7523, ("CH340",)),
    BoardSignature("arduino-uno", "Arduino Uno (CH340)", 0x1A86, 0x7523, ("CH340", "Arduino")),
]

DESCRIPTION_HINTS: list[tuple[str, str, str]] = [
    ("arduino uno", "arduino-uno", "Arduino Uno R3"),
    ("mega 2560", "arduino-mega", "Arduino Mega 2560"),
    ("arduino nano", "arduino-nano", "Arduino Nano"),
    ("esp32", "esp32", "ESP32 DevKit V1"),
    ("esp8266", "esp8266", "ESP8266"),
    ("stm32", "stm32", "STM32"),
    ("blue pill", "stm32", "STM32 Blue Pill"),
    ("pico", "raspberry-pi-pico", "Raspberry Pi Pico"),
]


def identify_board(
    *,
    vid: Optional[int],
    pid: Optional[int],
    description: Optional[str],
    manufacturer: Optional[str],
) -> tuple[str, str]:
    """Return ``(board_type, label)`` for a serial port."""
    desc = (description or "").lower()
    mfr = (manufacturer or "").lower()

    for sig in BOARD_SIGNATURES:
        if sig.vid is not None and sig.pid is not None:
            if vid == sig.vid and pid == sig.pid:
                if sig.description_contains and not any(h.lower() in desc for h in sig.description_contains):
                    continue
                if sig.manufacturer_contains and not any(h.lower() in mfr for h in sig.manufacturer_contains):
                    continue
                return sig.board_type, sig.label

    combined = f"{desc} {mfr}".strip()
    for hint, board_type, label in DESCRIPTION_HINTS:
        if hint in combined:
            return board_type, label

    if vid is not None or desc or mfr:
        return "unknown-serial", "Unknown Serial Device"
    return "unknown-serial", "Unknown Serial Device"
```

## `engine\hybrid\device_agent.py`

```python
"""HHIP firmware agent protocol handler."""

from __future__ import annotations

import time
from typing import Any, Optional

from engine.protocol.messages import MessageType, create_message, validate_message

from .physical_device import PhysicalDevice, PhysicalPin

AGENT_EVENT_DEVICE_DISCOVERY = "DEVICE_DISCOVERY"
AGENT_EVENT_GPIO_STATE = "GPIO_STATE"
AGENT_CMD_GPIO_WRITE = "GPIO_WRITE"


class DeviceAgent:
    """Speak the hhip_agent firmware protocol over any HardwareTransport."""

    def __init__(self, transport: Any, *, device_id: str = "") -> None:
        self.transport = transport
        self.device_id = device_id
        self._sequence = 0
        self._device: Optional[PhysicalDevice] = None

    @property
    def device(self) -> Optional[PhysicalDevice]:
        return self._device

    def connect(self) -> None:
        self.transport.connect()

    def disconnect(self) -> None:
        self.transport.disconnect()
        if self._device is not None:
            self._device.connected = False

    def poll(self) -> list[dict[str, Any]]:
        """Receive and parse pending agent messages."""
        events: list[dict[str, Any]] = []
        for _ in range(8):
            msg = self.transport.receive()
            if msg is None:
                break
            parsed = self._parse_inbound(msg)
            if parsed:
                events.append(parsed)
        return events

    def wait_for_discovery(self, *, timeout_s: float = 2.0) -> Optional[PhysicalDevice]:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            for event in self.poll():
                if event.get("kind") == AGENT_EVENT_DEVICE_DISCOVERY:
                    return self._device
            time.sleep(0.05)
        return self._device

    def send_gpio_write(self, pin_id: str, value: int) -> dict[str, Any]:
        self._sequence += 1
        message = create_message(
            type_=MessageType.EVENT,
            source="hhip",
            target=self.device_id or "device",
            sequence=self._sequence,
            payload={"event": AGENT_CMD_GPIO_WRITE, "pin": pin_id, "value": int(value)},
        )
        self.transport.send(message)
        return message

    def send_hello_ack(self) -> dict[str, Any]:
        self._sequence += 1
        message = create_message(
            type_=MessageType.HELLO_ACK,
            source="hhip-hybrid",
            target=self.device_id or "device",
            sequence=self._sequence,
            payload={"engine_version": "hybrid-1.0", "status": "ok"},
        )
        self.transport.send(message)
        return message

    def _parse_inbound(self, message: dict[str, Any]) -> Optional[dict[str, Any]]:
        if validate_message(message):
            return None

        msg_type = message.get("type")
        payload = message.get("payload") or {}
        source = str(message.get("source") or "")

        if msg_type == MessageType.HELLO:
            self.device_id = source or str(payload.get("device_id") or "device")
            self._device = PhysicalDevice.from_discovery(
                device_id=self.device_id,
                board_type=str(payload.get("device_type") or payload.get("board_type") or "unknown"),
                port=self._endpoint(),
                firmware_version=str(payload.get("firmware_version") or ""),
                capabilities=_as_list(payload.get("capabilities")),
                pin_specs=payload.get("pins") if isinstance(payload.get("pins"), list) else None,
                transport=self._transport_kind(),
            )
            self.send_hello_ack()
            return {"kind": AGENT_EVENT_DEVICE_DISCOVERY, "device": self._device.to_dict()}

        if msg_type == MessageType.EVENT:
            event_name = str(payload.get("event") or "")
            if event_name == AGENT_EVENT_DEVICE_DISCOVERY:
                self.device_id = str(payload.get("device_id") or source)
                pins_raw = payload.get("pins") or []
                self._device = PhysicalDevice.from_discovery(
                    device_id=self.device_id,
                    board_type=str(payload.get("board_type") or payload.get("device_type") or "unknown"),
                    port=self._endpoint(),
                    label=str(payload.get("label") or ""),
                    firmware_version=str(payload.get("firmware_version") or ""),
                    capabilities=_as_list(payload.get("capabilities")),
                    pin_specs=pins_raw if isinstance(pins_raw, list) else None,
                    transport=self._transport_kind(),
                    vendor=str(payload.get("vendor") or payload.get("manufacturer") or ""),
                    manufacturer=str(payload.get("manufacturer") or payload.get("vendor") or ""),
                )
                if isinstance(pins_raw, list) and pins_raw:
                    self._apply_pin_specs(pins_raw)
                return {"kind": AGENT_EVENT_DEVICE_DISCOVERY, "device": self._device.to_dict()}

            if event_name == AGENT_EVENT_GPIO_STATE:
                pin_id = str(payload.get("pin") or "")
                value = int(payload.get("value", 0))
                if self._device and pin_id:
                    self._device.update_pin_state(pin_id, value)
                return {
                    "kind": AGENT_EVENT_GPIO_STATE,
                    "device_id": self.device_id,
                    "pin": pin_id,
                    "value": value,
                }

            if event_name == AGENT_CMD_GPIO_WRITE:
                return {"kind": AGENT_CMD_GPIO_WRITE, "payload": dict(payload)}

        if msg_type == MessageType.HEARTBEAT:
            self.transport.record_heartbeat()
            return {"kind": "HEARTBEAT", "device_id": self.device_id or source}

        if msg_type in (MessageType.WRITE, MessageType.STATE_UPDATE):
            pin_id = str(payload.get("pin") or "")
            if pin_id and self._device:
                val = payload.get("value", payload.get("state"))
                if isinstance(val, (int, float)):
                    self._device.update_pin_state(pin_id, int(val))
            return {"kind": msg_type, "device_id": self.device_id, "payload": dict(payload)}

        return {"kind": msg_type, "device_id": self.device_id, "payload": dict(payload)}

    def _apply_pin_specs(self, specs: list[Any]) -> None:
        if self._device is None:
            return
        for spec in specs:
            if not isinstance(spec, dict):
                continue
            pid = str(spec.get("pin_id") or spec.get("id") or "")
            if not pid:
                continue
            self._device.pins[pid] = PhysicalPin(
                pin_id=pid,
                name=str(spec.get("name", pid)),
                number=spec.get("number", pid),
                interfaces=_as_list(spec.get("interfaces") or ["gpio"]),
                signal=str(spec.get("signal", "bidirectional")),
                voltage_v=float(spec.get("voltage_v", 3.3)),
                state=int(spec.get("state", 0)),
            )

    def _endpoint(self) -> str:
        return str(
            getattr(self.transport, "port", None)
            or getattr(self.transport, "endpoint", "")
            or ""
        )

    def _transport_kind(self) -> str:
        kind = getattr(self.transport, "kind", None)
        if kind is None:
            return "serial"
        return str(getattr(kind, "value", kind))


def _as_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [v.strip() for v in value.split(",") if v.strip()]
    if isinstance(value, list):
        return [str(v) for v in value]
    return []
```

## `engine\hybrid\hybrid_router.py`

```python
"""Route EventBus GPIO events to physical devices and mirror inbound state."""

from __future__ import annotations

import logging
from typing import Any, Optional

from engine.events.event import Event
from engine.events.event_bus import EventBus
from engine.events.subscriber import EventSubscriber

from .device_agent import AGENT_EVENT_GPIO_STATE, DeviceAgent
from .events import HybridEventType, publish_hybrid_event
from .pin_mapper import PinMapper
from .registry import PhysicalDeviceRegistry

logger = logging.getLogger("hhip.hybrid.router")


class HybridRouter(EventSubscriber):
    """Bridge EventBus GPIO events with physical serial agents."""

    def __init__(
        self,
        registry: PhysicalDeviceRegistry,
        pin_mapper: PinMapper,
        *,
        event_bus: Optional[EventBus] = None,
    ) -> None:
        self.registry = registry
        self.pin_mapper = pin_mapper
        self.event_bus = event_bus
        self._sequence = 0

    def handle_event(self, event: Event) -> None:
        if event.event_type == HybridEventType.GPIO_WRITE:
            self._route_gpio_write(event)
        elif event.event_type == HybridEventType.GPIO_STATE:
            self._mirror_gpio_state(event)

    def poll_physical(self) -> list[dict[str, Any]]:
        """Poll all agents and publish GPIO_STATE / connection events."""
        published: list[dict[str, Any]] = []
        for raw in self.registry.poll_all():
            kind = raw.get("kind")
            if kind == AGENT_EVENT_GPIO_STATE and self.event_bus:
                publish_hybrid_event(
                    self.event_bus,
                    HybridEventType.GPIO_STATE,
                    source=str(raw.get("device_id") or "physical"),
                    payload={
                        "pin": raw.get("pin"),
                        "value": raw.get("value"),
                        "device_id": raw.get("device_id"),
                    },
                )
                published.append(raw)
                self._fanout_to_virtual(raw)
        return published

    def write_gpio(
        self,
        device_id: str,
        pin_id: str,
        value: int,
        *,
        virtual_node_id: str = "",
    ) -> dict[str, Any]:
        agent = self.registry.get_agent(device_id)
        if agent is None:
            raise KeyError(f"physical device not connected: {device_id}")
        message = agent.send_gpio_write(pin_id, value)
        payload = {
            "device_id": device_id,
            "pin": pin_id,
            "value": int(value),
            "virtual_node_id": virtual_node_id,
            "message": message,
        }
        if self.event_bus:
            publish_hybrid_event(
                self.event_bus,
                HybridEventType.GPIO_WRITE,
                source="hhip-hybrid",
                target=device_id,
                payload=payload,
            )
        return payload

    def publish_connected(self, device: dict[str, Any]) -> None:
        if self.event_bus is None:
            return
        publish_hybrid_event(
            self.event_bus,
            HybridEventType.PHYSICAL_DEVICE_CONNECTED,
            source=str(device.get("device_id") or "physical"),
            payload=device,
        )

    def publish_disconnected(self, device_id: str) -> None:
        if self.event_bus is None:
            return
        publish_hybrid_event(
            self.event_bus,
            HybridEventType.PHYSICAL_DEVICE_DISCONNECTED,
            source=device_id,
            payload={"device_id": device_id},
        )

    def _route_gpio_write(self, event: Event) -> None:
        payload = event.payload or {}
        device_id = str(payload.get("device_id") or event.target or "")
        pin_id = str(payload.get("pin") or "")
        value = int(payload.get("value", 0))
        if not device_id or not pin_id:
            return
        try:
            self.write_gpio(device_id, pin_id, value, virtual_node_id=str(payload.get("virtual_node_id") or ""))
        except KeyError:
            logger.warning("[HYBRID] GPIO_WRITE target not found: %s", device_id)

    def _mirror_gpio_state(self, event: Event) -> None:
        if self.event_bus is None:
            return
        publish_hybrid_event(
            self.event_bus,
            HybridEventType.HYBRID_PIN_MIRROR,
            source=event.source,
            payload=event.payload or {},
        )

    def _fanout_to_virtual(self, gpio_event: dict[str, Any]) -> None:
        device_id = str(gpio_event.get("device_id") or "")
        pin_id = str(gpio_event.get("pin") or "")
        value = gpio_event.get("value")
        for conn in self.pin_mapper.connections_for_device(device_id):
            if conn.get("physical_pin_id") != pin_id:
                continue
            if self.event_bus is None:
                continue
            publish_hybrid_event(
                self.event_bus,
                HybridEventType.HYBRID_VIRTUAL_EVENT,
                source=device_id,
                target=str(conn.get("virtual_node_id") or ""),
                payload={
                    "virtual_node_id": conn.get("virtual_node_id"),
                    "virtual_pin_id": conn.get("virtual_pin_id"),
                    "physical_pin_id": pin_id,
                    "value": value,
                    "mirrored": True,
                },
            )
```

## `engine\hybrid\pin_mapper.py`

```python
"""Virtual-to-physical pin mapping for hybrid experiments."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional


class PinMapper:
    """Create and validate virtual↔physical pin connections."""

    def __init__(self, *, storage_path: Optional[Path | str] = None) -> None:
        self._connections: dict[str, dict[str, Any]] = {}
        self._storage_path = Path(storage_path) if storage_path else None
        if self._storage_path and self._storage_path.exists():
            self._load()

    def list_connections(self) -> list[dict[str, Any]]:
        return list(self._connections.values())

    def get_connection(self, connection_id: str) -> Optional[dict[str, Any]]:
        return self._connections.get(connection_id)

    def create_connection(
        self,
        *,
        virtual_node_id: str,
        virtual_pin_id: str,
        physical_device_id: str,
        physical_pin_id: str,
        workspace_id: str = "",
    ) -> dict[str, Any]:
        issues = self.validate(
            virtual_pin_id=virtual_pin_id,
            physical_pin_id=physical_pin_id,
            virtual_interfaces=["digital", "gpio"],
            physical_interfaces=["gpio", "digital", "pwm"],
        )
        connection_id = f"HC{len(self._connections) + 1:04d}"
        record = {
            "connection_id": connection_id,
            "workspace_id": workspace_id,
            "virtual_node_id": virtual_node_id,
            "virtual_pin_id": virtual_pin_id,
            "physical_device_id": physical_device_id,
            "physical_pin_id": physical_pin_id,
            "valid": not issues,
            "issues": issues,
        }
        self._connections[connection_id] = record
        self._persist()
        return record

    def delete_connection(self, connection_id: str) -> bool:
        if connection_id not in self._connections:
            return False
        del self._connections[connection_id]
        self._persist()
        return True

    def connections_for_device(self, physical_device_id: str) -> list[dict[str, Any]]:
        return [
            c for c in self._connections.values() if c["physical_device_id"] == physical_device_id
        ]

    def connections_for_virtual(self, virtual_node_id: str) -> list[dict[str, Any]]:
        return [c for c in self._connections.values() if c["virtual_node_id"] == virtual_node_id]

    @staticmethod
    def validate(
        *,
        virtual_pin_id: str,
        physical_pin_id: str,
        virtual_interfaces: list[str],
        physical_interfaces: list[str],
    ) -> list[str]:
        issues: list[str] = []
        if not virtual_pin_id:
            issues.append("virtual pin is required")
        if not physical_pin_id:
            issues.append("physical pin is required")
        v_set = {i.lower() for i in virtual_interfaces}
        p_set = {i.lower() for i in physical_interfaces}
        if v_set and p_set and not (v_set & p_set):
            issues.append(
                f"incompatible interfaces: virtual={sorted(v_set)} physical={sorted(p_set)}"
            )
        return issues

    def _persist(self) -> None:
        if self._storage_path is None:
            return
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        with self._storage_path.open("w", encoding="utf-8") as fh:
            json.dump({"connections": list(self._connections.values())}, fh, indent=2)
            fh.write("\n")

    def _load(self) -> None:
        try:
            with self._storage_path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError):
            return
        for item in data.get("connections") or []:
            cid = str(item.get("connection_id") or "")
            if cid:
                self._connections[cid] = item
```

## `engine\hybrid\physical_device.py`

```python
"""Physical microcontroller representation for the hybrid device layer.

Sprint 28: wraps universal :class:`HardwareDevice` while keeping the
Sprint 27 ``PhysicalDevice`` API for backward compatibility.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from engine.hybrid.hardware import HardwareDevice, HardwarePin, get_profile_registry


@dataclass
class PhysicalPin:
    pin_id: str
    name: str
    number: int | str
    interfaces: list[str] = field(default_factory=list)
    signal: str = "bidirectional"
    voltage_v: float = 3.3
    state: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "pin_id": self.pin_id,
            "name": self.name,
            "number": self.number,
            "interfaces": list(self.interfaces),
            "signal": self.signal,
            "voltage_v": self.voltage_v,
            "state": self.state,
        }

    @classmethod
    def from_hardware(cls, pin: HardwarePin) -> "PhysicalPin":
        return cls(
            pin_id=pin.pin_id,
            name=pin.name,
            number=pin.number,
            interfaces=list(pin.interfaces),
            signal=pin.signal,
            voltage_v=pin.voltage_v,
            state=pin.state,
        )


@dataclass
class PhysicalDevice:
    """A connected physical board with pin map and capabilities."""

    device_id: str
    board_type: str
    port: str
    label: str = ""
    firmware_version: str = ""
    capabilities: list[str] = field(default_factory=list)
    pins: dict[str, PhysicalPin] = field(default_factory=dict)
    connected: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
    # Sprint 28 universal fields
    vendor: str = ""
    manufacturer: str = ""
    model: str = ""
    category: str = "microcontroller"
    interfaces: list[str] = field(default_factory=list)
    transport: str = "serial"
    connection_state: str = "disconnected"
    profile_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "device_id": self.device_id,
            "board_type": self.board_type,
            "port": self.port,
            "endpoint": self.port,
            "label": self.label or self.model or self.board_type,
            "firmware_version": self.firmware_version,
            "capabilities": list(self.capabilities),
            "pins": [p.to_dict() for p in self.pins.values()],
            "connected": self.connected,
            "connection_state": self.connection_state or ("connected" if self.connected else "disconnected"),
            "vendor": self.vendor,
            "manufacturer": self.manufacturer or self.vendor,
            "model": self.model or self.label or self.board_type,
            "category": self.category,
            "interfaces": list(self.interfaces),
            "transport": self.transport,
            "communication_method": self.transport,
            "profile_id": self.profile_id,
            "metadata": dict(self.metadata),
        }

    def list_pins(self) -> list[dict[str, Any]]:
        return [p.to_dict() for p in self.pins.values()]

    def get_pin(self, pin_id: str) -> Optional[PhysicalPin]:
        return self.pins.get(pin_id)

    def update_pin_state(self, pin_id: str, value: int) -> None:
        pin = self.pins.get(pin_id)
        if pin is not None:
            pin.state = int(value)

    @classmethod
    def from_hardware(cls, device: HardwareDevice) -> "PhysicalDevice":
        pins = {pid: PhysicalPin.from_hardware(p) for pid, p in device.pins.items()}
        caps = [c.name if hasattr(c, "name") else str(c) for c in device.capabilities]
        return cls(
            device_id=device.device_id,
            board_type=device.board_type,
            port=device.endpoint,
            label=device.label,
            firmware_version=device.firmware_version,
            capabilities=caps,
            pins=pins,
            connected=device.connected,
            metadata=dict(device.metadata),
            vendor=device.vendor,
            manufacturer=device.manufacturer or device.vendor,
            model=device.model,
            category=device.category,
            interfaces=list(device.interfaces),
            transport=device.transport,
            connection_state=device.connection_state.value,
            profile_id=device.profile_id,
        )

    @classmethod
    def from_discovery(
        cls,
        *,
        device_id: str,
        board_type: str,
        port: str,
        label: str = "",
        firmware_version: str = "",
        capabilities: Optional[list[str]] = None,
        pin_specs: Optional[list[dict[str, Any]]] = None,
        transport: str = "",
        vendor: str = "",
        manufacturer: str = "",
        profiles_dir: Any = None,
    ) -> "PhysicalDevice":
        hw = HardwareDevice.from_discovery(
            device_id=device_id,
            board_type=board_type,
            port=port,
            label=label,
            firmware_version=firmware_version,
            capabilities=capabilities,
            pin_specs=pin_specs,
            transport=transport,
            vendor=vendor,
            manufacturer=manufacturer,
            profiles_dir=profiles_dir,
        )
        return cls.from_hardware(hw)


def _default_pins_for_board(board_type: str) -> list[dict[str, Any]]:
    profile = get_profile_registry().resolve_board_type(board_type)
    return list(profile.pins)
```

## `engine\communication\serial_adapter.py`

```python
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
```

## 2. Existing firmware source (C/C++)

## `firmware\esp32\hhip_device\hhip_device.ino`

```cpp
/*
 * HHIP Device Firmware — ESP32
 *
 * Phase 1.3 (PoC-01): HELLO / HELLO_ACK / HEARTBEAT / ACK over
 * newline-delimited JSON.
 *
 * Phase 1.4: adds a physical button (input, STATE_UPDATE source) and
 * a physical LED (output, STATE_UPDATE sink), extending — not
 * replacing — the Phase 1.3 message loop.
 *
 * Protocol: HHIP Protocol Version 1 (mirrors engine/protocol/messages.py)
 *
 * Dependency note (flagged per project rule "explain decisions that
 * affect the architecture before implementing them"): this firmware
 * uses the ArduinoJson library (https://arduinojson.org) rather than
 * hand-built JSON strings. Hand-rolled JSON on a microcontroller is a
 * common source of subtle bugs (escaping, buffer sizing) and
 * ArduinoJson is small, well-tested, and the de-facto standard for
 * exactly this use case — this is the "strong technical reason"
 * exception to "avoid unnecessary dependencies". Install via the
 * Arduino Library Manager: "ArduinoJson" (v6.x).
 *
 * Does not yet read a wall-clock time from the host, so `timestamp`
 * is device uptime in milliseconds (millis()), not epoch time. Once
 * Phase 1.5 (synchronization) exists, HHIP can supply a time
 * reference during/after HELLO_ACK.
 */

#include <ArduinoJson.h>

// ---- Configuration --------------------------------------------------

static const char* DEVICE_ID = "esp32_01";
static const char* DEVICE_TYPE = "esp32";
static const char* FIRMWARE_VERSION = "0.2.0";
static const uint32_t HEARTBEAT_INTERVAL_MS = 5000;
static const int PROTOCOL_VERSION = 1;
static const long SERIAL_BAUD = 115200;

// Phase 1.4: physical button (input) and physical LED (output).
// BUTTON_PIN uses INPUT_PULLUP, so the button should wire the pin to
// GND when pressed (active LOW) — no external resistor needed on
// most boards. LED_PIN defaults to GPIO2, the commonly-built-in LED
// on many ESP32 dev boards; change it if your board differs.
static const int BUTTON_PIN = 4;
static const int LED_PIN = 2;
static const uint32_t BUTTON_DEBOUNCE_MS = 50;

// Where an outgoing STATE_UPDATE from this device's button should be
// addressed. Matches engine/main.py's DEFAULT_VIRTUAL_LED_ID.
static const char* VIRTUAL_LED_TARGET = "virtual_led_01";

// ---- State ------------------------------------------------------------

static uint32_t outgoingSequence = 0;
static uint32_t lastHeartbeatMillis = 0;
static bool helloAcknowledged = false;

static String incomingLine;

// Phase 1.4 button debounce state.
static int lastStableButtonState = HIGH;   // HIGH = released (INPUT_PULLUP, active LOW)
static int lastRawButtonState = HIGH;
static uint32_t lastButtonChangeMillis = 0;


// ---- Helpers ------------------------------------------------------------

// Generates a reasonably unique message id without pulling in a UUID
// library. Not globally/cryptographically unique — sufficient for
// tracing/dedup within a single PoC-01 session.
String generateMessageId() {
  static uint32_t counter = 0;
  counter++;
  return String(DEVICE_ID) + "-" + String(millis()) + "-" + String(counter);
}

void sendMessage(const char* type, const char* target, JsonObject payload) {
  StaticJsonDocument<256> doc;
  doc["version"] = PROTOCOL_VERSION;
  doc["message_id"] = generateMessageId();
  doc["type"] = type;
  doc["source"] = DEVICE_ID;
  doc["target"] = target;
  doc["sequence"] = ++outgoingSequence;
  doc["timestamp"] = (uint32_t)millis();  // device uptime ms, see file header note
  doc["payload"] = payload;

  serializeJson(doc, Serial);
  Serial.print('\n');
}

void sendHello() {
  StaticJsonDocument<128> payloadDoc;
  JsonObject payload = payloadDoc.to<JsonObject>();
  payload["device_type"] = DEVICE_TYPE;
  payload["firmware_version"] = FIRMWARE_VERSION;
  sendMessage("HELLO", "hhip", payload);
}

void sendHeartbeat() {
  StaticJsonDocument<64> payloadDoc;
  JsonObject payload = payloadDoc.to<JsonObject>();
  sendMessage("HEARTBEAT", "hhip", payload);
}

// Phase 1.4: sends a STATE_UPDATE reporting this device's physical
// button state to the virtual LED it drives (Demonstration A).
void sendButtonStateUpdate(const char* state) {
  StaticJsonDocument<64> payloadDoc;
  JsonObject payload = payloadDoc.to<JsonObject>();
  payload["state"] = state;
  sendMessage("STATE_UPDATE", VIRTUAL_LED_TARGET, payload);
}

// Phase 1.4: polls the physical button with simple time-based
// debouncing and sends a STATE_UPDATE on genuine state changes only.
void checkButton() {
  int raw = digitalRead(BUTTON_PIN);

  if (raw != lastRawButtonState) {
    lastButtonChangeMillis = millis();
    lastRawButtonState = raw;
  }

  if ((millis() - lastButtonChangeMillis) >= BUTTON_DEBOUNCE_MS && raw != lastStableButtonState) {
    lastStableButtonState = raw;
    // Active LOW: pin reads LOW when pressed (INPUT_PULLUP wired to GND).
    if (raw == LOW) {
      sendButtonStateUpdate("ON");
    } else {
      sendButtonStateUpdate("OFF");
    }
  }
}

void handleIncomingLine(const String& line) {
  if (line.length() == 0) {
    return;
  }

  StaticJsonDocument<256> doc;
  DeserializationError err = deserializeJson(doc, line);
  if (err) {
    // Malformed line; drop it. A diagnostics/ERROR channel back to
    // the host is future work, not required for PoC-01.
    return;
  }

  const char* type = doc["type"];
  if (type == nullptr) {
    return;
  }

  if (strcmp(type, "HELLO_ACK") == 0) {
    helloAcknowledged = true;
  } else if (strcmp(type, "ACK") == 0) {
    // HHIP acknowledged a HEARTBEAT (or other message). Nothing
    // further required in PoC-01 beyond having received it.
  } else if (strcmp(type, "ERROR") == 0) {
    // Error handling policy is defined in later phases; PoC-01 just
    // needs to not crash on receiving one.
  } else if (strcmp(type, "STATE_UPDATE") == 0) {
    handleStateUpdate(doc);
  }
}

// Phase 1.4: applies an inbound STATE_UPDATE to the physical LED
// (Demonstration B), if this message is actually addressed to us —
// `target` is checked explicitly per the protocol's addressing
// semantics, even though this point-to-point serial link currently
// has only one possible recipient.
void handleStateUpdate(const JsonDocument& doc) {
  const char* target = doc["target"];
  if (target == nullptr || strcmp(target, DEVICE_ID) != 0) {
    return;  // not addressed to this device; ignore
  }

  const char* state = doc["payload"]["state"];
  if (state == nullptr) {
    return;
  }

  if (strcmp(state, "ON") == 0) {
    digitalWrite(LED_PIN, HIGH);
  } else if (strcmp(state, "OFF") == 0) {
    digitalWrite(LED_PIN, LOW);
  } else {
    return;  // unrecognized state; don't ACK something we didn't apply
  }

  StaticJsonDocument<64> payloadDoc;
  JsonObject ackPayload = payloadDoc.to<JsonObject>();
  ackPayload["ack_type"] = "STATE_UPDATE";
  sendMessage("ACK", "hhip", ackPayload);
}

// ---- Arduino entry points -----------------------------------------------

void setup() {
  Serial.begin(SERIAL_BAUD);
  // Give the host side a moment to open the port before we start
  // talking; avoids losing the very first HELLO on some USB-serial
  // chipsets that reset the ESP32 when the port opens.
  delay(1000);

  incomingLine.reserve(256);

  pinMode(BUTTON_PIN, INPUT_PULLUP);
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);
  lastRawButtonState = digitalRead(BUTTON_PIN);
  lastStableButtonState = lastRawButtonState;

  sendHello();
  lastHeartbeatMillis = millis();
}

void loop() {
  // Non-blocking line assembly from Serial.
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\n') {
      handleIncomingLine(incomingLine);
      incomingLine = "";
    } else if (c != '\r') {
      incomingLine += c;
    }
  }

  checkButton();

  uint32_t now = millis();
  if (now - lastHeartbeatMillis >= HEARTBEAT_INTERVAL_MS) {
    sendHeartbeat();
    lastHeartbeatMillis = now;
  }
}
```

## `firmware\esp32\sync_agent\sync_agent.ino`

```cpp
/*
 * HHIP ESP32 Sync Agent Prototype (Sprint 16)
 *
 * Measurement + bounded software clock correction (no hardware oscillator change).
 *
 * Receives SYNC_REQUEST / SYNC_CORRECTION_REQUEST over serial (newline-delimited JSON),
 * maintains a software clock offset model, and returns SYNC_RESPONSE /
 * SYNC_CORRECTION_RESPONSE.
 *
 * Protocol: HHIP Protocol Version 1 envelope + Sprint 9/16 sync fields.
 *
 * Dependency: ArduinoJson (Library Manager, v6.x)
 *
 * Flash this sketch alone for sync measurement + correction experiments.
 * Does not replace firmware/esp32/hhip_device/ (full device firmware).
 */

#include <ArduinoJson.h>

static const char* DEVICE_ID = "esp32_01";
static const int PROTOCOL_VERSION = 1;
static const long SERIAL_BAUD = 115200;

static uint32_t outgoingSequence = 0;
static String incomingLine;

// Software clock model — does NOT modify hardware oscillator.
static int32_t softwareClockOffsetMs = 0;
static float accumulatedCorrectionMs = 0.0f;

uint32_t deviceClockNow() {
  return (uint32_t)((int32_t)millis() + softwareClockOffsetMs);
}

String generateMessageId() {
  static uint32_t counter = 0;
  counter++;
  return String(DEVICE_ID) + "-" + String(millis()) + "-" + String(counter);
}

void sendSyncResponse(JsonObjectConst requestDoc) {
  uint32_t device_timestamp = deviceClockNow();

  JsonObjectConst payloadIn = requestDoc["payload"].as<JsonObjectConst>();

  uint32_t sequence_number = 0;
  if (!payloadIn.isNull() && payloadIn.containsKey("sequence_number")) {
    sequence_number = payloadIn["sequence_number"] | 0;
  } else if (requestDoc.containsKey("sequence")) {
    sequence_number = requestDoc["sequence"] | 0;
  }

  const char* correlation_id = "";
  if (!payloadIn.isNull() && payloadIn["correlation_id"].is<const char*>()) {
    correlation_id = payloadIn["correlation_id"];
  }

  uint32_t server_timestamp = 0;
  if (!payloadIn.isNull()) {
    if (payloadIn.containsKey("server_timestamp")) {
      server_timestamp = payloadIn["server_timestamp"] | 0;
    } else if (payloadIn.containsKey("request_time")) {
      server_timestamp = payloadIn["request_time"] | 0;
    }
  }

  const char* request_id = "";
  if (!payloadIn.isNull() && payloadIn["request_id"].is<const char*>()) {
    request_id = payloadIn["request_id"];
  } else if (requestDoc["message_id"].is<const char*>()) {
    request_id = requestDoc["message_id"];
  }

  StaticJsonDocument<384> doc;
  doc["version"] = PROTOCOL_VERSION;
  doc["message_id"] = generateMessageId();
  doc["type"] = "SYNC_RESPONSE";
  doc["source"] = DEVICE_ID;
  doc["target"] = "hhip";
  doc["sequence"] = ++outgoingSequence;
  doc["timestamp"] = device_timestamp;

  JsonObject payload = doc.createNestedObject("payload");
  payload["sequence_number"] = sequence_number;
  payload["device_id"] = DEVICE_ID;
  payload["server_timestamp"] = server_timestamp;
  payload["device_timestamp"] = device_timestamp;
  payload["correlation_id"] = correlation_id;
  payload["request_id"] = request_id;
  payload["request_time"] = server_timestamp;
  payload["server_timestamp"] = device_timestamp;
  payload["server_timestamp_host"] = server_timestamp;
  payload["software_clock_offset"] = softwareClockOffsetMs;

  serializeJson(doc, Serial);
  Serial.print('\n');
}

void sendCorrectionResponse(JsonObjectConst requestDoc, bool applied) {
  uint32_t device_timestamp = deviceClockNow();

  JsonObjectConst payloadIn = requestDoc["payload"].as<JsonObjectConst>();

  const char* transaction_id = "";
  if (!payloadIn.isNull() && payloadIn["transaction_id"].is<const char*>()) {
    transaction_id = payloadIn["transaction_id"];
  } else if (requestDoc["message_id"].is<const char*>()) {
    transaction_id = requestDoc["message_id"];
  }

  float correction_step = 0.0f;
  if (!payloadIn.isNull() && payloadIn.containsKey("correction_step")) {
    correction_step = payloadIn["correction_step"] | 0.0f;
  }

  const char* correlation_id = "";
  if (!payloadIn.isNull() && payloadIn["correlation_id"].is<const char*>()) {
    correlation_id = payloadIn["correlation_id"];
  }

  StaticJsonDocument<384> doc;
  doc["version"] = PROTOCOL_VERSION;
  doc["message_id"] = generateMessageId();
  doc["type"] = "SYNC_CORRECTION_RESPONSE";
  doc["source"] = DEVICE_ID;
  doc["target"] = "hhip";
  doc["sequence"] = ++outgoingSequence;
  doc["timestamp"] = device_timestamp;

  JsonObject payload = doc.createNestedObject("payload");
  payload["transaction_id"] = transaction_id;
  payload["device_id"] = DEVICE_ID;
  payload["correction_step"] = correction_step;
  payload["timestamp"] = device_timestamp;
  payload["applied"] = applied;
  payload["accumulated_correction"] = accumulatedCorrectionMs;
  payload["software_clock_offset"] = (float)softwareClockOffsetMs;
  payload["correlation_id"] = correlation_id;

  serializeJson(doc, Serial);
  Serial.print('\n');
}

void handleCorrectionRequest(JsonObjectConst requestDoc) {
  JsonObjectConst payloadIn = requestDoc["payload"].as<JsonObjectConst>();
  if (payloadIn.isNull()) {
    sendCorrectionResponse(requestDoc, false);
    return;
  }

  float correction_step = payloadIn["correction_step"] | 0.0f;

  // Apply bounded software clock adjustment (device-side mirror of host step).
  // Positive step = device was ahead → subtract from software clock.
  int32_t stepMs = (int32_t)correction_step;
  softwareClockOffsetMs -= stepMs;
  accumulatedCorrectionMs += abs(correction_step);

  sendCorrectionResponse(requestDoc, true);
}

void handleIncomingLine(const String& line) {
  if (line.length() == 0) {
    return;
  }

  StaticJsonDocument<512> doc;
  DeserializationError err = deserializeJson(doc, line);
  if (err) {
    return;
  }

  const char* type = doc["type"];
  if (type == nullptr) {
    return;
  }

  if (strcmp(type, "SYNC_REQUEST") == 0) {
    sendSyncResponse(doc.as<JsonObjectConst>());
  } else if (strcmp(type, "SYNC_CORRECTION_REQUEST") == 0) {
    handleCorrectionRequest(doc.as<JsonObjectConst>());
  }
}

void setup() {
  Serial.begin(SERIAL_BAUD);
  delay(200);
  StaticJsonDocument<128> hello;
  hello["version"] = PROTOCOL_VERSION;
  hello["message_id"] = generateMessageId();
  hello["type"] = "HELLO";
  hello["source"] = DEVICE_ID;
  hello["target"] = "hhip";
  hello["sequence"] = ++outgoingSequence;
  hello["timestamp"] = (uint32_t)millis();
  JsonObject payload = hello.createNestedObject("payload");
  payload["device_type"] = "esp32";
  payload["firmware_version"] = "sync_agent_0.2.0";
  payload["sync_agent"] = true;
  payload["correction_agent"] = true;
  serializeJson(hello, Serial);
  Serial.print('\n');
}

void loop() {
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\n') {
      handleIncomingLine(incomingLine);
      incomingLine = "";
    } else if (c != '\r') {
      incomingLine += c;
      if (incomingLine.length() > 512) {
        incomingLine = "";
      }
    }
  }
}
```

## `firmware\hhip_agent\arduino_uno\hhip_agent.ino`

```cpp
/*
 * HHIP Hybrid Agent — Arduino Uno (Sprint 27)
 *
 * Newline-delimited JSON @ 115200.
 * Minimal JSON builder (no external libraries).
 */

static const long SERIAL_BAUD = 115200;
static const int PROTOCOL_VERSION = 1;
static const uint32_t HEARTBEAT_INTERVAL_MS = 5000;
static const int LED_PIN = 13;

static char deviceId[24] = "uno_000000";
static uint32_t outgoingSequence = 0;
static uint32_t lastHeartbeatMs = 0;
static String incomingLine;

static int pinStates[3] = {0, 0, 0};  // D2, D13, A0 mapped

uint32_t simpleHash() {
  uint32_t h = 0;
  for (int i = 0; i < 6; i++) {
    h = h * 31 + analogRead(A0) + i * 17;
  }
  return h;
}

void sendLine(const String& line) {
  Serial.println(line);
}

String nextMessageId() {
  static uint32_t counter = 0;
  counter++;
  return String(deviceId) + "-" + String(millis()) + "-" + String(counter);
}

void sendHeartbeat() {
  String msg = "{";
  msg += "\"version\":" + String(PROTOCOL_VERSION) + ",";
  msg += "\"message_id\":\"" + nextMessageId() + "\",";
  msg += "\"type\":\"HEARTBEAT\",";
  msg += "\"source\":\"" + String(deviceId) + "\",";
  msg += "\"target\":\"hhip\",";
  msg += "\"sequence\":" + String(++outgoingSequence) + ",";
  msg += "\"timestamp\":" + String(millis()) + ",";
  msg += "\"payload\":{}";
  msg += "}";
  sendLine(msg);
}

void sendGpioState(const char* pinId, int value) {
  String msg = "{";
  msg += "\"version\":" + String(PROTOCOL_VERSION) + ",";
  msg += "\"message_id\":\"" + nextMessageId() + "\",";
  msg += "\"type\":\"EVENT\",";
  msg += "\"source\":\"" + String(deviceId) + "\",";
  msg += "\"target\":\"hhip\",";
  msg += "\"sequence\":" + String(++outgoingSequence) + ",";
  msg += "\"timestamp\":" + String(millis()) + ",";
  msg += "\"payload\":{\"event\":\"GPIO_STATE\",\"pin\":\"" + String(pinId) + "\",\"value\":" + String(value) + "}";
  msg += "}";
  sendLine(msg);
}

void sendDeviceDiscovery() {
  String msg = "{";
  msg += "\"version\":" + String(PROTOCOL_VERSION) + ",";
  msg += "\"message_id\":\"" + nextMessageId() + "\",";
  msg += "\"type\":\"EVENT\",";
  msg += "\"source\":\"" + String(deviceId) + "\",";
  msg += "\"target\":\"hhip\",";
  msg += "\"sequence\":" + String(++outgoingSequence) + ",";
  msg += "\"timestamp\":" + String(millis()) + ",";
  msg += "\"payload\":{";
  msg += "\"event\":\"DEVICE_DISCOVERY\",";
  msg += "\"device_id\":\"" + String(deviceId) + "\",";
  msg += "\"board_type\":\"arduino-uno\",";
  msg += "\"device_type\":\"arduino-uno\",";
  msg += "\"firmware_version\":\"1.0.0-hhip-agent\",";
  msg += "\"label\":\"Arduino Uno HHIP Agent\",";
  msg += "\"capabilities\":[\"gpio\",\"adc\",\"pwm\"],";
  msg += "\"pins\":[";
  msg += "{\"pin_id\":\"D2\",\"name\":\"Digital 2\",\"number\":2,\"interfaces\":[\"gpio\"],\"state\":" + String(pinStates[0]) + "},";
  msg += "{\"pin_id\":\"D13\",\"name\":\"LED\",\"number\":13,\"interfaces\":[\"gpio\"],\"state\":" + String(pinStates[1]) + "},";
  msg += "{\"pin_id\":\"A0\",\"name\":\"Analog 0\",\"number\":\"A0\",\"interfaces\":[\"adc\"],\"signal\":\"input\",\"state\":" + String(pinStates[2]) + "}";
  msg += "]}}";
  sendLine(msg);
}

void applyGpioWrite(const String& pinId, int value) {
  if (pinId == "D13") {
    pinStates[1] = value ? 1 : 0;
    digitalWrite(LED_PIN, pinStates[1] ? HIGH : LOW);
    sendGpioState("D13", pinStates[1]);
  } else if (pinId == "D2") {
    pinStates[0] = value ? 1 : 0;
    pinMode(2, OUTPUT);
    digitalWrite(2, pinStates[0] ? HIGH : LOW);
    sendGpioState("D2", pinStates[0]);
  }
}

bool jsonExtract(const String& json, const String& key, String& out) {
  String needle = "\"" + key + "\":";
  int idx = json.indexOf(needle);
  if (idx < 0) return false;
  idx += needle.length();
  while (idx < (int)json.length() && json[idx] == ' ') idx++;
  if (idx >= (int)json.length()) return false;
  if (json[idx] == '"') {
    idx++;
    int end = json.indexOf('"', idx);
    if (end < 0) return false;
    out = json.substring(idx, end);
    return true;
  }
  int end = idx;
  while (end < (int)json.length() && json[end] != ',' && json[end] != '}') end++;
  out = json.substring(idx, end);
  return true;
}

void handleLine(const String& line) {
  String type, event, pin, valueStr;
  if (!jsonExtract(line, "type", type)) return;

  if (type == "EVENT") {
    jsonExtract(line, "event", event);
    if (event == "GPIO_WRITE") {
      jsonExtract(line, "pin", pin);
      jsonExtract(line, "value", valueStr);
      applyGpioWrite(pin, valueStr.toInt());
    } else if (type == "HELLO" || type == "HELLO_ACK") {
      sendDeviceDiscovery();
    }
    return;
  }

  if (type == "WRITE") {
    jsonExtract(line, "pin", pin);
    jsonExtract(line, "value", valueStr);
    applyGpioWrite(pin, valueStr.toInt());
    return;
  }

  if (type == "HELLO" || type == "HELLO_ACK") {
    sendDeviceDiscovery();
  }
}

void setup() {
  Serial.begin(SERIAL_BAUD);
  pinMode(LED_PIN, OUTPUT);
  snprintf(deviceId, sizeof(deviceId), "uno_%06lu", (unsigned long)(simpleHash() % 1000000UL));
  delay(300);
  sendDeviceDiscovery();
  lastHeartbeatMs = millis();
}

void loop() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n') {
      if (incomingLine.length() > 0) {
        handleLine(incomingLine);
        incomingLine = "";
      }
    } else {
      incomingLine += c;
    }
  }

  if (millis() - lastHeartbeatMs >= HEARTBEAT_INTERVAL_MS) {
    sendHeartbeat();
    lastHeartbeatMs = millis();
  }
}
```

## `firmware\hhip_agent\esp32\hhip_agent.ino`

```cpp
/*
 * HHIP Hybrid Agent — ESP32 (Sprint 27)
 *
 * Newline-delimited JSON over Serial @ 115200.
 * Messages: DEVICE_DISCOVERY (EVENT), HEARTBEAT, GPIO_STATE (EVENT),
 * accepts GPIO_WRITE (EVENT) and WRITE.
 *
 * Requires ArduinoJson v6 (Library Manager).
 */

#include <ArduinoJson.h>
#include <WiFi.h>

static const long SERIAL_BAUD = 115200;
static const int PROTOCOL_VERSION = 1;
static const uint32_t HEARTBEAT_INTERVAL_MS = 5000;
static const char* BOARD_TYPE = "esp32";
static const char* FIRMWARE_VERSION = "1.0.0-hhip-agent";

// Built-in LED on many ESP32 dev boards
static const int LED_PIN = 2;
static const int BUTTON_PIN = 4;

static char deviceId[32];
static uint32_t outgoingSequence = 0;
static uint32_t lastHeartbeatMs = 0;
static String incomingLine;

static const int MAX_PINS = 4;
struct PinSpec {
  const char* pin_id;
  const char* name;
  int number;
  int state;
};

static PinSpec pins[MAX_PINS] = {
  {"D2", "GPIO2", 2, 0},
  {"D4", "GPIO4", 4, 0},
  {"D13", "GPIO13", 13, 0},
  {"D25", "GPIO25", 25, 0},
};

String generateMessageId() {
  static uint32_t counter = 0;
  counter++;
  return String(deviceId) + "-" + String(millis()) + "-" + String(counter);
}

void sendJsonDoc(JsonDocument& doc) {
  serializeJson(doc, Serial);
  Serial.print('\n');
}

void sendEvent(const char* eventName, JsonObject payload) {
  StaticJsonDocument<512> doc;
  doc["version"] = PROTOCOL_VERSION;
  doc["message_id"] = generateMessageId();
  doc["type"] = "EVENT";
  doc["source"] = deviceId;
  doc["target"] = "hhip";
  doc["sequence"] = ++outgoingSequence;
  doc["timestamp"] = (uint32_t)millis();
  JsonObject pl = doc.createNestedObject("payload");
  pl["event"] = eventName;
  for (JsonPair kv : payload) {
    pl[kv.key()] = kv.value();
  }
  sendJsonDoc(doc);
}

void sendHeartbeat() {
  StaticJsonDocument<128> doc;
  doc["version"] = PROTOCOL_VERSION;
  doc["message_id"] = generateMessageId();
  doc["type"] = "HEARTBEAT";
  doc["source"] = deviceId;
  doc["target"] = "hhip";
  doc["sequence"] = ++outgoingSequence;
  doc["timestamp"] = (uint32_t)millis();
  doc.createNestedObject("payload");
  sendJsonDoc(doc);
}

void sendGpioState(const char* pinId, int value) {
  StaticJsonDocument<128> payloadDoc;
  JsonObject payload = payloadDoc.to<JsonObject>();
  payload["pin"] = pinId;
  payload["value"] = value;
  sendEvent("GPIO_STATE", payload);
}

void sendDeviceDiscovery() {
  StaticJsonDocument<768> payloadDoc;
  JsonObject payload = payloadDoc.to<JsonObject>();
  payload["event"] = "DEVICE_DISCOVERY";
  payload["device_id"] = deviceId;
  payload["board_type"] = BOARD_TYPE;
  payload["device_type"] = BOARD_TYPE;
  payload["firmware_version"] = FIRMWARE_VERSION;
  payload["label"] = "ESP32 HHIP Agent";

  JsonArray caps = payload.createNestedArray("capabilities");
  caps.add("gpio");
  caps.add("pwm");
  caps.add("adc");
  caps.add("wifi");

  JsonArray pinArr = payload.createNestedArray("pins");
  for (int i = 0; i < MAX_PINS; i++) {
    JsonObject p = pinArr.createNestedObject();
    p["pin_id"] = pins[i].pin_id;
    p["name"] = pins[i].name;
    p["number"] = pins[i].number;
    p["interfaces"] = "gpio,pwm";
    p["state"] = pins[i].state;
  }

  StaticJsonDocument<896> doc;
  doc["version"] = PROTOCOL_VERSION;
  doc["message_id"] = generateMessageId();
  doc["type"] = "EVENT";
  doc["source"] = deviceId;
  doc["target"] = "hhip";
  doc["sequence"] = ++outgoingSequence;
  doc["timestamp"] = (uint32_t)millis();
  doc["payload"] = payload;
  sendJsonDoc(doc);
}

void generateDeviceId() {
  uint64_t mac = ESP.getEfuseMac();
  snprintf(deviceId, sizeof(deviceId), "esp32_%04X%08X",
           (uint16_t)(mac >> 32), (uint32_t)mac);
}

PinSpec* findPin(const char* pinId) {
  for (int i = 0; i < MAX_PINS; i++) {
    if (strcmp(pins[i].pin_id, pinId) == 0) return &pins[i];
  }
  return nullptr;
}

void applyGpioWrite(const char* pinId, int value) {
  PinSpec* pin = findPin(pinId);
  if (pin == nullptr) return;
  pin->state = value ? 1 : 0;
  if (strcmp(pinId, "D13") == 0 || pin->number == LED_PIN) {
    digitalWrite(LED_PIN, pin->state ? HIGH : LOW);
  } else {
    pinMode(pin->number, OUTPUT);
    digitalWrite(pin->number, pin->state ? HIGH : LOW);
  }
  sendGpioState(pinId, pin->state);
}

void handleMessage(JsonDocument& doc) {
  const char* type = doc["type"];
  JsonObject payload = doc["payload"];
  if (!type) return;

  if (strcmp(type, "EVENT") == 0) {
    const char* eventName = payload["event"];
    if (eventName && strcmp(eventName, "GPIO_WRITE") == 0) {
      const char* pin = payload["pin"];
      int value = payload["value"] | 0;
      if (pin) applyGpioWrite(pin, value);
    }
    return;
  }

  if (strcmp(type, "WRITE") == 0) {
    const char* pin = payload["pin"];
    int value = payload["value"] | 0;
    if (pin) applyGpioWrite(pin, value);
    return;
  }

  if (strcmp(type, "HELLO") == 0 || strcmp(type, "HELLO_ACK") == 0) {
    sendDeviceDiscovery();
  }
}

void setup() {
  Serial.begin(SERIAL_BAUD);
  pinMode(LED_PIN, OUTPUT);
  pinMode(BUTTON_PIN, INPUT_PULLUP);
  generateDeviceId();
  delay(300);
  sendDeviceDiscovery();
  lastHeartbeatMs = millis();
}

void loop() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n') {
      if (incomingLine.length() > 0) {
        StaticJsonDocument<512> doc;
        DeserializationError err = deserializeJson(doc, incomingLine);
        if (!err) handleMessage(doc);
        incomingLine = "";
      }
    } else {
      incomingLine += c;
    }
  }

  if (millis() - lastHeartbeatMs >= HEARTBEAT_INTERVAL_MS) {
    sendHeartbeat();
    lastHeartbeatMs = millis();
  }
}
```
