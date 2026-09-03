"""Tests for PhysicalDevice model."""

from __future__ import annotations

from engine.hybrid.physical_device import PhysicalDevice


class TestPhysicalDevice:
    def test_from_discovery_esp32(self):
        device = PhysicalDevice.from_discovery(
            device_id="esp32_abc",
            board_type="esp32",
            port="COM4",
            capabilities=["gpio", "pwm"],
        )
        assert device.device_id == "esp32_abc"
        assert device.connected is True
        assert len(device.pins) >= 3
        assert "D2" in device.pins

    def test_update_pin_state(self):
        device = PhysicalDevice.from_discovery(
            device_id="uno_1",
            board_type="arduino-uno",
            port="COM3",
        )
        device.update_pin_state("D13", 1)
        assert device.get_pin("D13").state == 1

    def test_to_dict(self):
        device = PhysicalDevice.from_discovery(
            device_id="esp32_x",
            board_type="esp32",
            port="COM8",
        )
        data = device.to_dict()
        assert data["device_id"] == "esp32_x"
        assert isinstance(data["pins"], list)
