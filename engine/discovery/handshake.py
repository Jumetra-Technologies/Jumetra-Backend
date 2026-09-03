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
