"""AdaptiveIntervalStrategy — deterministic sync interval tuning."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Optional

from ..strategy_base import SyncIntervalStrategy


@dataclass
class IntervalRecommendation:
    """Adaptive interval decision with explanatory factors."""

    device_id: str
    interval_ms: int
    drift_rate: float
    confidence: float
    rtt_stability: float
    device_health: float
    failure_rate: float
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AdaptiveIntervalConfig:
    """Bounds and weights for interval calculation."""

    base_interval_ms: int = 5_000
    min_interval_ms: int = 1_000
    max_interval_ms: int = 30_000
    drift_sensitivity: float = 500.0
    confidence_threshold: float = 0.7
    health_threshold: float = 0.8
    failure_threshold: float = 0.2

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AdaptiveIntervalStrategy(SyncIntervalStrategy):
    """Deterministic adaptive sync interval from measurement signals.

    Higher drift, lower confidence, unstable RTT, poor health, or elevated
    failure rate → shorter interval. Stable devices sync less often.
    """

    def __init__(self, config: Optional[AdaptiveIntervalConfig] = None) -> None:
        self.config = config or AdaptiveIntervalConfig()

    def recommend(
        self,
        device_id: str,
        *,
        drift_rate: float = 0.0,
        confidence: float = 0.0,
        rtt_stability: float = 1.0,
        device_health: float = 1.0,
        failure_rate: float = 0.0,
        last_interval_ms: int = 0,
    ) -> IntervalRecommendation:
        cfg = self.config
        interval = float(cfg.base_interval_ms)

        drift_penalty = min(1.0, abs(drift_rate) * cfg.drift_sensitivity)
        if drift_penalty > 0.01:
            interval *= max(0.4, 1.0 - drift_penalty)

        if confidence < cfg.confidence_threshold:
            interval *= max(0.5, confidence / cfg.confidence_threshold)

        if rtt_stability < 0.8:
            interval *= max(0.5, rtt_stability)

        if device_health < cfg.health_threshold:
            interval *= max(0.5, device_health)

        if failure_rate > cfg.failure_threshold:
            interval *= max(0.4, 1.0 - failure_rate)

        interval_ms = int(max(cfg.min_interval_ms, min(cfg.max_interval_ms, round(interval))))
        reason = (
            f"drift={drift_rate:.6f} conf={confidence:.2f} "
            f"rtt_stab={rtt_stability:.2f} health={device_health:.2f} "
            f"fail={failure_rate:.2f}"
        )
        return IntervalRecommendation(
            device_id=device_id,
            interval_ms=interval_ms,
            drift_rate=drift_rate,
            confidence=confidence,
            rtt_stability=rtt_stability,
            device_health=device_health,
            failure_rate=failure_rate,
            reason=reason,
        )

    def calculate_next_interval(
        self,
        device_id: str,
        *,
        last_interval_ms: int,
        quality: Optional[Mapping[str, Any]] = None,
        drift: Optional[float] = None,
        confidence: Optional[float] = None,
        rtt_stability: Optional[float] = None,
        device_health: Optional[float] = None,
        failure_rate: Optional[float] = None,
    ) -> int:
        q = quality or {}
        jitter = q.get("jitter")
        avg_rtt = q.get("average_rtt")
        if rtt_stability is None:
            if jitter is not None and avg_rtt and float(avg_rtt) > 0:
                rel = float(jitter) / float(avg_rtt)
                rtt_stability = 1.0 / (1.0 + rel)
            else:
                rtt_stability = 1.0

        rec = self.recommend(
            device_id,
            drift_rate=float(drift or 0.0),
            confidence=float(confidence or q.get("confidence_score", 0.0)),
            rtt_stability=float(rtt_stability),
            device_health=float(device_health if device_health is not None else 1.0),
            failure_rate=float(failure_rate if failure_rate is not None else 0.0),
            last_interval_ms=last_interval_ms,
        )
        return rec.interval_ms

    @staticmethod
    def rtt_stability_from_quality(quality: Mapping[str, Any]) -> float:
        jitter = quality.get("jitter")
        avg_rtt = quality.get("average_rtt")
        if jitter is None or not avg_rtt or float(avg_rtt) <= 0:
            return 1.0
        rel = float(jitter) / float(avg_rtt)
        return 1.0 / (1.0 + rel)
