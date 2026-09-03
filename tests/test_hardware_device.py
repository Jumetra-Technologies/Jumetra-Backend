"""Tests for universal HardwareDevice abstraction."""

from __future__ import annotations

from pathlib import Path

from engine.hybrid.hardware import Capability, HardwareDevice, get_profile_registry


PROFILES = Path(__file__).resolve().parents[1] / "data" / "hardware_profiles"


class TestHardwareDevice:
    def test_from_profile_esp32(self):
        registry = get_profile_registry(PROFILES)
        profile = registry.get("esp32")
        assert profile is not None
        device = HardwareDevice.from_profile(
            profile,
            device_id="esp32_lab",
            endpoint="COM4",
        )
        assert device.vendor == "Espressif"
        assert device.category == "microcontroller"
        assert device.transport == "serial"
        assert "D13" in device.pins
        assert any(c.name == "wifi" for c in device.capabilities)

    def test_from_discovery_uses_profile(self):
        device = HardwareDevice.from_discovery(
            device_id="uno_1",
            board_type="arduino-uno",
            port="COM3",
            profiles_dir=PROFILES,
        )
        assert device.manufacturer == "Arduino"
        assert device.model.startswith("Arduino")
        data = device.to_dict()
        assert data["communication_method"] == "serial"
        assert data["connected"] is True

    def test_capability_from_string_list(self):
        caps = Capability.from_list(["gpio", {"name": "pwm", "kind": "pwm"}])
        assert caps[0].name == "gpio"
        assert caps[1].kind == "pwm"

    def test_raspberry_pi_ssh_default(self):
        device = HardwareDevice.from_discovery(
            device_id="rpi4_1",
            board_type="raspberry-pi-4",
            endpoint="192.168.1.50",
            profiles_dir=PROFILES,
        )
        assert device.transport == "ssh"
        assert "GPIO17" in device.pins
