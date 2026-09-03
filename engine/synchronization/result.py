"""SynchronizationResult — output of SynchronizationEngine (estimation only)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Optional, Sequence


@dataclass
class SynchronizationResult:
    """Result of running an offset estimation algorithm over samples."""

    device_id: str
    estimated_offset: float
    sample_count: int
    selected_samples: int
    confidence: float
    timestamp: int
    algorithm_used: str = "cristian"
    before_offset: Optional[float] = None
    min_rtt_selected: Optional[float] = None
    filter_mode: Optional[str] = None
    selected_offsets: list[float] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SynchronizationResult":
        selected = data.get("selected_offsets") or []
        meta = data.get("metadata") or {}
        return cls(
            device_id=str(data["device_id"]),
            estimated_offset=float(data["estimated_offset"]),
            sample_count=int(data.get("sample_count", 0)),
            selected_samples=int(data.get("selected_samples", 0)),
            confidence=float(data.get("confidence", 0.0)),
            timestamp=int(data["timestamp"]),
            algorithm_used=str(data.get("algorithm_used", "cristian")),
            before_offset=(
                float(data["before_offset"])
                if data.get("before_offset") is not None
                else None
            ),
            min_rtt_selected=(
                float(data["min_rtt_selected"])
                if data.get("min_rtt_selected") is not None
                else None
            ),
            filter_mode=data.get("filter_mode"),
            selected_offsets=[float(x) for x in selected],
            metadata=dict(meta) if isinstance(meta, Mapping) else {},
        )
