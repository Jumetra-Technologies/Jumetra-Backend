"""ClockOffsetEstimate model."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Optional


@dataclass
class ClockOffsetEstimate:
    """Single-sample (or aggregated) Cristian-style offset estimate.

    Convention (matches ClockObservation):
        estimated_offset = remote_device_clock - (host_time + RTT/2)

    Positive values mean the device clock is ahead of the host midpoint.
    This estimate is **not** applied to any clock in Sprint 11.
    """

    device_id: str
    estimated_offset: float
    host_time: int
    device_time: int
    round_trip_time: int
    algorithm: str = "cristian"
    request_id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ClockOffsetEstimate":
        return cls(
            device_id=str(data["device_id"]),
            estimated_offset=float(data["estimated_offset"]),
            host_time=int(data["host_time"]),
            device_time=int(data["device_time"]),
            round_trip_time=int(data["round_trip_time"]),
            algorithm=str(data.get("algorithm", "cristian")),
            request_id=data.get("request_id"),
        )
