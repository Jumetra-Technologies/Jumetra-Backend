"""Physical ESP32 bridge — serial communication and event conversion."""

from __future__ import annotations

import time
from typing import Any, Optional

from engine.events.event_bus import EventBus
from engine.protocol.messages import MessageType, create_message, encode_message, validate_message

from ..adapters.serial_adapter import HybridSerialAdapter
from ..events import HybridEventType, publish_hybrid_event


class PhysicalESP32:
    """Bridge a physical ESP32 over serial into hybrid experiment events."""

    def __init__(
        self,
        device_id: str,
        adapter: HybridSerialAdapter,
        *,
        event_bus: Optional[EventBus] = None,
        experiment_id: str = "",
    ) -> None:
        self.device_id = device_id
        self.adapter = adapter
        self.event_bus = event_bus
        self.experiment_id = experiment_id
        self._sequence = 0
        self._connected = False
        self.last_message: Optional[dict[str, Any]] = None

    def connect(self) -> None:
        self.adapter.connect()
        self._connected = True

    def disconnect(self) -> None:
        self.adapter.disconnect()
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected and self.adapter.is_connected

    def send_hello(self, device_type: str = "esp32") -> dict[str, Any]:
        self._sequence += 1
        message = create_message(
            type_=MessageType.HELLO,
            source=self.device_id,
            target="hhip",
            sequence=self._sequence,
            payload={"device_type": device_type},
        )
        self._send_wire(message)
        return message

    def send_write(self, target: str, pin: str, value: Any) -> dict[str, Any]:
        self._sequence += 1
        message = create_message(
            type_=MessageType.WRITE,
            source="hhip",
            target=target,
            sequence=self._sequence,
            payload={"pin": pin, "value": value},
        )
        self._send_wire(message)
        return message

    def poll(self) -> Optional[dict[str, Any]]:
        """Receive and convert the next wire message to a hybrid event payload."""
        raw = self.adapter.receive()
        if raw is None:
            return None
        try:
            validate_message(raw)
        except Exception:
            return {"raw": raw, "valid": False}

        self.last_message = raw
        converted = self._wire_to_hybrid(raw)
        self._publish_physical(raw, converted)
        return converted

    def _send_wire(self, message: dict[str, Any]) -> None:
        self.adapter.send(message)
        if self.event_bus is not None:
            publish_hybrid_event(
                self.event_bus,
                HybridEventType.HYBRID_COMMAND_ROUTED,
                source=self.device_id,
                payload={"direction": "outbound", "message": message},
                experiment_id=self.experiment_id,
            )

    def _wire_to_hybrid(self, message: dict[str, Any]) -> dict[str, Any]:
        msg_type = message.get("type", "")
        payload = message.get("payload") or {}
        return {
            "device_id": self.device_id,
            "wire_type": msg_type,
            "source": message.get("source"),
            "target": message.get("target"),
            "payload": dict(payload),
            "timestamp_ms": int(time.time() * 1000),
            "encoded_preview": encode_message(message)[:120],
        }

    def _publish_physical(self, wire: dict[str, Any], converted: dict[str, Any]) -> None:
        if self.event_bus is None:
            return
        publish_hybrid_event(
            self.event_bus,
            HybridEventType.HYBRID_PHYSICAL_EVENT,
            source=self.device_id,
            payload={"wire": wire, "converted": converted},
            experiment_id=self.experiment_id,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "device_id": self.device_id,
            "connected": self.is_connected,
            "experiment_id": self.experiment_id,
            "last_message": self.last_message,
        }
