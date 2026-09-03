import pytest

from engine.devices.registry import (
    DeviceMode,
    DeviceRegistry,
    DeviceStatus,
    UnknownDeviceError,
)


class TestRegister:
    def test_register_adds_device(self):
        registry = DeviceRegistry()
        device = registry.register(device_id="esp32_01", device_type="esp32")
        assert device.device_id == "esp32_01"
        assert device.device_type == "esp32"
        assert device.mode == DeviceMode.PHYSICAL
        assert device.status == DeviceStatus.CONNECTED
        assert "esp32_01" in registry
        assert len(registry) == 1

    def test_register_same_device_id_refreshes_instead_of_duplicating(self):
        registry = DeviceRegistry()
        first = registry.register(device_id="esp32_01", device_type="esp32")
        second = registry.register(device_id="esp32_01", device_type="esp32")
        assert len(registry) == 1
        assert first is second

    def test_register_supports_virtual_mode(self):
        registry = DeviceRegistry()
        device = registry.register(device_id="soil_moisture_01", device_type="soil_moisture", mode=DeviceMode.VIRTUAL)
        assert device.mode == DeviceMode.VIRTUAL


class TestGet:
    def test_get_returns_registered_device(self):
        registry = DeviceRegistry()
        registry.register(device_id="esp32_01", device_type="esp32")
        device = registry.get("esp32_01")
        assert device is not None
        assert device.device_id == "esp32_01"

    def test_get_returns_none_for_unknown_device(self):
        registry = DeviceRegistry()
        assert registry.get("does_not_exist") is None


class TestRemove:
    def test_remove_deletes_device(self):
        registry = DeviceRegistry()
        registry.register(device_id="esp32_01", device_type="esp32")
        registry.remove("esp32_01")
        assert "esp32_01" not in registry
        assert len(registry) == 0

    def test_remove_unknown_device_raises(self):
        registry = DeviceRegistry()
        with pytest.raises(UnknownDeviceError):
            registry.remove("does_not_exist")


class TestAllDevices:
    def test_all_devices_returns_every_registered_device(self):
        registry = DeviceRegistry()
        registry.register(device_id="esp32_01", device_type="esp32")
        registry.register(device_id="esp32_02", device_type="esp32")
        ids = {d.device_id for d in registry.all_devices()}
        assert ids == {"esp32_01", "esp32_02"}

    def test_all_devices_empty_registry(self):
        registry = DeviceRegistry()
        assert registry.all_devices() == []


class TestTouch:
    def test_touch_updates_last_seen(self):
        registry = DeviceRegistry()
        device = registry.register(device_id="esp32_01", device_type="esp32")
        original_last_seen = device.last_seen
        registry.touch("esp32_01")
        assert device.last_seen >= original_last_seen

    def test_touch_unknown_device_raises(self):
        registry = DeviceRegistry()
        with pytest.raises(UnknownDeviceError):
            registry.touch("does_not_exist")
