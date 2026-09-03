"""Route EventBus GPIO events to physical devices and mirror inbound state."""

from __future__ import annotations

import logging
from typing import Any, Optional

from engine.events.event import Event
from engine.events.event_bus import EventBus
from engine.events.subscriber import EventSubscriber

from .device_agent import AGENT_EVENT_GPIO_STATE, DeviceAgent
from .events import HybridEventType, publish_hybrid_event
from .pin_mapper import PinMapper
from .registry import PhysicalDeviceRegistry

logger = logging.getLogger("hhip.hybrid.router")


class HybridRouter(EventSubscriber):
    """Bridge EventBus GPIO events with physical serial agents."""

    def __init__(
        self,
        registry: PhysicalDeviceRegistry,
        pin_mapper: PinMapper,
        *,
        event_bus: Optional[EventBus] = None,
    ) -> None:
        self.registry = registry
        self.pin_mapper = pin_mapper
        self.event_bus = event_bus
        self._sequence = 0

    def handle_event(self, event: Event) -> None:
        if event.event_type == HybridEventType.GPIO_WRITE:
            self._route_gpio_write(event)
        elif event.event_type == HybridEventType.GPIO_STATE:
            self._mirror_gpio_state(event)

    def poll_physical(self) -> list[dict[str, Any]]:
        """Poll all agents and publish GPIO_STATE / connection events."""
        published: list[dict[str, Any]] = []
        for raw in self.registry.poll_all():
            kind = raw.get("kind")
            if kind == AGENT_EVENT_GPIO_STATE and self.event_bus:
                publish_hybrid_event(
                    self.event_bus,
                    HybridEventType.GPIO_STATE,
                    source=str(raw.get("device_id") or "physical"),
                    payload={
                        "pin": raw.get("pin"),
                        "value": raw.get("value"),
                        "device_id": raw.get("device_id"),
                    },
                )
                published.append(raw)
                self._fanout_to_virtual(raw)
        return published

    def write_gpio(
        self,
        device_id: str,
        pin_id: str,
        value: int,
        *,
        virtual_node_id: str = "",
    ) -> dict[str, Any]:
        agent = self.registry.get_agent(device_id)
        if agent is None:
            raise KeyError(f"physical device not connected: {device_id}")
        message = agent.send_gpio_write(pin_id, value)
        payload = {
            "device_id": device_id,
            "pin": pin_id,
            "value": int(value),
            "virtual_node_id": virtual_node_id,
            "message": message,
        }
        if self.event_bus:
            publish_hybrid_event(
                self.event_bus,
                HybridEventType.GPIO_WRITE,
                source="hhip-hybrid",
                target=device_id,
                payload=payload,
            )
        return payload

    def publish_connected(self, device: dict[str, Any]) -> None:
        if self.event_bus is None:
            return
        publish_hybrid_event(
            self.event_bus,
            HybridEventType.PHYSICAL_DEVICE_CONNECTED,
            source=str(device.get("device_id") or "physical"),
            payload=device,
        )

    def publish_disconnected(self, device_id: str) -> None:
        if self.event_bus is None:
            return
        publish_hybrid_event(
            self.event_bus,
            HybridEventType.PHYSICAL_DEVICE_DISCONNECTED,
            source=device_id,
            payload={"device_id": device_id},
        )

    def _route_gpio_write(self, event: Event) -> None:
        payload = event.payload or {}
        device_id = str(payload.get("device_id") or event.target or "")
        pin_id = str(payload.get("pin") or "")
        value = int(payload.get("value", 0))
        if not device_id or not pin_id:
            return
        try:
            self.write_gpio(device_id, pin_id, value, virtual_node_id=str(payload.get("virtual_node_id") or ""))
        except KeyError:
            logger.warning("[HYBRID] GPIO_WRITE target not found: %s", device_id)

    def _mirror_gpio_state(self, event: Event) -> None:
        if self.event_bus is None:
            return
        publish_hybrid_event(
            self.event_bus,
            HybridEventType.HYBRID_PIN_MIRROR,
            source=event.source,
            payload=event.payload or {},
        )

    def _fanout_to_virtual(self, gpio_event: dict[str, Any]) -> None:
        device_id = str(gpio_event.get("device_id") or "")
        pin_id = str(gpio_event.get("pin") or "")
        value = gpio_event.get("value")
        for conn in self.pin_mapper.connections_for_device(device_id):
            if conn.get("physical_pin_id") != pin_id:
                continue
            if self.event_bus is None:
                continue
            publish_hybrid_event(
                self.event_bus,
                HybridEventType.HYBRID_VIRTUAL_EVENT,
                source=device_id,
                target=str(conn.get("virtual_node_id") or ""),
                payload={
                    "virtual_node_id": conn.get("virtual_node_id"),
                    "virtual_pin_id": conn.get("virtual_pin_id"),
                    "physical_pin_id": pin_id,
                    "value": value,
                    "mirrored": True,
                },
            )
