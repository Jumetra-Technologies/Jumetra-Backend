"""Clock observation model — measurement only, no clock correction."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Optional


@dataclass
class ClockObservation:
    """One RTT / offset sample between HHIP and a device clock.

    All fields are observations. ``estimated_offset`` is recorded but
    **never applied** to any Clock in this sprint.
    """

    device_id: str
    local_timestamp: int
    server_timestamp: int
    round_trip_time: int
    estimated_offset: float
    measurement_time: int
    request_time: Optional[int] = None
    response_time: Optional[int] = None
    request_id: Optional[str] = None
    correlation_id: Optional[str] = None
    experiment_id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ClockObservation":
        """Deserialize from :meth:`to_dict` output."""
        return cls(
            device_id=str(data["device_id"]),
            local_timestamp=int(data["local_timestamp"]),
            server_timestamp=int(data["server_timestamp"]),
            round_trip_time=int(data["round_trip_time"]),
            estimated_offset=float(data["estimated_offset"]),
            measurement_time=int(data["measurement_time"]),
            request_time=int(data["request_time"]) if data.get("request_time") is not None else None,
            response_time=(
                int(data["response_time"]) if data.get("response_time") is not None else None
            ),
            request_id=data.get("request_id"),
            correlation_id=data.get("correlation_id"),
            experiment_id=data.get("experiment_id"),
        )
