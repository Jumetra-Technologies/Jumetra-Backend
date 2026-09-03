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
