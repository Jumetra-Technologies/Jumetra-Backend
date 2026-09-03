"""SynchronizationReport — validation report export (measurement only)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Optional, Union

from .quality import SyncQuality

PathLike = Union[str, Path]


@dataclass
class SynchronizationReport:
    """Summary report for a sync measurement validation run."""

    sample_count: int
    average_rtt: Optional[float]
    minimum_rtt: Optional[float]
    maximum_rtt: Optional[float]
    jitter: Optional[float]
    confidence_score: float
    device_id: str = ""
    scenario_name: Optional[str] = None
    offset_variance: Optional[float] = None
    experiment_id: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)

    def export_json(self, path: PathLike) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8") as fh:
            fh.write(self.to_json())
            fh.write("\n")
        return target

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SynchronizationReport":
        meta = data.get("metadata")
        return cls(
            sample_count=int(data.get("sample_count", 0)),
            average_rtt=(
                float(data["average_rtt"]) if data.get("average_rtt") is not None else None
            ),
            minimum_rtt=(
                float(data["minimum_rtt"])
                if data.get("minimum_rtt") is not None
                else (
                    float(data["min_rtt"]) if data.get("min_rtt") is not None else None
                )
            ),
            maximum_rtt=(
                float(data["maximum_rtt"])
                if data.get("maximum_rtt") is not None
                else (
                    float(data["max_rtt"]) if data.get("max_rtt") is not None else None
                )
            ),
            jitter=float(data["jitter"]) if data.get("jitter") is not None else None,
            confidence_score=float(data.get("confidence_score", 0.0)),
            device_id=str(data.get("device_id", "")),
            scenario_name=data.get("scenario_name"),
            offset_variance=(
                float(data["offset_variance"])
                if data.get("offset_variance") is not None
                else None
            ),
            experiment_id=data.get("experiment_id"),
            metadata=dict(meta) if isinstance(meta, Mapping) else None,
        )

    @classmethod
    def from_quality(
        cls,
        quality: SyncQuality,
        *,
        scenario_name: Optional[str] = None,
        experiment_id: Optional[str] = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> "SynchronizationReport":
        return cls(
            sample_count=quality.sample_count,
            average_rtt=quality.average_rtt,
            minimum_rtt=quality.min_rtt,
            maximum_rtt=quality.max_rtt,
            jitter=quality.jitter,
            confidence_score=quality.confidence_score,
            device_id=quality.device_id,
            scenario_name=scenario_name,
            offset_variance=quality.offset_variance,
            experiment_id=experiment_id,
            metadata=dict(metadata) if metadata else None,
        )
