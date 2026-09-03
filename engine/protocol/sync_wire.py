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
