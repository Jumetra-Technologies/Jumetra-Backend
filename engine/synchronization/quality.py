"""SyncQuality — measurement quality summary for a device (no correction)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Optional, Sequence


@dataclass
class SyncQuality:
    """Quality metrics derived from a window of RTT / offset samples."""

    device_id: str
    sample_count: int
    average_rtt: Optional[float]
    jitter: Optional[float]
    offset_variance: Optional[float]
    confidence_score: float
    min_rtt: Optional[float] = None
    max_rtt: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SyncQuality":
        return cls(
            device_id=str(data["device_id"]),
            sample_count=int(data.get("sample_count", 0)),
            average_rtt=(
                float(data["average_rtt"]) if data.get("average_rtt") is not None else None
            ),
            jitter=float(data["jitter"]) if data.get("jitter") is not None else None,
            offset_variance=(
                float(data["offset_variance"])
                if data.get("offset_variance") is not None
                else None
            ),
            confidence_score=float(data.get("confidence_score", 0.0)),
            min_rtt=float(data["min_rtt"]) if data.get("min_rtt") is not None else None,
            max_rtt=float(data["max_rtt"]) if data.get("max_rtt") is not None else None,
        )

    @classmethod
    def from_samples(
        cls,
        device_id: str,
        rtts: Sequence[float],
        offsets: Sequence[float],
        *,
        target_samples: int = 100,
    ) -> "SyncQuality":
        """Compute quality stats from RTT and offset sample sequences."""
        sample_count = len(rtts)
        if sample_count == 0:
            return cls(
                device_id=device_id,
                sample_count=0,
                average_rtt=None,
                jitter=None,
                offset_variance=None,
                confidence_score=0.0,
            )

        avg_rtt = sum(rtts) / sample_count
        min_rtt = float(min(rtts))
        max_rtt = float(max(rtts))

        if sample_count >= 2:
            diffs = [abs(rtts[i] - rtts[i - 1]) for i in range(1, sample_count)]
            jitter = sum(diffs) / len(diffs)
        else:
            jitter = 0.0

        if offsets:
            mean_off = sum(offsets) / len(offsets)
            offset_variance = sum((o - mean_off) ** 2 for o in offsets) / len(offsets)
        else:
            offset_variance = 0.0

        # Heuristic confidence in [0, 1]: more samples, lower relative jitter,
        # lower offset variance → higher confidence. Measurement only.
        sample_factor = min(1.0, sample_count / float(max(target_samples, 1)))
        rel_jitter = (jitter / avg_rtt) if avg_rtt > 0 else jitter
        jitter_factor = 1.0 / (1.0 + rel_jitter)
        variance_factor = 1.0 / (1.0 + (offset_variance ** 0.5) / 1000.0)
        confidence = max(0.0, min(1.0, sample_factor * jitter_factor * variance_factor))

        return cls(
            device_id=device_id,
            sample_count=sample_count,
            average_rtt=float(avg_rtt),
            jitter=float(jitter),
            offset_variance=float(offset_variance),
            confidence_score=float(confidence),
            min_rtt=min_rtt,
            max_rtt=max_rtt,
        )
