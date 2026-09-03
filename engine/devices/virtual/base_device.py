"""Abstract VirtualDevice — software-only Device specialization.

Virtual devices must not import ESP32 / Arduino / transport code.
"""

from __future__ import annotations

from abc import abstractmethod
from typing import Any, Mapping, Optional, TYPE_CHECKING

from ..base.device import Device, DeviceMode, DeviceStatus, _now_ms

if TYPE_CHECKING:
    from ...events.event import Event
    from ...state.state_manager import StateManager

# Re-export so existing `from ...virtual.base_device import DeviceStatus` works.
__all__ = ["DeviceStatus", "VirtualDevice"]


class VirtualDevice(Device):
    """Common shape for every virtual device in HHIP.

    Extends :class:`~engine.devices.base.device.Device` with functional
    state tracking and optional StateManager synchronization.
    """

    def __init__(
        self,
        device_id: str,
        device_type: str,
        *,
        device_name: Optional[str] = None,
        manufacturer: Optional[str] = None,
        model: Optional[str] = None,
        firmware_version: Optional[str] = None,
        state_manager: Optional["StateManager"] = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> None:
        super().__init__(
            device_id=device_id,
            device_type=device_type,
            device_mode=DeviceMode.VIRTUAL,
            device_name=device_name,
            manufacturer=manufacturer,
            model=model,
            firmware_version=firmware_version,
            metadata=metadata,
        )
        self._state: Any = None
        self._state_manager = state_manager

    @property
    def state(self) -> Any:
        return self._state

    @property
    def last_updated(self) -> int:
        """Alias for ``updated_at`` (Phase 1.4 compatibility)."""
        return self.updated_at

    def update_state(self, new_state: Any, *, source: str = "local") -> Any:
        """Set functional state, refresh timestamps, sync StateManager."""
        previous = self._state
        self._state = new_state
        self.updated_at = _now_ms()
        if self._state_manager is not None and previous != new_state:
            self._state_manager.update_state(
                self.device_id,
                new_state,
                source=source,
                previous_state=previous,
                timestamp=self.updated_at,
            )
        return previous

    def get_state(self) -> Any:
        return self._state

    def bind_state_manager(self, state_manager: "StateManager") -> None:
        self._state_manager = state_manager

    def handle_event(self, event: "Event") -> None:
        if event.target and event.target != self.device_id:
            return
        self.receive_event(event.payload if isinstance(event.payload, dict) else {})

    @abstractmethod
    def receive_event(self, payload: dict) -> None:
        """Handle an inbound STATE_UPDATE payload (Phase 1.4 API)."""

    def serialize(self) -> dict[str, Any]:
        data = super().serialize()
        data["state"] = self._state
        return data

    def deserialize(self, data: Mapping[str, Any]) -> None:
        super().deserialize(data)
        if "state" in data:
            self._state = data["state"]

    def health(self) -> dict[str, Any]:
        snapshot = super().health()
        snapshot["state"] = self._state
        return snapshot

    def report_state(self) -> dict[str, Any]:
        """Phase 1.4 full state report (kept for existing callers/tests)."""
        return {
            "device_id": self.device_id,
            "device_type": self.device_type,
            "state": self._state,
            "last_updated": self.updated_at,
        }
