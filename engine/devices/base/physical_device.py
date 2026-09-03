"""PhysicalDevice — abstraction over wire-connected hardware."""

from __future__ import annotations

from typing import Any, Mapping, Optional, TYPE_CHECKING

from .device import Device, DeviceMode, DeviceStatus

if TYPE_CHECKING:
    from ...events.event import Event


class PhysicalDevice(Device):
    """Represents a physical device known to HHIP (e.g. ESP32 on serial).

    Does not open transports itself — the communication layer owns that.
    This class is the Device-abstraction view used by DeviceManager.
    """

    def __init__(
        self,
        device_id: str,
        device_type: str = "ESP32",
        *,
        device_name: Optional[str] = None,
        manufacturer: Optional[str] = None,
        model: Optional[str] = None,
        firmware_version: Optional[str] = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> None:
        super().__init__(
            device_id=device_id,
            device_type=device_type,
            device_mode=DeviceMode.PHYSICAL,
            device_name=device_name or device_id,
            manufacturer=manufacturer,
            model=model,
            firmware_version=firmware_version,
            metadata=metadata,
        )
        self.last_seen: int = self.created_at

    def mark_connected(self) -> None:
        """Mark the device as connected / READY (e.g. after HELLO)."""
        self.set_status(DeviceStatus.READY)
        self._initialized = True
        from .device import _now_ms

        self.last_seen = _now_ms()

    def mark_disconnected(self) -> None:
        """Mark the device OFFLINE (e.g. disconnect / timeout)."""
        self.set_status(DeviceStatus.OFFLINE)
        self._initialized = False

    def touch(self) -> None:
        """Refresh last_seen (e.g. on HEARTBEAT)."""
        from .device import _now_ms

        self.last_seen = _now_ms()
        if self._status == DeviceStatus.OFFLINE:
            self.set_status(DeviceStatus.READY)

    def handle_event(self, event: "Event") -> None:
        """Physical devices are typically sinks via transport, not local handlers."""
        if event.target and event.target != self.device_id:
            return
        # Future: apply inbound WRITE / STATE_UPDATE locally for digital twin.
        return
