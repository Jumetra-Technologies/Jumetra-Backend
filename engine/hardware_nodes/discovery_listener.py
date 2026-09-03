"""Listen for hybrid / discovery board events and sync workspace HardwareNodes."""

from __future__ import annotations

import logging
from typing import Any, Optional

from engine.events.event import Event
from engine.events.subscriber import EventSubscriber
from engine.hybrid.events import HybridEventType

from .workspace_sync import WorkspaceEventType, WorkspaceSyncService

logger = logging.getLogger(__name__)


class DiscoveryListener(EventSubscriber):
    """
    Whenever HybridRegistry / HybridRouter publishes BOARD / PHYSICAL connect events,
    create a HardwareNode and emit WORKSPACE_NODE_CREATED.

    On disconnect → WORKSPACE_NODE_REMOVED (node marked waiting).
    On GPIO_STATE → live pin updates.
    """

    CONNECT_EVENTS = frozenset(
        {
            HybridEventType.PHYSICAL_DEVICE_CONNECTED,
            "BOARD_CONNECTED",  # external alias only when source is not workspace-sync
        }
    )
    DISCONNECT_EVENTS = frozenset(
        {
            HybridEventType.PHYSICAL_DEVICE_DISCONNECTED,
            "BOARD_DISCONNECTED",
        }
    )
    # Only hybrid router GPIO — never workspace-sync echoes (avoids EventBus loops)
    GPIO_EVENTS = frozenset(
        {
            HybridEventType.GPIO_STATE,
            HybridEventType.GPIO_WRITE,
        }
    )

    def __init__(
        self,
        sync: WorkspaceSyncService,
        *,
        workspace_id: str = "",
        event_bus: Any = None,
    ) -> None:
        self.sync = sync
        self.workspace_id = workspace_id
        self.event_bus = event_bus
        if event_bus is not None:
            event_bus.register_subscriber(self)

    def handle_event(self, event: Event) -> None:
        # Ignore events we ourselves published via WorkspaceSyncService
        if str(event.source or "") == "workspace-sync":
            return

        et = str(event.event_type or "")
        payload = dict(event.payload or {})

        if et in self.CONNECT_EVENTS:
            device = payload if payload.get("device_id") or payload.get("board_type") else {
                **payload,
                "device_id": payload.get("device_id") or event.source,
            }
            try:
                self.sync.upsert_from_device(device, workspace_id=self.workspace_id)
            except Exception:  # noqa: BLE001
                logger.exception("DiscoveryListener failed to create HardwareNode")
            return

        if et in self.DISCONNECT_EVENTS:
            device_id = str(payload.get("device_id") or event.source or "")
            if device_id:
                self.sync.remove_device(device_id)
            return

        if et in self.GPIO_EVENTS:
            device_id = str(payload.get("device_id") or event.source or "")
            pin = str(payload.get("pin") or payload.get("pin_id") or "")
            if not device_id or not pin:
                return
            value = payload.get("value", 0)
            self.sync.update_pin_state(
                device_id,
                pin,
                value,
                voltage=payload.get("voltage"),
                frequency_hz=payload.get("frequency_hz"),
                duty_cycle=payload.get("duty_cycle"),
                mode=payload.get("mode"),
            )
            return

        if et in ("HEARTBEAT", WorkspaceEventType.HEARTBEAT):
            device_id = str(payload.get("device_id") or event.source or "")
            if device_id:
                self.sync.touch_heartbeat(device_id)
