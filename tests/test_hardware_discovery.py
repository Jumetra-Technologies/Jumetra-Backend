"""Tests for hardware discovery service."""

from __future__ import annotations

import threading
import time

import pytest

from engine.communication.memory_adapter import InMemoryAdapter, make_adapter_pair
from engine.discovery.handshake import perform_handshake
from engine.discovery.identify import identify_board
from engine.discovery.models import DiscoveryStatus
from engine.discovery.scanner import PortInfo
from engine.discovery.service import HardwareDiscoveryService
from engine.events.event_bus import EventBus
from engine.protocol.messages import MessageType, create_message


class TestBoardIdentification:
    def test_identify_esp32_cp2102(self):
        board_type, label = identify_board(vid=0x10C4, pid=0xEA60, description="CP2102 USB to UART", manufacturer="Silicon Labs")
        assert board_type == "esp32"

    def test_identify_pico(self):
        board_type, label = identify_board(vid=0x2E8A, pid=0x0005, description="Board CDC", manufacturer="Raspberry Pi")
        assert board_type == "raspberry-pi-pico"

    def test_unknown_serial(self):
        board_type, label = identify_board(vid=0xFFFF, pid=0x0001, description="Mystery", manufacturer="Acme")
        assert board_type == "unknown-serial"
        assert label == "Unknown Serial Device"


class TestHandshake:
    def test_device_hello_handshake(self):
        hhip_side, device_side = make_adapter_pair(timeout=0.2)
        hhip_side.connect()
        device_side.connect()
        device_side.send(
            create_message(
                type_=MessageType.HELLO,
                source="esp32_test",
                target="hhip-discovery",
                sequence=1,
                payload={
                    "device_type": "esp32",
                    "firmware_version": "1.2.3",
                    "capabilities": ["gpio", "wifi"],
                },
            )
        )
        result = perform_handshake(hhip_side, listen_ms=200, timeout_s=0.5)
        assert result.success
        assert result.hhip_firmware
        assert result.device_id == "esp32_test"
        assert result.firmware_version == "1.2.3"
        assert "gpio" in result.capabilities


class TestDiscoveryService:
    def test_scan_detects_mock_port(self):
        events: list[str] = []

        def port_lister():
            return [
                PortInfo(
                    device="COM_MOCK",
                    vid=0x10C4,
                    pid=0xEA60,
                    manufacturer="Silicon Labs",
                    description="CP2102 USB to UART",
                    serial_number="ABC123",
                )
            ]

        hhip_side, device_side = make_adapter_pair(timeout=0.2)

        def factory(port: str):
            return hhip_side

        bus = EventBus()
        received: list[str] = []

        from engine.events.subscriber import EventSubscriber

        class CaptureSubscriber(EventSubscriber):
            def handle_event(self, event):
                received.append(event.event_type)

        bus.register_subscriber(CaptureSubscriber())

        device_side.connect()

        def respond():
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline:
                msg = device_side.receive()
                if msg and msg.get("type") == MessageType.HELLO:
                    device_side.send(
                        create_message(
                            type_=MessageType.HELLO_ACK,
                            source="esp32_mock",
                            target="hhip-discovery",
                            sequence=2,
                            payload={
                                "device_id": "esp32_mock",
                                "device_type": "esp32",
                                "firmware_version": "2.0.0",
                                "capabilities": ["gpio", "uart"],
                            },
                        )
                    )
                    return

        responder = threading.Thread(target=respond, daemon=True)
        responder.start()
        time.sleep(0.05)

        svc = HardwareDiscoveryService(
            event_bus=bus,
            scan_interval_s=60,
            port_lister=port_lister,
            transport_factory=factory,
        )

        devices = svc.scan_once()
        responder.join(timeout=1)
        assert len(devices) == 1
        d = devices[0]
        assert d.port == "COM_MOCK"
        assert d.status == DiscoveryStatus.CONNECTED
        assert d.hhip_firmware
        assert d.device_id == "esp32_mock"
        assert "DEVICE_CONNECTED" in [e for e in received]

    def test_hot_unplug_marks_disconnected(self):
        ports = [
            PortInfo("COM1", 0x2341, 0x0043, "Arduino", "Uno", "SN1"),
        ]
        seen = {"count": 1}

        def port_lister():
            if seen["count"] > 0:
                seen["count"] -= 1
                return ports
            return []

        class BusyTransport:
            port = "COM1"

            def connect(self):
                raise OSError("access denied busy")

            def disconnect(self):
                pass

            def send(self, message):
                pass

            def receive(self):
                return None

        svc = HardwareDiscoveryService(
            scan_interval_s=60,
            port_lister=port_lister,
            transport_factory=lambda p: BusyTransport(),
        )
        svc.scan_once()
        assert svc.get_device("COM1") is not None
        svc.scan_once()
        assert svc.get_device("COM1").status == DiscoveryStatus.DISCONNECTED


class TestDiscoveryAPI:
    def test_discovery_list_endpoint(self, tmp_path):
        from fastapi.testclient import TestClient
        from api.main import create_app

        app = create_app(data_dir=tmp_path)
        with TestClient(app) as client:
            resp = client.get("/discovery/devices")
            assert resp.status_code == 200
            body = resp.json()
            assert "devices" in body
            assert "count" in body

            scan = client.post("/discovery/scan")
            assert scan.status_code == 200
