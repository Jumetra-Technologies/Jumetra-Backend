"""ClockDomain — measurement view of a clock (no correction)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Optional


@dataclass
class ClockDomain:
    """Describes one clock domain for sync research.

    ``offset_estimate`` / ``drift_estimate`` are observations only —
    they are never applied to the underlying Clock.
    """

    clock_id: str
    clock_type: str  # e.g. host | device | simulation | virtual
    precision: float = 1.0  # nominal resolution in milliseconds
    offset_estimate: float = 0.0
    drift_estimate: float = 0.0
    last_measurement: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ClockDomain":
        last = data.get("last_measurement")
        return cls(
            clock_id=str(data["clock_id"]),
            clock_type=str(data.get("clock_type", "unknown")),
            precision=float(data.get("precision", 1.0)),
            offset_estimate=float(data.get("offset_estimate", 0.0)),
            drift_estimate=float(data.get("drift_estimate", 0.0)),
            last_measurement=dict(last) if isinstance(last, Mapping) else None,
        )

    def record_observation(self, observation: Any) -> None:
        """Update estimates from a ClockObservation / mapping (measurement only)."""
        if hasattr(observation, "to_dict"):
            record = observation.to_dict()
            offset = float(getattr(observation, "estimated_offset", 0.0))
        else:
            record = dict(observation)
            offset = float(record.get("estimated_offset", 0.0))
        self.offset_estimate = offset
        self.last_measurement = record


@dataclass
class ClockDomainRegistry:
    """Simple registry of clock domains keyed by ``clock_id``."""

    domains: dict[str, ClockDomain] = field(default_factory=dict)

    def register(self, domain: ClockDomain) -> ClockDomain:
        self.domains[domain.clock_id] = domain
        return domain

    def get(self, clock_id: str) -> Optional[ClockDomain]:
        return self.domains.get(clock_id)

    def ensure(
        self,
        clock_id: str,
        *,
        clock_type: str = "device",
        precision: float = 1.0,
    ) -> ClockDomain:
        existing = self.domains.get(clock_id)
        if existing is not None:
            return existing
        return self.register(
            ClockDomain(clock_id=clock_id, clock_type=clock_type, precision=precision)
        )

    def record_observation(self, clock_id: str, observation: Any, **kwargs: Any) -> ClockDomain:
        domain = self.ensure(clock_id, **kwargs)
        domain.record_observation(observation)
        return domain

    def to_dict(self) -> dict[str, Any]:
        return {cid: d.to_dict() for cid, d in self.domains.items()}
