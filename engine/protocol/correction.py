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
