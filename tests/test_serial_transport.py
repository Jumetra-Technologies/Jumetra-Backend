"""Tests for SerialTransport."""

from __future__ import annotations

import time

from engine.communication.memory_adapter import make_adapter_pair
from engine.hybrid.serial_transport import SerialTransport
from engine.protocol.messages import MessageType, create_message


class TestSerialTransport:
    def test_connect_send_receive(self):
        engine_side, device_side = make_adapter_pair(timeout=0.2)
        transport = SerialTransport("memory://test", transport_factory=lambda _: engine_side)
        transport.connect()
        device_side.connect()
        msg = create_message(
            type_=MessageType.HEARTBEAT,
            source="esp32_test",
            target="hhip",
            sequence=1,
            payload={},
        )
        device_side.send(msg)
        received = transport.receive()
        assert received is not None
        assert received["type"] == MessageType.HEARTBEAT
        transport.disconnect()

    def test_heartbeat_updates_liveness(self):
        engine_side, device_side = make_adapter_pair(timeout=0.2)
        transport = SerialTransport(
            "memory://hb",
            transport_factory=lambda _: engine_side,
            heartbeat_timeout_s=2.0,
        )
        transport.connect()
        device_side.connect()
        device_side.send(
            create_message(
                type_=MessageType.HEARTBEAT,
                source="dev",
                target="hhip",
                sequence=1,
                payload={},
            )
        )
        transport.receive()
        assert transport.is_connected

    def test_disconnect(self):
        engine_side, _ = make_adapter_pair(timeout=0.2)
        transport = SerialTransport("memory://d", transport_factory=lambda _: engine_side)
        transport.connect()
        transport.disconnect()
        assert not transport.is_connected
