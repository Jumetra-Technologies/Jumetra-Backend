"""SyncTransportSubscriber — bridges EventBus SYNC_REQUEST to the wire.

Owns the *outbound* physical path only:

    SynchronizationManager → SYNC_REQUEST (EventBus)
        → SyncTransportSubscriber
        → send_callback(wire_message)
        → SerialAdapter / InMemoryAdapter

Inbound SYNC_RESPONSE is handled by the normal protocol path
(validate → Event.from_message → EventBus → SynchronizationManager).

The synchronization package never imports serial adapters.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from ..devices.base.device import Device, DeviceMode
from ..events.event import Event
from ..events.subscriber import EventSubscriber
from ..synchronization.agent import PhysicalSyncAgent
from ..synchronization.events import SyncEventType
from ..synchronization.protocol import SyncRequest

logger = logging.getLogger("hhip.events.sync_bridge")

# Full wire envelope → transport.send(message)
WireSendCallback = Callable[[dict[str, Any]], None]


class SyncTransportSubscriber(EventSubscriber):
    """Forward synchronization-originated SYNC_REQUEST events to physical devices."""

    def __init__(
        self,
        device_manager: Any,
        send_callback: Optional[WireSendCallback] = None,
    ) -> None:
        self._device_manager = device_manager
        self._send = send_callback

    def handle_event(self, event: Event) -> None:
        if event.event_type != SyncEventType.SYNC_REQUEST:
            return
        # Only host-originated measurement probes — never re-transmit wire RX.
        if event.metadata.get("origin") != "synchronization":
            return

        target = event.target
        if not target or self._device_manager is None:
            return

        device = self._device_manager.get_device(target)
        if device is None or not isinstance(device, Device):
            return
        if device.device_mode != DeviceMode.PHYSICAL:
            return

        if self._send is None:
            logger.warning(
                "[SYNC BRIDGE] SYNC_REQUEST → %s → no send_callback; cannot transmit",
                target,
            )
            return

        payload = event.payload if isinstance(event.payload, dict) else {}
        request = SyncRequest.from_dict(
            {
                **payload,
                "device_id": target,
                "server_timestamp": payload.get(
                    "server_timestamp", payload.get("request_time", 0)
                ),
                "sequence_number": payload.get("sequence_number", 0),
                "correlation_id": event.correlation_id or payload.get("correlation_id"),
                "request_id": payload.get("request_id"),
            }
        )
        agent = PhysicalSyncAgent(device)
        wire = agent.to_wire_request(request)
        # Align envelope correlation with the Event for transcript tracing.
        wire.setdefault("message_id", request.request_id)
        logger.info(
            "[SYNC BRIDGE] TX SYNC_REQUEST → %s request_id=%s",
            target,
            request.request_id,
        )
        self._send(wire)
