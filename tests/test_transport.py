"""Tests for universal hardware transports."""

from __future__ import annotations

from engine.communication.memory_adapter import make_adapter_pair
from engine.hybrid.transports import (
    MqttHardwareTransport,
    SerialHardwareTransport,
    SshHardwareTransport,
    TransportKind,
    create_transport,
)
from engine.protocol.messages import MessageType, create_message


class TestTransport:
    def test_serial_transport_roundtrip(self):
        engine_side, device_side = make_adapter_pair(timeout=0.2)
        transport = SerialHardwareTransport(
            "COM_TEST",
            adapter_factory=lambda _: engine_side,
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
        msg = transport.receive()
        assert msg is not None
        assert msg["type"] == MessageType.HEARTBEAT
        assert transport.kind == TransportKind.SERIAL
        transport.disconnect()

    def test_mqtt_transport_inject(self):
        mqtt = MqttHardwareTransport("mqtt://localhost/hhip")
        mqtt.connect()
        mqtt.inject({"type": "HEARTBEAT", "source": "mqtt_dev", "payload": {}})
        msg = mqtt.receive()
        assert msg is not None
        mqtt.send({"type": "EVENT", "payload": {"event": "GPIO_WRITE"}})
        assert mqtt.drain_outbound()
        mqtt.disconnect()

    def test_ssh_transport_execute_simulated(self):
        ssh = SshHardwareTransport("192.168.1.10", username="pi")
        ssh.connect()
        result = ssh.execute("hostname")
        assert result["ok"] is True
        assert result.get("simulated") is True
        ssh.disconnect()

    def test_create_transport_factory(self):
        engine_side, _ = make_adapter_pair(timeout=0.2)
        t = create_transport("serial", "COM9", adapter_factory=lambda _: engine_side)
        assert isinstance(t, SerialHardwareTransport)
        m = create_transport("mqtt", "broker")
        assert isinstance(m, MqttHardwareTransport)
        s = create_transport("ssh", "pi.local")
        assert isinstance(s, SshHardwareTransport)
