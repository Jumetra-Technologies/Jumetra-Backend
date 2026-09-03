"""RouterSubscriber — delivers STATE_UPDATE Events to devices via DeviceManager.

The EventBus stays device-agnostic; this subscriber owns the lookup and
delivery logic.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from ..devices.manager import DeviceManager
from ..devices.virtual.base_device import VirtualDevice
from ..events.event import Event
from ..events.subscriber import EventSubscriber
from ..state.state_manager import StateManager

logger = logging.getLogger("hhip.routing.router_subscriber")

SendCallback = Callable[[str, dict], None]


class RouterSubscriber(EventSubscriber):
    """Subscribe to the Event Bus and route STATE_UPDATE events to devices."""

    def __init__(
        self,
        device_manager: DeviceManager,
        state_manager: StateManager,
        send_callback: Optional[SendCallback] = None,
    ) -> None:
        self.device_manager = device_manager
        self.state_manager = state_manager
        self._send = send_callback

    def handle_event(self, event: Event) -> None:
        if event.event_type != "STATE_UPDATE":
            return

        target = event.target
        if not target:
            logger.warning("[ROUTER] STATE_UPDATE missing target; dropping %s", event.event_id)
            return

        device = self.device_manager.get_virtual(target)
        if device is not None:
            self._deliver_virtual(event, device)
            return

        physical = self.device_manager.physical.get(target)
        if physical is not None:
            self._deliver_physical(event)
            return

        logger.warning(
            "[ROUTER] STATE_UPDATE → %s → No device registered; dropping", target
        )

    def _deliver_virtual(self, event: Event, device: VirtualDevice) -> None:
        previous_state = device.state
        device.handle_event(event)
        logger.info(
            "[ROUTER] STATE_UPDATE → %s → Delivered (%s → %s)",
            device.device_id,
            previous_state,
            device.state,
        )
        if previous_state != device.state or event.source:
            self.state_manager.record(
                device_id=device.device_id,
                previous_state=previous_state,
                current_state=device.state,
                source=event.source,
            )

    def _deliver_physical(self, event: Event) -> None:
        if self._send is None:
            logger.warning(
                "[ROUTER] STATE_UPDATE → %s → No send_callback; cannot deliver", event.target
            )
            return

        payload = dict(event.payload) if isinstance(event.payload, dict) else {}
        self._send(event.target, payload)
        logger.info("[ROUTER] STATE_UPDATE → %s → Delivered (physical)", event.target)
