"""SimulatorDevice — placeholder for Wokwi / Proteus / future sim engines."""

from __future__ import annotations

from typing import Any, Mapping, Optional, TYPE_CHECKING

from .device import Device, DeviceMode, DeviceStatus

if TYPE_CHECKING:
    from ...events.event import Event


class SimulatorDevice(Device):
    """A device backed by an external or in-process simulator.

    Phase Sprint 6 only establishes the abstraction. Wokwi / Proteus
    adapters plug in later without changing DeviceManager or EventBus.
    """

    def __init__(
        self,
        device_id: str,
        *,
        device_type: str = "SIMULATOR",
        device_name: Optional[str] = None,
        manufacturer: Optional[str] = None,
        model: Optional[str] = None,
        firmware_version: Optional[str] = None,
        simulator_backend: str = "generic",
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> None:
        meta = dict(metadata) if metadata else {}
        meta.setdefault("simulator_backend", simulator_backend)
        super().__init__(
            device_id=device_id,
            device_type=device_type,
            device_mode=DeviceMode.SIMULATED,
            device_name=device_name or device_id,
            manufacturer=manufacturer or "HHIP",
            model=model or simulator_backend,
            firmware_version=firmware_version,
            metadata=meta,
        )
        self.simulator_backend = simulator_backend
        self._last_event_type: Optional[str] = None

    def _on_initialize(self) -> None:
        self.metadata["backend_ready"] = True

    def _on_shutdown(self) -> None:
        self.metadata["backend_ready"] = False

    def connect_backend(self) -> None:
        """Mark simulator backend connected (no real I/O in this phase)."""
        self.metadata["backend_ready"] = True
        self.set_status(DeviceStatus.READY)
        self._initialized = True

    def disconnect_backend(self) -> None:
        """Mark simulator backend disconnected."""
        self.metadata["backend_ready"] = False
        self.set_status(DeviceStatus.OFFLINE)
        self._initialized = False

    def handle_event(self, event: "Event") -> None:
        if event.target and event.target != self.device_id:
            return
        self._last_event_type = event.event_type
        from .device import _now_ms

        self.updated_at = _now_ms()
        # Future Wokwi adapter will forward payload to the simulator here.

    def serialize(self) -> dict[str, Any]:
        data = super().serialize()
        data["simulator_backend"] = self.simulator_backend
        return data
