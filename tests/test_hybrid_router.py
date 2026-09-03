"""Tests for HybridRouter."""

from __future__ import annotations

import threading
import time

from engine.communication.memory_adapter import make_adapter_pair
from engine.events.event import Event
from engine.events.event_bus import EventBus
from engine.events.subscriber import EventSubscriber
from engine.hybrid.device_agent import AGENT_EVENT_DEVICE_DISCOVERY, DeviceAgent
from engine.hybrid.events import HybridEventType
from engine.hybrid.hybrid_router import HybridRouter
from engine.hybrid.physical_layer import PhysicalHybridLayer
from engine.hybrid.pin_mapper import PinMapper
from engine.hybrid.registry import PhysicalDeviceRegistry
from engine.hybrid.serial_transport import SerialTransport
from engine.protocol.messages import MessageType, create_message


class _Recorder(EventSubscriber):
    def __init__(self) -> None:
        self.events: list[Event] = []

    def handle_event(self, event: Event) -> None:
        self.events.append(event)


def _discovery_message(device_id: str = "esp32_test") -> dict:
    return create_message(
        type_=MessageType.EVENT,
        source=device_id,
        target="hhip",
        sequence=1,
        payload={
            "event": AGENT_EVENT_DEVICE_DISCOVERY,
            "device_id": device_id,
            "board_type": "esp32",
            "firmware_version": "1.0.0",
            "capabilities": ["gpio"],
            "pins": [
                {"pin_id": "D13", "name": "GPIO13", "number": 13, "interfaces": ["gpio"]},
            ],
        },
    )


class TestHybridRouter:
    def test_connect_and_gpio_write(self, tmp_path):
        engine_side, device_side = make_adapter_pair(timeout=0.2)
        bus = EventBus()
        layer = PhysicalHybridLayer(
            event_bus=bus,
            data_dir=tmp_path,
            transport_factory=lambda _: engine_side,
        )

        device_side.connect()

        def boot():
            time.sleep(0.05)
            device_side.send(_discovery_message("esp32_hybrid"))

        threading.Thread(target=boot, daemon=True).start()
        device = layer.connect_device(port="COM_TEST", board_type="esp32", device_id="esp32_hybrid")
        assert device["device_id"] == "esp32_hybrid"

        result = layer.write_gpio("esp32_hybrid", "D13", 1)
        assert result["pin"] == "D13"
        assert result["value"] == 1

        inbound = device_side.receive()
        assert inbound is not None
        assert inbound["payload"]["event"] == "GPIO_WRITE"

    def test_gpio_state_publishes_event(self, tmp_path):
        engine_side, device_side = make_adapter_pair(timeout=0.2)
        bus = EventBus()
        recorder = _Recorder()
        bus.register_subscriber(recorder)
        layer = PhysicalHybridLayer(
            event_bus=bus,
            data_dir=tmp_path,
            transport_factory=lambda _: engine_side,
        )
        device_side.connect()
        device_side.send(_discovery_message("esp32_gpio"))
        layer.connect_device(port="COM2", device_id="esp32_gpio")

        device_side.send(
            create_message(
                type_=MessageType.EVENT,
                source="esp32_gpio",
                target="hhip",
                sequence=2,
                payload={"event": "GPIO_STATE", "pin": "D13", "value": 1},
            )
        )
        layer.poll()
        assert any(e.event_type == HybridEventType.GPIO_STATE for e in recorder.events)

    def test_pin_mirror_to_virtual(self, tmp_path):
        engine_side, device_side = make_adapter_pair(timeout=0.2)
        bus = EventBus()
        recorder = _Recorder()
        bus.register_subscriber(recorder)
        layer = PhysicalHybridLayer(
            event_bus=bus,
            data_dir=tmp_path,
            transport_factory=lambda _: engine_side,
        )
        device_side.connect()
        device_side.send(_discovery_message("esp32_mirror"))
        layer.connect_device(port="COM3", device_id="esp32_mirror")
        layer.create_connection(
            virtual_node_id="NLED01",
            virtual_pin_id="anode",
            physical_device_id="esp32_mirror",
            physical_pin_id="D13",
        )

        device_side.send(
            create_message(
                type_=MessageType.EVENT,
                source="esp32_mirror",
                target="hhip",
                sequence=3,
                payload={"event": "GPIO_STATE", "pin": "D13", "value": 1},
            )
        )
        layer.poll()
        assert any(e.event_type == HybridEventType.HYBRID_VIRTUAL_EVENT for e in recorder.events)
