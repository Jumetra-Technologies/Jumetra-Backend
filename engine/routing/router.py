"""Generic message router.

Bridges the protocol layer and the virtual device layer:

    Inbound:  decoded STATE_UPDATE -> target device_id -> virtual device.receive_event()
    Outbound: virtual device state change -> STATE_UPDATE message -> transport

Deliberately contains no device-type-specific logic (no "if it's an
LED do X, if it's a button do Y"). It only resolves a target device_id
via the DeviceManager and hands the payload off — VirtualLED,
VirtualButton, and anything added in later phases decide what the
payload means.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from ..devices.manager import DeviceManager
from ..state.state_manager import StateManager
from ..devices.virtual.base_device import VirtualDevice

logger = logging.getLogger("hhip.routing.router")

# Called as send_callback(target_device_id, payload) to actually transmit
# an outgoing STATE_UPDATE. Keeps Router decoupled from the transport
# and protocol-encoding details, which stay owned by HHIPEngine.
SendCallback = Callable[[str, dict], None]


class Router:
    """Routes STATE_UPDATE traffic between the wire protocol and virtual devices."""

    def __init__(
        self,
        device_manager: DeviceManager,
        state_manager: StateManager,
        send_callback: Optional[SendCallback] = None,
    ) -> None:
        self.device_manager = device_manager
        self.state_manager = state_manager
        self._send = send_callback

    def route_incoming(self, message: dict) -> None:
        """Route a decoded, already-validated STATE_UPDATE message to its target.

        Example flow (Demonstration A):
            Physical Button -> ESP32 -> STATE_UPDATE(target=virtual_led_01)
            -> route_incoming() -> VirtualLED.receive_event() -> StateManager.record()
        """
        target = message["target"]
        source = message["source"]
        payload = message.get("payload", {})

        device = self.device_manager.get_virtual(target)
        if device is None:
            logger.warning(
                "[ROUTER] No virtual device registered for target %r; dropping message", target
            )
            return

        previous_state = device.state
        device.receive_event(payload)
        logger.info("[ROUTER] %s -> %s: %s -> %s", source, target, previous_state, device.state)

        self.state_manager.record(
            device_id=target,
            previous_state=previous_state,
            current_state=device.state,
            source=source,
        )

    def route_outgoing(
        self,
        target: str,
        payload: dict,
        source_device: VirtualDevice,
        previous_state: Any,
    ) -> None:
        """Send a STATE_UPDATE out over the transport, triggered by a
        virtual device's own state change (Demonstration B: VirtualButton press).

        previous_state is passed in explicitly (rather than re-read
        from source_device) because by the time this runs the device
        has already updated to its new state.
        """
        if self._send is None:
            logger.warning(
                "[ROUTER] No send_callback configured; cannot deliver STATE_UPDATE to %r", target
            )
            return

        self._send(target, payload)
        logger.info("[ROUTER] %s -> %s: %s", source_device.device_id, target, payload)

        self.state_manager.record(
            device_id=source_device.device_id,
            previous_state=previous_state,
            current_state=source_device.state,
            source="hhip",
        )
