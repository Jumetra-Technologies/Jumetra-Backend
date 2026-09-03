"""CorrectionTransportSubscriber — bridges correction events to the wire."""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from ..devices.base.device import Device, DeviceMode
from ..events.event import Event
from ..events.subscriber import EventSubscriber
from ..protocol.correction import SyncCorrectionRequest
from ..protocol.correction_wire import build_wire_correction_request
from ..synchronization.events import SyncEventType

logger = logging.getLogger("hhip.events.correction_bridge")

WireSendCallback = Callable[[dict[str, Any]], None]


class CorrectionTransportSubscriber(EventSubscriber):
    """Forward host-originated SYNC_CORRECTION_REQUEST events to physical devices."""

    def __init__(
        self,
        device_manager: Any,
        send_callback: Optional[WireSendCallback] = None,
    ) -> None:
        self._device_manager = device_manager
        self._send = send_callback
        self._sequence = 0

    def handle_event(self, event: Event) -> None:
        if event.event_type != SyncEventType.SYNC_CORRECTION_REQUEST:
            return
        if event.metadata.get("origin") != "synchronization":
            return

        target = event.target
        if not target or self._device_manager is None or self._send is None:
            return

        device = self._device_manager.get_device(target)
        if device is None or not isinstance(device, Device):
            return
        if device.device_mode != DeviceMode.PHYSICAL:
            return

        payload = event.payload if isinstance(event.payload, dict) else {}
        request = SyncCorrectionRequest.from_dict({**payload, "device_id": target})
        self._sequence += 1
        wire = build_wire_correction_request(request, sequence=self._sequence)
        wire.setdefault("message_id", request.transaction_id)
        logger.info(
            "[CORR BRIDGE] TX SYNC_CORRECTION_REQUEST → %s txn=%s step=%.2f",
            target,
            request.transaction_id,
            request.correction_step,
        )
        self._send(wire)
