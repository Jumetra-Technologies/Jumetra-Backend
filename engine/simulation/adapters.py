"""Simulator adapter interfaces — pluggable simulation backends."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class SimulatorAdapter(ABC):
    """Abstract adapter for external simulators (Wokwi, Proteus, etc.)."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable adapter name."""

    @abstractmethod
    def connect(self) -> None:
        """Establish connection to the simulation backend."""

    @abstractmethod
    def disconnect(self) -> None:
        """Release simulation backend resources."""

    @abstractmethod
    def load_circuit(self, circuit: dict[str, Any]) -> None:
        """Load a circuit definition into the simulator."""

    @abstractmethod
    def step(self, delta_ms: int = 1) -> dict[str, Any]:
        """Advance simulation by ``delta_ms`` milliseconds."""

    @abstractmethod
    def read_pin(self, pin: str) -> Any:
        """Read simulated pin state."""

    @abstractmethod
    def write_pin(self, pin: str, value: Any) -> None:
        """Write simulated pin state."""


class InProcessSimulatorAdapter(SimulatorAdapter):
    """In-process stub simulator for virtual laboratory foundation."""

    name = "in-process"

    def __init__(self) -> None:
        self._connected = False
        self._circuit: dict[str, Any] = {}
        self._pin_state: dict[str, Any] = {}
        self._tick = 0

    def connect(self) -> None:
        self._connected = True

    def disconnect(self) -> None:
        self._connected = False
        self._pin_state.clear()

    def load_circuit(self, circuit: dict[str, Any]) -> None:
        if not self._connected:
            raise RuntimeError("simulator not connected")
        self._circuit = dict(circuit)
        for node in circuit.get("nodes", []):
            pin_id = node.get("id")
            if pin_id:
                self._pin_state[str(pin_id)] = node.get("default_value", 0)

    def step(self, delta_ms: int = 1) -> dict[str, Any]:
        if not self._connected:
            raise RuntimeError("simulator not connected")
        self._tick += delta_ms
        return {"tick_ms": self._tick, "pin_count": len(self._pin_state)}

    def read_pin(self, pin: str) -> Any:
        return self._pin_state.get(pin, 0)

    def write_pin(self, pin: str, value: Any) -> None:
        self._pin_state[pin] = value
