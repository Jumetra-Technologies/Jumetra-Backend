"""HHIP firmware agent protocol handler."""

from __future__ import annotations

import time
from typing import Any, Optional

from engine.protocol.messages import MessageType, create_message, validate_message

from .physical_device import PhysicalDevice, PhysicalPin

AGENT_EVENT_DEVICE_DISCOVERY = "DEVICE_DISCOVERY"
AGENT_EVENT_GPIO_STATE = "GPIO_STATE"
AGENT_CMD_GPIO_WRITE = "GPIO_WRITE"


class DeviceAgent:
    """Speak the hhip_agent firmware protocol over any HardwareTransport."""

    def __init__(self, transport: Any, *, device_id: str = "") -> None:
        self.transport = transport
        self.device_id = device_id
        self._sequence = 0
        self._device: Optional[PhysicalDevice] = None

    @property
    def device(self) -> Optional[PhysicalDevice]:
        return self._device

    def connect(self) -> None:
        self.transport.connect()

    def disconnect(self) -> None:
        self.transport.disconnect()
        if self._device is not None:
            self._device.connected = False

    def poll(self) -> list[dict[str, Any]]:
        """Receive and parse pending agent messages."""
        events: list[dict[str, Any]] = []
        for _ in range(8):
            msg = self.transport.receive()
            if msg is None:
                break
            parsed = self._parse_inbound(msg)
            if parsed:
                events.append(parsed)
        return events

    def wait_for_discovery(self, *, timeout_s: float = 2.0) -> Optional[PhysicalDevice]:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            for event in self.poll():
                if event.get("kind") == AGENT_EVENT_DEVICE_DISCOVERY:
                    return self._device
            time.sleep(0.05)
        return self._device

    def send_gpio_write(self, pin_id: str, value: int) -> dict[str, Any]:
        self._sequence += 1
        message = create_message(
            type_=MessageType.EVENT,
            source="hhip",
            target=self.device_id or "device",
            sequence=self._sequence,
            payload={"event": AGENT_CMD_GPIO_WRITE, "pin": pin_id, "value": int(value)},
        )
        self.transport.send(message)
        return message

    def send_hello_ack(self) -> dict[str, Any]:
        self._sequence += 1
        message = create_message(
            type_=MessageType.HELLO_ACK,
            source="hhip-hybrid",
            target=self.device_id or "device",
            sequence=self._sequence,
            payload={"engine_version": "hybrid-1.0", "status": "ok"},
        )
        self.transport.send(message)
        return message

    def _parse_inbound(self, message: dict[str, Any]) -> Optional[dict[str, Any]]:
        if validate_message(message):
            return None

        msg_type = message.get("type")
        payload = message.get("payload") or {}
        source = str(message.get("source") or "")

        if msg_type == MessageType.HELLO:
            self.device_id = source or str(payload.get("device_id") or "device")
            self._device = PhysicalDevice.from_discovery(
                device_id=self.device_id,
                board_type=str(payload.get("device_type") or payload.get("board_type") or "unknown"),
                port=self._endpoint(),
                firmware_version=str(payload.get("firmware_version") or ""),
                capabilities=_as_list(payload.get("capabilities")),
                pin_specs=payload.get("pins") if isinstance(payload.get("pins"), list) else None,
                transport=self._transport_kind(),
            )
            self.send_hello_ack()
            return {"kind": AGENT_EVENT_DEVICE_DISCOVERY, "device": self._device.to_dict()}

        if msg_type == MessageType.EVENT:
            event_name = str(payload.get("event") or "")
            if event_name == AGENT_EVENT_DEVICE_DISCOVERY:
                self.device_id = str(payload.get("device_id") or source)
                pins_raw = payload.get("pins") or []
                self._device = PhysicalDevice.from_discovery(
                    device_id=self.device_id,
                    board_type=str(payload.get("board_type") or payload.get("device_type") or "unknown"),
                    port=self._endpoint(),
                    label=str(payload.get("label") or ""),
                    firmware_version=str(payload.get("firmware_version") or ""),
                    capabilities=_as_list(payload.get("capabilities")),
                    pin_specs=pins_raw if isinstance(pins_raw, list) else None,
                    transport=self._transport_kind(),
                    vendor=str(payload.get("vendor") or payload.get("manufacturer") or ""),
                    manufacturer=str(payload.get("manufacturer") or payload.get("vendor") or ""),
                )
                if isinstance(pins_raw, list) and pins_raw:
                    self._apply_pin_specs(pins_raw)
                return {"kind": AGENT_EVENT_DEVICE_DISCOVERY, "device": self._device.to_dict()}

            if event_name == AGENT_EVENT_GPIO_STATE:
                pin_id = str(payload.get("pin") or "")
                value = int(payload.get("value", 0))
                if self._device and pin_id:
                    self._device.update_pin_state(pin_id, value)
                return {
                    "kind": AGENT_EVENT_GPIO_STATE,
                    "device_id": self.device_id,
                    "pin": pin_id,
                    "value": value,
                }

            if event_name == AGENT_CMD_GPIO_WRITE:
                return {"kind": AGENT_CMD_GPIO_WRITE, "payload": dict(payload)}

        if msg_type == MessageType.HEARTBEAT:
            self.transport.record_heartbeat()
            return {"kind": "HEARTBEAT", "device_id": self.device_id or source}

        if msg_type in (MessageType.WRITE, MessageType.STATE_UPDATE):
            pin_id = str(payload.get("pin") or "")
            if pin_id and self._device:
                val = payload.get("value", payload.get("state"))
                if isinstance(val, (int, float)):
                    self._device.update_pin_state(pin_id, int(val))
            return {"kind": msg_type, "device_id": self.device_id, "payload": dict(payload)}

        return {"kind": msg_type, "device_id": self.device_id, "payload": dict(payload)}

    def _apply_pin_specs(self, specs: list[Any]) -> None:
        if self._device is None:
            return
        for spec in specs:
            if not isinstance(spec, dict):
                continue
            pid = str(spec.get("pin_id") or spec.get("id") or "")
            if not pid:
                continue
            self._device.pins[pid] = PhysicalPin(
                pin_id=pid,
                name=str(spec.get("name", pid)),
                number=spec.get("number", pid),
                interfaces=_as_list(spec.get("interfaces") or ["gpio"]),
                signal=str(spec.get("signal", "bidirectional")),
                voltage_v=float(spec.get("voltage_v", 3.3)),
                state=int(spec.get("state", 0)),
            )

    def _endpoint(self) -> str:
        return str(
            getattr(self.transport, "port", None)
            or getattr(self.transport, "endpoint", "")
            or ""
        )

    def _transport_kind(self) -> str:
        kind = getattr(self.transport, "kind", None)
        if kind is None:
            return "serial"
        return str(getattr(kind, "value", kind))


def _as_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [v.strip() for v in value.split(",") if v.strip()]
    if isinstance(value, list):
        return [str(v) for v in value]
    return []
