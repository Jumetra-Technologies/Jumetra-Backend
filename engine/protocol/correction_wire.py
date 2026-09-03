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
