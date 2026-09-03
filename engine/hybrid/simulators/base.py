"""External simulator adapter framework for hybrid bridge."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from engine.simulation.adapters import SimulatorAdapter as BaseSimulatorAdapter


class HybridSimulatorBackend(ABC):
    """Abstract external simulator backend (Wokwi, Proteus, etc.)."""

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    def connect(self) -> None:
        pass

    @abstractmethod
    def disconnect(self) -> None:
        pass

    @abstractmethod
    def load_circuit(self, circuit: dict[str, Any]) -> None:
        pass

    @abstractmethod
    def step(self, delta_ms: int = 1) -> dict[str, Any]:
        pass

    @abstractmethod
    def read_pin(self, pin: str) -> Any:
        pass

    @abstractmethod
    def write_pin(self, pin: str, value: Any) -> None:
        pass


class WokwiAdapter(HybridSimulatorBackend):
    """Wokwi simulator stub — API integration planned for a future sprint."""

    name = "wokwi"

    def __init__(self) -> None:
        self._connected = False
        self._circuit: dict[str, Any] = {}
        self._pins: dict[str, Any] = {}

    def connect(self) -> None:
        self._connected = True

    def disconnect(self) -> None:
        self._connected = False

    def load_circuit(self, circuit: dict[str, Any]) -> None:
        if not self._connected:
            raise RuntimeError("wokwi adapter not connected")
        self._circuit = dict(circuit)

    def step(self, delta_ms: int = 1) -> dict[str, Any]:
        return {"backend": self.name, "delta_ms": delta_ms, "stub": True}

    def read_pin(self, pin: str) -> Any:
        return self._pins.get(pin, 0)

    def write_pin(self, pin: str, value: Any) -> None:
        self._pins[pin] = value


class ProteusAdapter(HybridSimulatorBackend):
    """Proteus simulator stub — VSM integration planned for a future sprint."""

    name = "proteus"

    def __init__(self) -> None:
        self._connected = False
        self._circuit: dict[str, Any] = {}

    def connect(self) -> None:
        self._connected = True

    def disconnect(self) -> None:
        self._connected = False

    def load_circuit(self, circuit: dict[str, Any]) -> None:
        if not self._connected:
            raise RuntimeError("proteus adapter not connected")
        self._circuit = dict(circuit)

    def step(self, delta_ms: int = 1) -> dict[str, Any]:
        return {"backend": self.name, "delta_ms": delta_ms, "stub": True}

    def read_pin(self, pin: str) -> Any:
        return 0

    def write_pin(self, pin: str, value: Any) -> None:
        return None


def wrap_backend(backend: HybridSimulatorBackend) -> BaseSimulatorAdapter:
    """Adapt HybridSimulatorBackend to engine.simulation.adapters.SimulatorAdapter."""

    class _Wrapper(BaseSimulatorAdapter):
        @property
        def name(self) -> str:
            return backend.name

        def connect(self) -> None:
            backend.connect()

        def disconnect(self) -> None:
            backend.disconnect()

        def load_circuit(self, circuit: dict[str, Any]) -> None:
            backend.load_circuit(circuit)

        def step(self, delta_ms: int = 1) -> dict[str, Any]:
            return backend.step(delta_ms)

        def read_pin(self, pin: str) -> Any:
            return backend.read_pin(pin)

        def write_pin(self, pin: str, value: Any) -> None:
            backend.write_pin(pin, value)

    return _Wrapper()
