"""ClockDriftEstimator — drift rate from SynchronizationResult time series."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Optional, Sequence

from .result import SynchronizationResult


@dataclass
class DriftEstimate:
    """Drift analysis output (measurement only)."""

    device_id: str
    drift_rate: float  # offset change per millisecond of host time
    initial_offset: float
    final_offset: float
    sample_count: int
    confidence: float
    duration_ms: int = 0
    intercept: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "DriftEstimate":
        return cls(
            device_id=str(data["device_id"]),
            drift_rate=float(data.get("drift_rate", 0.0)),
            initial_offset=float(data.get("initial_offset", 0.0)),
            final_offset=float(data.get("final_offset", 0.0)),
            sample_count=int(data.get("sample_count", 0)),
            confidence=float(data.get("confidence", 0.0)),
            duration_ms=int(data.get("duration_ms", 0)),
            intercept=float(data.get("intercept", 0.0)),
        )


class ClockDriftEstimator:
    """Estimate clock drift from multiple SynchronizationResult samples.

    Uses ordinary least-squares linear regression::

        offset(t) ≈ intercept + drift_rate * t

    where ``t`` is the result ``timestamp`` (host ms). Positive drift_rate
    means the remote clock is drifting ahead relative to the host.
    """

    def estimate(
        self,
        results: Sequence[SynchronizationResult],
        *,
        device_id: Optional[str] = None,
    ) -> DriftEstimate:
        """Compute drift rate from a sequence of sync results."""
        samples = list(results)
        if device_id is not None:
            samples = [r for r in samples if r.device_id == device_id]

        if not samples:
            did = device_id or ""
            return DriftEstimate(
                device_id=did,
                drift_rate=0.0,
                initial_offset=0.0,
                final_offset=0.0,
                sample_count=0,
                confidence=0.0,
                duration_ms=0,
            )

        ordered = sorted(samples, key=lambda r: r.timestamp)
        device_id = ordered[0].device_id
        initial_offset = float(ordered[0].estimated_offset)
        final_offset = float(ordered[-1].estimated_offset)
        duration_ms = max(0, ordered[-1].timestamp - ordered[0].timestamp)

        if len(ordered) < 2 or duration_ms == 0:
            conf = float(ordered[0].confidence) if ordered else 0.0
            return DriftEstimate(
                device_id=device_id,
                drift_rate=0.0,
                initial_offset=initial_offset,
                final_offset=final_offset,
                sample_count=len(ordered),
                confidence=conf,
                duration_ms=duration_ms,
                intercept=initial_offset,
            )

        drift_rate, intercept, confidence = self._linear_regression(ordered)
        return DriftEstimate(
            device_id=device_id,
            drift_rate=drift_rate,
            initial_offset=initial_offset,
            final_offset=final_offset,
            sample_count=len(ordered),
            confidence=confidence,
            duration_ms=duration_ms,
            intercept=intercept,
        )

    def estimate_from_dicts(
        self,
        records: Sequence[Mapping[str, Any]],
        *,
        device_id: Optional[str] = None,
    ) -> DriftEstimate:
        """Estimate drift from serialized result dicts."""
        results = [SynchronizationResult.from_dict(r) for r in records]
        return self.estimate(results, device_id=device_id)

    @staticmethod
    def _linear_regression(
        ordered: Sequence[SynchronizationResult],
    ) -> tuple[float, float, float]:
        """Return (slope, intercept, confidence)."""
        n = len(ordered)
        ts = [float(r.timestamp) for r in ordered]
        offsets = [float(r.estimated_offset) for r in ordered]

        sum_t = sum(ts)
        sum_o = sum(offsets)
        sum_tt = sum(t * t for t in ts)
        sum_to = sum(t * o for t, o in zip(ts, offsets))

        denom = n * sum_tt - sum_t * sum_t
        if denom == 0:
            avg_conf = sum(r.confidence for r in ordered) / n
            return 0.0, offsets[0], avg_conf

        slope = (n * sum_to - sum_t * sum_o) / denom
        intercept = (sum_o - slope * sum_t) / n

        # Residual-based confidence heuristic in [0, 1].
        predicted = [intercept + slope * t for t in ts]
        residuals = [abs(o - p) for o, p in zip(offsets, predicted)]
        mean_res = sum(residuals) / n
        spread = max(abs(offsets[-1] - offsets[0]), 1.0)
        fit_quality = 1.0 / (1.0 + mean_res / spread)
        avg_conf = sum(r.confidence for r in ordered) / n
        confidence = max(0.0, min(1.0, fit_quality * avg_conf))

        return slope, intercept, confidence
