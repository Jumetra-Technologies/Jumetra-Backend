"""Simulation clock — wraps HHIP SimulationClock for virtual hardware runtime."""

from __future__ import annotations

from engine.time.clock import SimulationClock as _BaseSimulationClock


class SimulationClock:
    """Deterministic simulated time for virtual hardware runs."""

    def __init__(self, *, start_ms: int = 0) -> None:
        self._clock = _BaseSimulationClock(start_ms=start_ms)

    def now(self) -> int:
        return self._clock.now()

    def advance(self, delta_ms: int) -> int:
        return self._clock.advance(delta_ms)

    def set_time(self, time_ms: int) -> None:
        self._clock.set_time(time_ms)
