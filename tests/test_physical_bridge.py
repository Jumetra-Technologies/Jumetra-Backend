"""Sprint 25 — physical ESP32 bridge tests."""

from __future__ import annotations

from engine.communication.memory_adapter import make_adapter_pair
from engine.events.event import Event
from engine.events.event_bus import EventBus
from engine.events.subscriber import EventSubscriber
from engine.hybrid.adapters import HybridSerialAdapter
from engine.hybrid.events import HybridEventType
from engine.hybrid.physical import PhysicalESP32
from engine.protocol.messages import MessageType, create_message


class _Recorder(EventSubscriber):
    def __init__(self) -> None:
        self.received: list[Event] = []

    def handle_event(self, event: Event) -> None:
        self.received.append(event)


class TestPhysicalBridge:
    def test_send_hello(self):
        engine_side, device_side = make_adapter_pair()
        adapter = HybridSerialAdapter(device_side)
        bridge = PhysicalESP32("esp32_01", adapter)
        bridge.connect()
        msg = bridge.send_hello()
        assert msg["type"] == MessageType.HELLO
        engine_side.connect()
        received = engine_side.receive()
        assert received is not None
        assert received["source"] == "esp32_01"

    def test_poll_converts_wire_message(self):
        engine_side, device_side = make_adapter_pair()
        adapter = HybridSerialAdapter(device_side)
        bus = EventBus()
        recorder = _Recorder()
        bus.register_subscriber(recorder)
        bridge = PhysicalESP32("esp32_01", adapter, event_bus=bus, experiment_id="HYB001")
        bridge.connect()

        engine_side.connect()
        engine_side.send(
            create_message(
                type_=MessageType.STATE_UPDATE,
                source="esp32_01",
                target="virtual_led_01",
                sequence=2,
                payload={"state": "ON"},
            )
        )

        converted = bridge.poll()
        assert converted is not None
        assert converted["wire_type"] == MessageType.STATE_UPDATE
        assert converted["payload"]["state"] == "ON"
        assert any(e.event_type == HybridEventType.HYBRID_PHYSICAL_EVENT for e in recorder.received)

    def test_send_write(self):
        _, device_side = make_adapter_pair()
        adapter = HybridSerialAdapter(device_side)
        bridge = PhysicalESP32("esp32_01", adapter)
        bridge.connect()
        msg = bridge.send_write("esp32_01", "D13", 1)
        assert msg["type"] == MessageType.WRITE
