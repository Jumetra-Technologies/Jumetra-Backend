"""Virtual device adapter — bridges hybrid commands to simulation runtime."""

from __future__ import annotations

from typing import Any, Optional, TYPE_CHECKING

from ..modes import HybridDeviceMode
from .base import DeviceAdapter

if TYPE_CHECKING:
    from engine.simulation.runtime.engine import SimulationEngine


class HybridVirtualAdapter(DeviceAdapter):
    """Routes commands to SimulationEngine behaviors and reads virtual state."""

    name = "virtual"

    def __init__(self, engine: Optional["SimulationEngine"] = None) -> None:
        self._engine = engine
        self._connected = False

    def bind_engine(self, engine: "SimulationEngine") -> None:
        self._engine = engine

    @property
    def mode(self) -> HybridDeviceMode:
        return HybridDeviceMode.VIRTUAL

    @property
    def is_connected(self) -> bool:
        return self._connected and self._engine is not None

    def connect(self) -> None:
        if self._engine is None:
            raise RuntimeError("virtual adapter requires a SimulationEngine")
        self._connected = True

    def disconnect(self) -> None:
        self._connected = False

    def is_available(self) -> bool:
        return self._engine is not None

    def send(self, command: dict[str, Any]) -> None:
        if not self.is_connected or self._engine is None:
            raise RuntimeError("virtual adapter not connected")
        action = str(command.get("action", ""))
        instance_id = str(command.get("instance_id", ""))
        value = command.get("value")
        if action and instance_id:
            self._engine.send_actuator_command(instance_id, action, value)

    def receive(self) -> Optional[dict[str, Any]]:
        if self._engine is None:
            return None
        return {"state": self._engine.get_state()}

    def advance(self, delta_ms: int = 100) -> dict[str, Any]:
        if self._engine is None:
            raise RuntimeError("virtual adapter not bound")
        return self._engine.advance_time(delta_ms)
