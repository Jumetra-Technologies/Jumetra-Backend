"""Tests for universal hardware discovery across board types."""

from __future__ import annotations

import threading
import time
from pathlib import Path

from engine.communication.memory_adapter import make_adapter_pair
from engine.events.event_bus import EventBus
from engine.hybrid.device_agent import AGENT_EVENT_DEVICE_DISCOVERY
from engine.hybrid.physical_layer import PhysicalHybridLayer
from engine.hybrid.registry import HybridRegistry
from engine.protocol.messages import MessageType, create_message


PROFILES = Path(__file__).resolve().parents[1] / "data" / "hardware_profiles"


def _discovery(device_id: str, board_type: str, **extra) -> dict:
    return create_message(
        type_=MessageType.EVENT,
        source=device_id,
        target="hhip",
        sequence=1,
        payload={
            "event": AGENT_EVENT_DEVICE_DISCOVERY,
            "device_id": device_id,
            "board_type": board_type,
            "device_type": board_type,
            "firmware_version": "1.0.0",
            "capabilities": ["gpio"],
            **extra,
        },
    )


class TestUniversalDiscovery:
    def test_registry_lists_supported_boards(self):
        boards = HybridRegistry.supported_board_types()
        assert "esp32" in boards
        assert "arduino-uno" in boards
        assert "stm32" in boards
        assert "raspberry-pi-4" in boards
        assert "raspberry-pi-pico" in boards

    def test_connect_esp32_enriches_profile(self, tmp_path):
        engine_side, device_side = make_adapter_pair(timeout=0.2)
        layer = PhysicalHybridLayer(
            event_bus=EventBus(),
            data_dir=tmp_path,
            transport_factory=lambda _: engine_side,
            profiles_dir=PROFILES,
        )
        device_side.connect()

        def boot():
            time.sleep(0.05)
            device_side.send(_discovery("esp32_u", "esp32"))

        threading.Thread(target=boot, daemon=True).start()
        device = layer.connect_device(port="COM_ESP", board_type="esp32", device_id="esp32_u")
        assert device["vendor"] == "Espressif"
        assert device["communication_method"] == "serial"
        assert device["manufacturer"] == "Espressif"
        assert len(device["pins"]) >= 1

    def test_connect_arduino_and_pico(self, tmp_path):
        engine_side, device_side = make_adapter_pair(timeout=0.2)
        layer = PhysicalHybridLayer(
            event_bus=EventBus(),
            data_dir=tmp_path,
            transport_factory=lambda _: engine_side,
            profiles_dir=PROFILES,
        )
        device_side.connect()
        device_side.send(_discovery("uno_u", "arduino-uno", vendor="Arduino"))
        uno = layer.connect_device(port="COM_UNO", board_type="arduino-uno", device_id="uno_u")
        assert uno["board_type"] == "arduino-uno"
        assert "Arduino" in (uno.get("manufacturer") or uno.get("vendor") or "")

        # Fallback without discovery message still uses profile
        engine2, _ = make_adapter_pair(timeout=0.05)
        layer2 = PhysicalHybridLayer(
            event_bus=EventBus(),
            data_dir=tmp_path / "pico",
            transport_factory=lambda _: engine2,
            profiles_dir=PROFILES,
        )
        pico = layer2.connect_device(
            port="COM_PICO",
            board_type="raspberry-pi-pico",
            device_id="pico_u",
            wait_discovery_s=0.1,
        )
        assert pico["board_type"] == "raspberry-pi-pico"
        assert pico["vendor"] == "Raspberry Pi Foundation"

    def test_raspberry_pi_ssh_connect_without_serial(self, tmp_path):
        layer = PhysicalHybridLayer(
            event_bus=EventBus(),
            data_dir=tmp_path,
            profiles_dir=PROFILES,
        )
        device = layer.connect_device(
            endpoint="192.168.0.20",
            board_type="raspberry-pi-4",
            device_id="rpi4_lab",
            transport="ssh",
            wait_discovery_s=0.05,
        )
        assert device["transport"] == "ssh"
        assert device["communication_method"] == "ssh"
        assert device["category"] == "single-board-computer"
        assert any(p["pin_id"].startswith("GPIO") for p in device["pins"])
