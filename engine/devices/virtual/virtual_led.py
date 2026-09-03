"""Virtual LED — software ON/OFF output with brightness and future color."""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional, TYPE_CHECKING

from .base_device import DeviceStatus, VirtualDevice

if TYPE_CHECKING:
    from ...events.event import Event

logger = logging.getLogger("hhip.devices.virtual.led")

# Optional publisher: publish(event_type, source, target, payload) -> None
EventPublishFn = Callable[[str, str, str, dict], None]


class VirtualLED(VirtualDevice):
    """An LED that exists only in software.

    Driven by :meth:`turn_on` / :meth:`turn_off` / :meth:`toggle`, or by
    :meth:`handle_event` when a ``STATE_UPDATE`` targets this device.
    """

    ON = "ON"
    OFF = "OFF"

    def __init__(
        self,
        device_id: str,
        *,
        device_name: Optional[str] = None,
        brightness: int = 100,
        color: Optional[str] = None,
        publish: Optional[EventPublishFn] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            device_id,
            device_type="LED",
            device_name=device_name or "LED",
            **kwargs,
        )
        self._brightness = self._clamp_brightness(brightness)
        self.color = color  # future-ready (e.g. "#FF0000" or "red")
        self._publish = publish
        self._state = self.OFF  # set without StateManager noise during construction
        self.updated_at = self.created_at

    @staticmethod
    def _clamp_brightness(value: int) -> int:
        try:
            level = int(value)
        except (TypeError, ValueError):
            level = 100
        return max(0, min(100, level))

    @property
    def brightness(self) -> int:
        return self._brightness

    @brightness.setter
    def brightness(self, value: int) -> None:
        from .base_device import _now_ms

        self._brightness = self._clamp_brightness(value)
        self.updated_at = _now_ms()

    def _emit_local_change(self, previous: Any, new_state: str) -> None:
        if previous == new_state:
            return
        logger.info("[VIRTUAL LED] %s: %s → %s", self.device_id, previous, new_state)
        if self._publish is not None:
            self._publish(
                "STATE_UPDATE",
                self.device_id,
                self.device_id,
                {
                    "state": new_state,
                    "brightness": self._brightness,
                    "color": self.color,
                },
            )

    def _set(self, new_state: str, *, source: str = "local") -> None:
        previous = self.update_state(new_state, source=source)
        if previous != new_state:
            self._emit_local_change(previous, new_state)

    def turn_on(self) -> None:
        self._set(self.ON)

    def turn_off(self) -> None:
        self._set(self.OFF)

    def toggle(self) -> None:
        self._set(self.OFF if self._state == self.ON else self.ON)

    def handle_event(self, event: "Event") -> None:
        """Apply a STATE_UPDATE Event targeted at this LED."""
        if event.target and event.target != self.device_id:
            return
        if event.event_type != "STATE_UPDATE":
            return
        payload = event.payload if isinstance(event.payload, dict) else {}
        if "brightness" in payload:
            self.brightness = payload["brightness"]
        if "color" in payload:
            self.color = payload.get("color")
        self.receive_event(payload, source=event.source)

    def receive_event(self, payload: dict, *, source: str = "event") -> None:
        """Handle an inbound STATE_UPDATE payload, e.g. ``{"state": "ON"}``."""
        if "brightness" in payload:
            self.brightness = payload["brightness"]
        if "color" in payload and payload.get("color") is not None:
            self.color = payload.get("color")

        requested = payload.get("state")
        if requested == self.ON:
            previous = self.update_state(self.ON, source=source)
            if previous != self.ON:
                logger.info("[VIRTUAL LED] %s: %s → %s", self.device_id, previous, self.ON)
        elif requested == self.OFF:
            previous = self.update_state(self.OFF, source=source)
            if previous != self.OFF:
                logger.info("[VIRTUAL LED] %s: %s → %s", self.device_id, previous, self.OFF)
        else:
            logger.warning(
                "[VIRTUAL LED] %s received unrecognized state %r; ignoring",
                self.device_id,
                requested,
            )

    def serialize(self) -> dict:
        data = super().serialize()
        data["brightness"] = self._brightness
        data["color"] = self.color
        return data

    def deserialize(self, data: Any) -> None:
        super().deserialize(data)
        if "brightness" in data:
            self._brightness = self._clamp_brightness(data["brightness"])
        if "color" in data:
            self.color = data["color"]

    def report_state(self) -> dict:
        report = super().report_state()
        # Preserve Phase 1.4 test expectation for device_type key while
        # exposing LED-specific fields.
        report["brightness"] = self._brightness
        report["color"] = self.color
        return report
