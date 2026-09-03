"""CorrectionTransaction model."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Optional

from .state import TransactionState


@dataclass
class CorrectionTransaction:
    """One physical correction attempt with verification metadata."""

    transaction_id: str
    device_id: str
    correction_step: float
    timestamp: int
    state: TransactionState = TransactionState.CREATED
    offset_before: Optional[float] = None
    offset_after: Optional[float] = None
    accumulated_correction: float = 0.0
    verified: bool = False
    improvement: float = 0.0
    failure_reason: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["state"] = self.state.value
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CorrectionTransaction":
        meta = data.get("metadata") or {}
        return cls(
            transaction_id=str(data["transaction_id"]),
            device_id=str(data["device_id"]),
            correction_step=float(data["correction_step"]),
            timestamp=int(data["timestamp"]),
            state=TransactionState(str(data.get("state", TransactionState.CREATED.value))),
            offset_before=(
                float(data["offset_before"])
                if data.get("offset_before") is not None
                else None
            ),
            offset_after=(
                float(data["offset_after"])
                if data.get("offset_after") is not None
                else None
            ),
            accumulated_correction=float(data.get("accumulated_correction", 0.0)),
            verified=bool(data.get("verified", False)),
            improvement=float(data.get("improvement", 0.0)),
            failure_reason=data.get("failure_reason"),
            metadata=dict(meta) if isinstance(meta, Mapping) else {},
        )
