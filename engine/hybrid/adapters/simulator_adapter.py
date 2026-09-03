"""Simulator device adapter — wraps external simulator backends."""

from __future__ import annotations

from typing import Any, Optional

from engine.simulation.adapters import InProcessSimulatorAdapter, SimulatorAdapter

from ..modes import HybridDeviceMode
from .base import DeviceAdapter


class HybridSimulatorAdapter(DeviceAdapter):
    """Wraps a SimulatorAdapter (Wokwi, Proteus, in-process) for hybrid experiments."""

    name = "simulator"

    def __init__(self, backend: SimulatorAdapter) -> None:
        self._backend = backend

    @property
    def backend(self) -> SimulatorAdapter:
        return self._backend

    @property
    def mode(self) -> HybridDeviceMode:
        return HybridDeviceMode.SIMULATED

    @property
    def is_connected(self) -> bool:
        return getattr(self._backend, "_connected", False) or isinstance(
            self._backend, InProcessSimulatorAdapter
        )

    def connect(self) -> None:
        self._backend.connect()

    def disconnect(self) -> None:
        self._backend.disconnect()

    def is_available(self) -> bool:
        return self.is_connected

    def send(self, command: dict[str, Any]) -> None:
        pin = str(command.get("pin", ""))
        value = command.get("value", 0)
        if pin:
            self._backend.write_pin(pin, value)

    def receive(self) -> Optional[dict[str, Any]]:
        return {"backend": self._backend.name}

    def load_circuit(self, circuit: dict[str, Any]) -> None:
        self._backend.load_circuit(circuit)

    def step(self, delta_ms: int = 1) -> dict[str, Any]:
        return self._backend.step(delta_ms)

    def read_pin(self, pin: str) -> Any:
        return self._backend.read_pin(pin)

    def write_pin(self, pin: str, value: Any) -> None:
        self._backend.write_pin(pin, value)
