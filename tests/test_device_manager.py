import pytest

from engine.devices.manager import DeviceManager, UnknownVirtualDeviceError
from engine.devices.registry import DeviceRegistry
from engine.virtual.virtual_led import VirtualLED


class TestVirtualRegistration:
    def test_register_virtual_adds_device(self):
        manager = DeviceManager()
        led = VirtualLED("virtual_led_01")
        manager.register_virtual(led)
        assert manager.get_virtual("virtual_led_01") is led

    def test_get_virtual_returns_none_for_unknown(self):
        manager = DeviceManager()
        assert manager.get_virtual("does_not_exist") is None

    def test_remove_virtual_deletes_device(self):
        manager = DeviceManager()
        led = VirtualLED("virtual_led_01")
        manager.register_virtual(led)
        manager.remove_virtual("virtual_led_01")
        assert manager.get_virtual("virtual_led_01") is None

    def test_remove_unknown_virtual_device_raises(self):
        manager = DeviceManager()
        with pytest.raises(UnknownVirtualDeviceError):
            manager.remove_virtual("does_not_exist")

    def test_all_virtual_returns_every_registered_device(self):
        manager = DeviceManager()
        manager.register_virtual(VirtualLED("virtual_led_01"))
        manager.register_virtual(VirtualLED("virtual_led_02"))
        ids = {d.device_id for d in manager.all_virtual()}
        assert ids == {"virtual_led_01", "virtual_led_02"}


class TestUnifiedLookup:
    def test_get_finds_virtual_device(self):
        manager = DeviceManager()
        led = VirtualLED("virtual_led_01")
        manager.register_virtual(led)
        assert manager.get("virtual_led_01") is led

    def test_get_finds_physical_device(self):
        physical_registry = DeviceRegistry()
        physical_registry.register(device_id="esp32_01", device_type="esp32")
        manager = DeviceManager(physical_registry=physical_registry)
        found = manager.get("esp32_01")
        assert found is not None
        assert found.device_id == "esp32_01"

    def test_get_returns_none_for_unknown_id(self):
        manager = DeviceManager()
        assert manager.get("does_not_exist") is None

    def test_contains_checks_both_registries(self):
        physical_registry = DeviceRegistry()
        physical_registry.register(device_id="esp32_01", device_type="esp32")
        manager = DeviceManager(physical_registry=physical_registry)
        manager.register_virtual(VirtualLED("virtual_led_01"))

        assert "esp32_01" in manager
        assert "virtual_led_01" in manager
        assert "does_not_exist" not in manager

    def test_wraps_existing_physical_registry_without_replacing_it(self):
        physical_registry = DeviceRegistry()
        manager = DeviceManager(physical_registry=physical_registry)
        assert manager.physical is physical_registry
