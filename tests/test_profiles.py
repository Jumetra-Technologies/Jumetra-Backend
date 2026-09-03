"""Tests for hardware profile loading."""

from __future__ import annotations

from pathlib import Path

from engine.hybrid.hardware import ProfileRegistry, get_profile_registry


PROFILES = Path(__file__).resolve().parents[1] / "data" / "hardware_profiles"


class TestProfiles:
    def test_loads_all_required_profiles(self):
        registry = ProfileRegistry(PROFILES)
        ids = {p.profile_id for p in registry.list_profiles()}
        assert "esp32" in ids
        assert "arduino_uno" in ids
        assert "stm32" in ids
        assert "raspberry_pi_4" in ids
        assert "raspberry_pi_pico" in ids

    def test_resolve_aliases(self):
        registry = ProfileRegistry(PROFILES)
        assert registry.get("arduino-uno") is not None
        assert registry.get("raspberry-pi-pico") is not None
        assert registry.resolve_board_type("unknown-xyz").board_type == "unknown-xyz"

    def test_profile_to_dict(self):
        profile = get_profile_registry(PROFILES).get("stm32")
        assert profile is not None
        data = profile.to_dict()
        assert data["vendor"] == "STMicroelectronics"
        assert data["default_transport"] == "serial"
        assert len(data["pins"]) >= 1
