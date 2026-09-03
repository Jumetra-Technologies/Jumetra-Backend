"""Sprint 25 — unified hybrid device abstraction tests."""

from __future__ import annotations

from engine.devices.base.device import DeviceMode
from engine.devices.base.physical_device import PhysicalDevice
from engine.hybrid.adapters import HybridSerialAdapter, HybridVirtualAdapter, HybridWifiAdapter
from engine.hybrid.device import HybridDevice, HybridDeviceMode, map_legacy_mode
from engine.communication.memory_adapter import make_adapter_pair


class TestHybridDevice:
    def test_modes(self):
        assert HybridDeviceMode.PHYSICAL.value == "physical"
        assert HybridDeviceMode.HYBRID.value == "hybrid"

    def test_from_physical(self):
        _, device_side = make_adapter_pair()
        adapter = HybridSerialAdapter(device_side)
        physical = PhysicalDevice(device_id="esp32_01")
        hybrid = HybridDevice.from_physical(physical, adapter)
        assert hybrid.mode == HybridDeviceMode.PHYSICAL
        assert hybrid.device_id == "esp32_01"

    def test_from_virtual(self):
        adapter = HybridVirtualAdapter()
        hybrid = HybridDevice.from_virtual(
            device_id="VCI001",
            component_id="dht11",
            instance_id="VCI001",
            adapter=adapter,
        )
        assert hybrid.mode == HybridDeviceMode.VIRTUAL
        assert hybrid.component_id == "dht11"

    def test_from_hybrid_binding(self):
        physical = HybridDevice("esp32_01", mode=HybridDeviceMode.PHYSICAL, available=True)
        virtual = HybridDevice("VCI001", mode=HybridDeviceMode.VIRTUAL, available=True)
        binding = HybridDevice.from_hybrid_binding("BIND001", physical=physical, virtual=virtual)
        assert binding.mode == HybridDeviceMode.HYBRID
        assert binding.metadata["physical_id"] == "esp32_01"

    def test_map_legacy_mode(self):
        assert map_legacy_mode(DeviceMode.PHYSICAL) == HybridDeviceMode.PHYSICAL

    def test_to_dict(self):
        hybrid = HybridDevice("dev1", mode=HybridDeviceMode.SIMULATED, device_type="simulator")
        data = hybrid.to_dict()
        assert data["mode"] == "simulated"
        assert data["device_id"] == "dev1"
