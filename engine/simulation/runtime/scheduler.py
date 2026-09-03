"""Simulation scheduler — periodic behavior ticks."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


TickCallback = Callable[[int, int], None]


@dataclass
class ScheduledTask:
    name: str
    interval_ms: int
    callback: TickCallback
    elapsed_ms: int = 0


class SimulationScheduler:
    """Schedule periodic simulation tasks against simulated time."""

    def __init__(self) -> None:
        self._tasks: list[ScheduledTask] = []

    def schedule(self, name: str, interval_ms: int, callback: TickCallback) -> None:
        self._tasks.append(ScheduledTask(name=name, interval_ms=max(1, interval_ms), callback=callback))

    def tick(self, delta_ms: int, sim_time_ms: int) -> list[str]:
        fired: list[str] = []
        for task in self._tasks:
            task.elapsed_ms += delta_ms
            while task.elapsed_ms >= task.interval_ms:
                task.callback(task.interval_ms, sim_time_ms)
                task.elapsed_ms -= task.interval_ms
                fired.append(task.name)
        return fired

    def clear(self) -> None:
        self._tasks.clear()
