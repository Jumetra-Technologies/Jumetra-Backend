"""Sprint 36 EventBus bridge over the existing serial adapter.

Reuse decisions
---------------
* ``SerialAdapter`` (and ``InMemoryAdapter`` with the same
  connect/send/receive shape) already does NDJSON encode/decode.
  This module calls ``adapter.receive()`` — it does not read bytes or
  parse JSON.
* ``validate_message()`` already checks protocol version and required
  fields. This module does not reimplement that.
* ``HHIPEngine.handle_message()`` already publishes onto EventBus, but
  as the *wire* type (``HELLO`` / ``EVENT``). ``DiscoveryListener`` only
  matches ``HybridEventType.PHYSICAL_DEVICE_CONNECTED`` (and GPIO /
  HEARTBEAT). Publishing HELLO therefore never creates a HardwareNode.
  That mapping gap is what this bridge fills. It does not replace
  ``HHIPEngine`` or ``SerialHardwareTransport``.
* ``SerialHardwareTransport`` remains the hybrid ``HardwareTransport``
  implementation. This file is not a second serial driver.

Invalid messages are rejected (not published). Device registration uses
existing ``DeviceManager.register_physical_from_hello``.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from engine.devices.device_identity import DeviceIdentityClaim
from engine.events.event import Event
from engine.events.event_bus import EventBus
from engine.hybrid.events import HybridEventType, publish_hybrid_event
from engine.protocol.messages import MessageType, ProtocolError, validate_message

logger = logging.getLogger("hhip.communication.serial_bridge")


class SerialEventBridge:
    """Poll one SerialAdapter-shaped transport and publish HybridEventType events."""

    def __init__(
        self,
        adapter: Any,
        event_bus: EventBus,
        *,
        device_manager: Any = None,
        endpoint: str = "",
    ) -> None:
        self.adapter = adapter
        self.event_bus = event_bus
        self.device_manager = device_manager
        self.endpoint = endpoint or str(getattr(adapter, "port", "") or "")
        self.last_errors: list[str] = []

    def poll(self) -> Optional[Event]:
        """Receive at most one line, validate, publish. None on timeout or reject."""
        self.last_errors = []
        try:
            message = self.adapter.receive()
        except ProtocolError as exc:
            self.last_errors = [str(exc)]
            logger.warning("[SERIAL BRIDGE] Dropped unparseable line: %s", exc)
            return None

        if message is None:
            return None

        errors = validate_message(message)
        if errors:
            self.last_errors = list(errors)
            logger.warning("[SERIAL BRIDGE] Invalid message: %s", "; ".join(errors))
            return None

        return self._dispatch(message)

    def _dispatch(self, message: dict[str, Any]) -> Optional[Event]:
        msg_type = str(message.get("type") or "")
        payload = message.get("payload") if isinstance(message.get("payload"), dict) else {}
        event_name = str(payload.get("event") or "")
        source = str(message.get("source") or "")

        claim = DeviceIdentityClaim.from_message(message)
        if claim is not None:
            return self._on_hello(claim)

        if msg_type == MessageType.EVENT and event_name == "GPIO_STATE":
            return self._on_gpio_state(source, payload)

        if msg_type == MessageType.STATE_UPDATE and (
            "pin" in payload or "pin_id" in payload
        ):
            return self._on_gpio_state(source, payload)

        if msg_type == MessageType.HEARTBEAT:
            return self._on_heartbeat(source, payload)

        if msg_type == MessageType.DISCONNECT:
            return publish_hybrid_event(
                self.event_bus,
                HybridEventType.PHYSICAL_DEVICE_DISCONNECTED,
                source=source,
                payload={"device_id": source},
            )

        return None

    def _on_hello(self, claim: DeviceIdentityClaim) -> Event:
        if self.device_manager is not None:
            self.device_manager.register_physical_from_hello(
                device_id=claim.device_id,
                device_type=claim.board_type,
                firmware_version=claim.firmware_version or None,
            )
        return publish_hybrid_event(
            self.event_bus,
            HybridEventType.PHYSICAL_DEVICE_CONNECTED,
            source=claim.device_id,
            payload=claim.to_discovery_payload(endpoint=self.endpoint),
        )

    def _on_gpio_state(self, source: str, payload: dict[str, Any]) -> Event:
        device_id = str(payload.get("device_id") or source)
        pin = str(payload.get("pin") or payload.get("pin_id") or "")
        return publish_hybrid_event(
            self.event_bus,
            HybridEventType.GPIO_STATE,
            source=device_id,
            payload={
                "device_id": device_id,
                "pin": pin,
                "value": payload.get("value", payload.get("state", 0)),
            },
        )

    def _on_heartbeat(self, source: str, payload: dict[str, Any]) -> Event:
        device_id = str(payload.get("device_id") or source)
        if self.device_manager is not None:
            device = self.device_manager.get_device(device_id)
            touch = getattr(device, "touch", None)
            if callable(touch):
                touch()
        event = Event.create(
            event_type="HEARTBEAT",
            source=device_id,
            payload={"device_id": device_id},
        )
        self.event_bus.publish(event)
        return event
