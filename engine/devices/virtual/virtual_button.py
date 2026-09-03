"""Virtual Button — software input that publishes STATE_UPDATE via the bus."""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional, TYPE_CHECKING

from .base_device import VirtualDevice

if TYPE_CHECKING:
    from ...events.event import Event

logger = logging.getLogger("hhip.devices.virtual.button")

# Invoked as on_change(button, previous_state, new_state) — Phase 1.4 compat.
StateChangeCallback = Callable[["VirtualButton", str, str], None]

# publish(event_type, source, target, payload) — Event Bus integration.
EventPublishFn = Callable[[str, str, str, dict], None]


class VirtualButton(VirtualDevice):
    """A button that exists only in software.

    Pressing/releasing updates local state and publishes a ``STATE_UPDATE``
    Event through the injected publisher (wired to the Event Bus by the
    engine). It never controls LEDs directly.
    """

    PRESSED = "PRESSED"
    RELEASED = "RELEASED"

    def __init__(
        self,
        device_id: str,
        *,
        device_name: Optional[str] = None,
        on_change: Optional[StateChangeCallback] = None,
        publish: Optional[EventPublishFn] = None,
        default_target: str = "",
        **kwargs: Any,
    ) -> None:
        super().__init__(
            device_id,
            device_type="BUTTON",
            device_name=device_name or "Button",
            **kwargs,
        )
        self.on_change = on_change
        self._publish = publish
        self.default_target = default_target
        self._state = self.RELEASED
        self.updated_at = self.created_at

    def _emit(self, previous: str, new_state: str) -> None:
        logger.info("[VIRTUAL BUTTON] %s: %s → %s", self.device_id, previous, new_state)
        if self.on_change is not None:
            self.on_change(self, previous, new_state)
        if self._publish is not None:
            # Map button gesture to a generic ON/OFF payload for physical LEDs
            # and other sinks. Target comes from default_target (engine-wired).
            payload = {
                "state": "ON" if new_state == self.PRESSED else "OFF",
                "button_state": new_state,
            }
            target = self.default_target or self.device_id
            self._publish("STATE_UPDATE", self.device_id, target, payload)

    def _set(self, new_state: str, *, source: str = "local") -> None:
        previous = self.update_state(new_state, source=source)
        if previous == new_state:
            return
        self._emit(previous if previous is not None else self.RELEASED, new_state)

    def press(self) -> None:
        self._set(self.PRESSED)

    def release(self) -> None:
        self._set(self.RELEASED)

    def toggle(self) -> None:
        """Toggle between PRESSED and RELEASED."""
        self._set(self.RELEASED if self._state == self.PRESSED else self.PRESSED)

    def handle_event(self, event: "Event") -> None:
        """Buttons are primarily sources; inbound events are ignored."""
        logger.debug(
            "[VIRTUAL BUTTON] %s ignoring inbound event %s", self.device_id, event.event_type
        )

    def receive_event(self, payload: dict) -> None:
        """Buttons ignore inbound payloads (Phase 1.4 behaviour)."""
        logger.debug("[VIRTUAL BUTTON] %s ignoring inbound event: %s", self.device_id, payload)
