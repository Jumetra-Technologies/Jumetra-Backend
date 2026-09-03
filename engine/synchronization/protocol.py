"""Serializable SYNC_REQUEST / SYNC_RESPONSE protocol messages.

Sprint 9 measurement protocol — no clock correction fields.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Optional


def _new_correlation_id() -> str:
    return str(uuid.uuid4())


def _new_request_id() -> str:
    return f"sync_{uuid.uuid4().hex[:10]}"


@dataclass
class SyncRequest:
    """Host → device synchronization probe.

    Fields:
        sequence_number: Monotonic probe index for this device session.
        device_id: Target device id.
        server_timestamp: HHIP/host time when the request was created (ms).
        device_timestamp: Unused on request (0); filled by the device on response.
        correlation_id: Links request and response.
    """

    sequence_number: int
    device_id: str
    server_timestamp: int
    device_timestamp: int = 0
    correlation_id: str = field(default_factory=_new_correlation_id)
    request_id: str = field(default_factory=_new_request_id)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), separators=(",", ":"))

    def to_event_payload(self) -> dict[str, Any]:
        """Payload shape embedded in an EventBus SYNC_REQUEST Event."""
        return {
            "request_id": self.request_id,
            "request_time": self.server_timestamp,
            "sequence_number": self.sequence_number,
            "device_id": self.device_id,
            "server_timestamp": self.server_timestamp,
            "device_timestamp": self.device_timestamp,
            "correlation_id": self.correlation_id,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SyncRequest":
        return cls(
            sequence_number=int(data.get("sequence_number", 0)),
            device_id=str(data["device_id"]),
            server_timestamp=int(
                data.get("server_timestamp", data.get("request_time", 0))
            ),
            device_timestamp=int(data.get("device_timestamp", 0)),
            correlation_id=str(data.get("correlation_id") or _new_correlation_id()),
            request_id=str(data.get("request_id") or _new_request_id()),
        )

    @classmethod
    def from_json(cls, raw: str) -> "SyncRequest":
        return cls.from_dict(json.loads(raw))


@dataclass
class SyncResponse:
    """Device → host synchronization reply.

    Fields:
        sequence_number: Echoed from the request when available.
        device_id: Responding device id.
        server_timestamp: Echoed host time from the request (for RTT pairing).
        device_timestamp: Device clock reading (e.g. ESP32 millis()).
        correlation_id: Echoed from the request.
    """

    sequence_number: int
    device_id: str
    server_timestamp: int
    device_timestamp: int
    correlation_id: str
    request_id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), separators=(",", ":"))

    def to_event_payload(self) -> dict[str, Any]:
        """Payload shape embedded in an EventBus SYNC_RESPONSE Event."""
        return {
            "request_id": self.request_id,
            "request_time": self.server_timestamp,
            "sequence_number": self.sequence_number,
            "device_id": self.device_id,
            "server_timestamp": self.server_timestamp,
            "device_timestamp": self.device_timestamp,
            # Prefer device_timestamp as the remote clock sample for offset math.
            "server_timestamp_host": self.server_timestamp,
            "correlation_id": self.correlation_id,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SyncResponse":
        device_ts = data.get("device_timestamp")
        if device_ts is None:
            # Sprint 8 compat: older echoes used server_timestamp for device time.
            device_ts = data.get("server_timestamp", 0)
        host_ts = data.get("server_timestamp")
        if data.get("request_time") is not None and data.get("device_timestamp") is not None:
            host_ts = data.get("request_time")
        elif data.get("server_timestamp_host") is not None:
            host_ts = data.get("server_timestamp_host")
        return cls(
            sequence_number=int(data.get("sequence_number", 0)),
            device_id=str(data.get("device_id") or data.get("source") or ""),
            server_timestamp=int(host_ts if host_ts is not None else 0),
            device_timestamp=int(device_ts),
            correlation_id=str(data.get("correlation_id") or _new_correlation_id()),
            request_id=data.get("request_id"),
        )

    @classmethod
    def from_json(cls, raw: str) -> "SyncResponse":
        return cls.from_dict(json.loads(raw))
