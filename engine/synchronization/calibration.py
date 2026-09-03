"""ClockCalibrationReport — drift calibration summary export."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence, Union

from .drift import ClockDriftEstimator, DriftEstimate
from .result import SynchronizationResult

PathLike = Union[str, Path]


@dataclass
class ClockCalibrationReport:
    """Calibration report derived from a time series of sync results."""

    device_id: str
    initial_offset: float
    final_offset: float
    drift_rate: float
    sample_count: int
    confidence: float
    duration_ms: Optional[int] = None
    experiment_id: Optional[str] = None
    uncertainty: Optional[float] = None
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
    def from_dict(cls, data: Mapping[str, Any]) -> "ClockCalibrationReport":
        meta = data.get("metadata")
        return cls(
            device_id=str(data["device_id"]),
            initial_offset=float(data.get("initial_offset", 0.0)),
            final_offset=float(data.get("final_offset", 0.0)),
            drift_rate=float(data.get("drift_rate", 0.0)),
            sample_count=int(data.get("sample_count", 0)),
            confidence=float(data.get("confidence", 0.0)),
            duration_ms=(
                int(data["duration_ms"]) if data.get("duration_ms") is not None else None
            ),
            experiment_id=data.get("experiment_id"),
            uncertainty=(
                float(data["uncertainty"])
                if data.get("uncertainty") is not None
                else None
            ),
            metadata=dict(meta) if isinstance(meta, Mapping) else None,
        )

    @classmethod
    def from_drift(
        cls,
        drift: DriftEstimate,
        *,
        experiment_id: Optional[str] = None,
        uncertainty: Optional[float] = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> "ClockCalibrationReport":
        return cls(
            device_id=drift.device_id,
            initial_offset=drift.initial_offset,
            final_offset=drift.final_offset,
            drift_rate=drift.drift_rate,
            sample_count=drift.sample_count,
            confidence=drift.confidence,
            duration_ms=drift.duration_ms,
            experiment_id=experiment_id,
            uncertainty=uncertainty,
            metadata=dict(metadata) if metadata else None,
        )

    @classmethod
    def from_results(
        cls,
        results: Sequence[SynchronizationResult],
        *,
        device_id: Optional[str] = None,
        experiment_id: Optional[str] = None,
        uncertainty: Optional[float] = None,
        metadata: Optional[Mapping[str, Any]] = None,
        estimator: Optional[ClockDriftEstimator] = None,
    ) -> "ClockCalibrationReport":
        est = estimator or ClockDriftEstimator()
        drift = est.estimate(results, device_id=device_id)
        return cls.from_drift(
            drift,
            experiment_id=experiment_id,
            uncertainty=uncertainty,
            metadata=metadata,
        )
