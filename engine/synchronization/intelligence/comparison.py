"""Compare fixed vs adaptive synchronization strategies in experiments."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Callable, Optional

from ..strategy import FixedIntervalStrategy
from .decision_engine import SynchronizationDecisionEngine
from .interval_strategy import AdaptiveIntervalStrategy


@dataclass
class StrategyComparisonResult:
    """Metrics from one strategy run."""

    strategy_name: str
    sync_event_count: int
    correction_count: int
    correction_accuracy: float
    communication_cost: int
    average_interval_ms: float
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class StrategyComparisonReport:
    """Side-by-side fixed vs adaptive comparison."""

    fixed: StrategyComparisonResult
    adaptive: StrategyComparisonResult

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixed": self.fixed.to_dict(),
            "adaptive": self.adaptive.to_dict(),
            "delta_sync_events": self.adaptive.sync_event_count - self.fixed.sync_event_count,
            "delta_communication_cost": (
                self.adaptive.communication_cost - self.fixed.communication_cost
            ),
            "accuracy_improvement": (
                self.adaptive.correction_accuracy - self.fixed.correction_accuracy
            ),
        }


MeasureFn = Callable[[], dict[str, Any]]


class SyncStrategyComparison:
    """Run deterministic fixed and adaptive strategy simulations."""

    def __init__(
        self,
        *,
        fixed_interval_ms: int = 5_000,
        decision_engine: Optional[SynchronizationDecisionEngine] = None,
    ) -> None:
        self.fixed_strategy = FixedIntervalStrategy(fixed_interval_ms)
        self.adaptive_strategy = AdaptiveIntervalStrategy()
        self.decision_engine = decision_engine or SynchronizationDecisionEngine(
            interval_strategy=self.adaptive_strategy
        )

    def simulate_fixed(
        self,
        device_id: str,
        measurements: list[dict[str, Any]],
        *,
        correction_fn: Optional[MeasureFn] = None,
    ) -> StrategyComparisonResult:
        return self._simulate(
            "fixed",
            device_id,
            measurements,
            interval_fn=lambda **_: self.fixed_strategy.interval_ms,
            correction_fn=correction_fn,
        )

    def simulate_adaptive(
        self,
        device_id: str,
        measurements: list[dict[str, Any]],
        *,
        health_score: float = 1.0,
        correction_fn: Optional[MeasureFn] = None,
    ) -> StrategyComparisonResult:
        last_interval = self.fixed_strategy.interval_ms

        def interval_fn(**kwargs: Any) -> int:
            nonlocal last_interval
            plan = self.decision_engine.decide(
                device_id,
                offset=float(kwargs.get("offset", 0.0)),
                drift=float(kwargs.get("drift", 0.0)),
                confidence=float(kwargs.get("confidence", 0.0)),
                quality=kwargs.get("quality"),
                health_score=health_score,
                last_interval_ms=last_interval,
                timestamp=int(kwargs.get("timestamp", 0)),
            )
            last_interval = plan.recommended_interval_ms
            return plan.recommended_interval_ms

        return self._simulate(
            "adaptive",
            device_id,
            measurements,
            interval_fn=interval_fn,
            correction_fn=correction_fn,
            use_adaptive_corrections=True,
        )

    def compare(
        self,
        device_id: str,
        measurements: list[dict[str, Any]],
        *,
        health_score: float = 1.0,
    ) -> StrategyComparisonReport:
        fixed = self.simulate_fixed(device_id, measurements)
        adaptive = self.simulate_adaptive(
            device_id, measurements, health_score=health_score
        )
        return StrategyComparisonReport(fixed=fixed, adaptive=adaptive)

    def _simulate(
        self,
        name: str,
        device_id: str,
        measurements: list[dict[str, Any]],
        *,
        interval_fn: Callable[..., int],
        correction_fn: Optional[MeasureFn] = None,
        use_adaptive_corrections: bool = False,
    ) -> StrategyComparisonResult:
        sync_events = 0
        corrections = 0
        correction_hits = 0
        comm_cost = 0
        interval_total = 0

        for m in measurements:
            sync_events += 1
            comm_cost += 1  # SYNC_REQUEST + RESPONSE ≈ 1 round-trip unit

            offset = float(m.get("offset", 0.0))
            drift = float(m.get("drift", 0.0))
            confidence = float(m.get("confidence", 0.5))
            quality = m.get("quality") or {}

            interval = interval_fn(
                offset=offset,
                drift=drift,
                confidence=confidence,
                quality=quality,
                timestamp=int(m.get("timestamp", 0)),
            )
            interval_total += interval

            if abs(offset) > 5.0 and confidence >= 0.5:
                corrections += 1
                comm_cost += 1  # correction wire exchange
                if use_adaptive_corrections:
                    step_rec = self.decision_engine.correction_policy.recommend_step(
                        device_id,
                        offset,
                        confidence=confidence,
                        previous_corrections=corrections - 1,
                        health_score=float(m.get("health_score", 1.0)),
                    )
                    hit = abs(step_rec.step_ms) <= abs(offset)
                else:
                    hit = abs(offset) <= 10.0
                if hit:
                    correction_hits += 1

            if correction_fn is not None:
                correction_fn()

        accuracy = correction_hits / corrections if corrections else 1.0
        avg_interval = interval_total / len(measurements) if measurements else 0.0

        return StrategyComparisonResult(
            strategy_name=name,
            sync_event_count=sync_events,
            correction_count=corrections,
            correction_accuracy=accuracy,
            communication_cost=comm_cost,
            average_interval_ms=avg_interval,
            metadata={"device_id": device_id},
        )
