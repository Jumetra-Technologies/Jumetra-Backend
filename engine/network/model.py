"""Virtual network condition model for measurement realism (no correction)."""

from __future__ import annotations

import random
from dataclasses import asdict, dataclass
from typing import Any, Callable, Mapping, Optional, Protocol


class _ClockLike(Protocol):
    def advance(self, delta_ms: int) -> None: ...


@dataclass
class NetworkConditionModel:
    """Optional impairments applied to virtual / simulator communication.

    Fields:
        latency_ms: Base one-way (or echo-leg) delay in milliseconds.
        jitter_ms: Uniform jitter amplitude added to latency (±).
        packet_loss: Probability in [0, 1] that a message is dropped.
    """

    latency_ms: float = 0.0
    jitter_ms: float = 0.0
    packet_loss: float = 0.0
    seed: Optional[int] = None

    def __post_init__(self) -> None:
        if not 0.0 <= self.packet_loss <= 1.0:
            raise ValueError("packet_loss must be in [0, 1]")
        if self.latency_ms < 0 or self.jitter_ms < 0:
            raise ValueError("latency_ms and jitter_ms must be non-negative")
        self._rng = random.Random(self.seed)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "NetworkConditionModel":
        return cls(
            latency_ms=float(data.get("latency_ms", 0.0)),
            jitter_ms=float(data.get("jitter_ms", 0.0)),
            packet_loss=float(data.get("packet_loss", 0.0)),
            seed=data.get("seed"),
        )

    def should_drop(self) -> bool:
        """Return True if this message should be lost."""
        if self.packet_loss <= 0.0:
            return False
        return self._rng.random() < self.packet_loss

    def sample_delay_ms(self) -> int:
        """Sample a non-negative delay from latency ± jitter."""
        if self.jitter_ms <= 0:
            delay = self.latency_ms
        else:
            delay = self.latency_ms + self._rng.uniform(-self.jitter_ms, self.jitter_ms)
        return max(0, int(round(delay)))

    def apply_delay(self, clock: Optional[_ClockLike] = None) -> int:
        """Apply sampled delay via SimulationClock.advance when available.

        Returns the delay applied (ms). Does not sleep on real wall clocks —
        scenarios should use SimulationClock for deterministic tests.
        """
        delay = self.sample_delay_ms()
        if delay > 0 and clock is not None and hasattr(clock, "advance"):
            clock.advance(delay)
        return delay


@dataclass
class ConditionedTransport:
    """Wraps a transport ``send`` callable with network impairments.

    Used optionally for virtual/simulator adapters. Dropped messages are
    silently discarded (measurement realism only).
    """

    send_fn: Callable[[dict], None]
    model: NetworkConditionModel
    clock: Optional[_ClockLike] = None

    def send(self, message: dict) -> None:
        if self.model.should_drop():
            return
        self.model.apply_delay(self.clock)
        self.send_fn(message)
