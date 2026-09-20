"""Sprint 36: SerialEventBridge reuses SerialAdapter + validate_message + EventBus."""

from __future__ import annotations

import time
from pathlib import Path

from engine.communication.memory_adapter import make_adapter_pair
from engine.communication.transports.serial_transport import SerialEventBridge
from engine.devices.device_identity import DeviceIdentityClaim
from engine.devices.device_manager import DeviceManager
from engine.events.event_bus import EventBus
from engine.events.subscriber import EventSubscriber
from engine.hardware_nodes.discovery_listener import DiscoveryListener
from engine.hardware_nodes.workspace_sync import WorkspaceSyncService
from engine.hybrid.events import HybridEventType
from engine.protocol.messages import (
    PROTOCOL_VERSION,
    MessageType,
    ProtocolError,
    create_message,
)


class _Recorder(EventSubscriber):
    def __init__(self) -> None:
        self.events: list = []

    def handle_event(self, event) -> None:
        self.events.append(event)


def _hello(source: str = "esp32_01", **payload) -> dict:
    body = {"device_type": "esp32", "firmware_version": "1.0.0-hhip-sdk"}
    body.update(payload)
    return create_message(
        type_=MessageType.HELLO,
        source=source,
        target="hhip",
        sequence=1,
        payload=body,
    )


def _discovery(source: str = "esp32_AABB") -> dict:
    return create_message(
        type_=MessageType.EVENT,
        source=source,
        target="hhip",
        sequence=1,
        payload={
            "event": "DEVICE_DISCOVERY",
            "device_id": source,
            "board_type": "esp32",
            "firmware_version": "1.0.0-hhip-agent",
            "capabilities": ["gpio", "pwm", "adc"],
        },
    )


class TestDeviceIdentityClaim:
    def test_hello_is_unvalidated_claim_not_a_store(self):
        claim = DeviceIdentityClaim.from_message(_hello())
        assert claim is not None
        assert claim.device_id == "esp32_01"
        assert claim.board_type == "esp32"
        assert claim.firmware_version == "1.0.0-hhip-sdk"
        assert claim.connection_state == "connecting"

    def test_discovery_event(self):
        claim = DeviceIdentityClaim.from_message(_discovery())
        assert claim is not None
        assert claim.capabilities == ("gpio", "pwm", "adc")

    def test_heartbeat_is_not_a_claim(self):
        msg = create_message(MessageType.HEARTBEAT, "esp32_01", "hhip", 2)
        assert DeviceIdentityClaim.from_message(msg) is None


class TestSerialEventBridge:
    def test_receive_hello_registers_device_and_publishes_physical_connected(self, tmp_path: Path):
        engine_side, device_side = make_adapter_pair(timeout=0.05)
        engine_side.connect()
        device_side.connect()

        bus = EventBus()
        recorder = _Recorder()
        bus.register_subscriber(recorder)
        sync = WorkspaceSyncService(data_dir=tmp_path, event_bus=bus)
        DiscoveryListener(sync, event_bus=bus)
        manager = DeviceManager()
        manager.bind_event_bus(bus)

        bridge = SerialEventBridge(
            engine_side, bus, device_manager=manager, endpoint="COM9"
        )
        device_side.send(_hello())
        event = bridge.poll()

        assert event is not None
        assert event.event_type == HybridEventType.PHYSICAL_DEVICE_CONNECTED
        assert any(
            e.event_type == HybridEventType.PHYSICAL_DEVICE_CONNECTED for e in recorder.events
        )
        assert "esp32_01" in manager
        device = manager.get_device("esp32_01")
        assert device is not None
        assert device.firmware_version == "1.0.0-hhip-sdk"

        node = sync.get_node("esp32_01")
        assert node is not None
        assert node["board_type"] == "esp32"
        assert node["status"] == "online"
        assert node["port"] == "COM9"

    def test_receive_device_discovery_uses_same_connect_event(self, tmp_path: Path):
        engine_side, device_side = make_adapter_pair(timeout=0.05)
        engine_side.connect()
        device_side.connect()
        bus = EventBus()
        sync = WorkspaceSyncService(data_dir=tmp_path, event_bus=bus)
        DiscoveryListener(sync, event_bus=bus)
        manager = DeviceManager()
        bridge = SerialEventBridge(engine_side, bus, device_manager=manager)

        device_side.send(_discovery())
        event = bridge.poll()
        assert event is not None
        assert event.event_type == HybridEventType.PHYSICAL_DEVICE_CONNECTED
        assert sync.get_node("esp32_AABB") is not None

    def test_reject_invalid_protocol(self):
        engine_side, device_side = make_adapter_pair(timeout=0.05)
        engine_side.connect()
        device_side.connect()
        bus = EventBus()
        recorder = _Recorder()
        bus.register_subscriber(recorder)
        manager = DeviceManager()
        bridge = SerialEventBridge(engine_side, bus, device_manager=manager)

        bad = _hello()
        bad["version"] = 99
        device_side.send(bad)
        assert bridge.poll() is None
        assert bridge.last_errors
        assert any("version" in err.lower() for err in bridge.last_errors)
        assert "esp32_01" not in manager
        assert not any(
            e.event_type == HybridEventType.PHYSICAL_DEVICE_CONNECTED for e in recorder.events
        )

        unknown = _hello()
        unknown["type"] = "NOT_A_REAL_TYPE"
        device_side.send(unknown)
        assert bridge.poll() is None
        assert "esp32_01" not in manager

    def test_reject_unparseable_line(self):
        class _BadJsonAdapter:
            port = "COM1"

            def receive(self):
                raise ProtocolError("Invalid JSON: boom")

        bus = EventBus()
        recorder = _Recorder()
        bus.register_subscriber(recorder)
        bridge = SerialEventBridge(_BadJsonAdapter(), bus)
        assert bridge.poll() is None
        assert bridge.last_errors
        assert recorder.events == []

    def test_heartbeat_update(self, tmp_path: Path):
        engine_side, device_side = make_adapter_pair(timeout=0.05)
        engine_side.connect()
        device_side.connect()
        bus = EventBus()
        sync = WorkspaceSyncService(data_dir=tmp_path, event_bus=bus)
        DiscoveryListener(sync, event_bus=bus)
        manager = DeviceManager()
        bridge = SerialEventBridge(engine_side, bus, device_manager=manager)

        device_side.send(_hello())
        assert bridge.poll() is not None
        physical = manager.get_device("esp32_01")
        seen_after_hello = physical.last_seen
        node_after_hello = sync.get_node("esp32_01")["heartbeat_ms"]

        time.sleep(0.02)
        device_side.send(
            create_message(MessageType.HEARTBEAT, "esp32_01", "hhip", 2)
        )
        event = bridge.poll()
        assert event is not None
        assert event.event_type == "HEARTBEAT"
        assert physical.last_seen >= seen_after_hello
        assert sync.get_node("esp32_01")["heartbeat_ms"] >= node_after_hello
        assert sync.get_node("esp32_01")["status"] == "online"

    def test_gpio_state_uses_listener_event_type(self, tmp_path: Path):
        engine_side, device_side = make_adapter_pair(timeout=0.05)
        engine_side.connect()
        device_side.connect()
        bus = EventBus()
        sync = WorkspaceSyncService(data_dir=tmp_path, event_bus=bus)
        DiscoveryListener(sync, event_bus=bus)
        bridge = SerialEventBridge(engine_side, bus, device_manager=DeviceManager())

        device_side.send(_hello())
        bridge.poll()
        device_side.send(
            create_message(
                MessageType.EVENT,
                "esp32_01",
                "hhip",
                3,
                payload={"event": "GPIO_STATE", "pin": "D13", "value": 1},
            )
        )
        event = bridge.poll()
        assert event is not None
        assert event.event_type == HybridEventType.GPIO_STATE
        pin = sync.get_node_obj("esp32_01").pins["D13"]
        assert pin.state.value == 1

    def test_validate_uses_protocol_version_constant(self):
        msg = _hello()
        assert msg["version"] == PROTOCOL_VERSION
