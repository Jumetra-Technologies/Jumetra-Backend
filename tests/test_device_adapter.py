"""Sprint 25 — hybrid device adapter layer tests."""

from __future__ import annotations

from engine.communication.memory_adapter import make_adapter_pair
from engine.hybrid.adapters import (
    HybridMqttAdapter,
    HybridSerialAdapter,
    HybridSimulatorAdapter,
    HybridVirtualAdapter,
    HybridWifiAdapter,
)
from engine.hybrid.device import HybridDeviceMode
from engine.simulation.adapters import InProcessSimulatorAdapter
from engine.simulation.runtime.engine import SimulationEngine


class TestDeviceAdapters:
    def test_serial_adapter(self):
        engine_side, device_side = make_adapter_pair()
        adapter = HybridSerialAdapter(device_side)
        adapter.connect()
        adapter.send({"type": "HELLO", "source": "esp32_01"})
        assert adapter.mode == HybridDeviceMode.PHYSICAL
        assert adapter.is_connected

    def test_wifi_adapter_stub(self):
        adapter = HybridWifiAdapter()
        adapter.connect()
        adapter.send({"action": "ping"})
        msg = adapter.receive()
        assert msg is not None
        assert msg["transport"] == "wifi"

    def test_mqtt_adapter_stub(self):
        adapter = HybridMqttAdapter()
        adapter.connect()
        adapter.send({"action": "read", "topic": "hhip/sensor"})
        msg = adapter.receive()
        assert msg["transport"] == "mqtt"

    def test_simulator_adapter(self):
        backend = InProcessSimulatorAdapter()
        adapter = HybridSimulatorAdapter(backend)
        adapter.connect()
        adapter.load_circuit({"nodes": [{"id": "D2", "default_value": 0}]})
        adapter.write_pin("D2", 1)
        assert adapter.read_pin("D2") == 1

    def test_virtual_adapter(self):
        engine = SimulationEngine(
            laboratory_id="LAB001",
            controller_id="esp32",
            component_instances=[
                {"instance_id": "VCI001", "component_id": "led", "pin_map": {"pin_0": "D2"}}
            ],
            circuit={"nodes": [], "edges": []},
        )
        adapter = HybridVirtualAdapter(engine)
        adapter.connect()
        adapter.send({"instance_id": "VCI001", "action": "on"})
        state = adapter.receive()
        assert state is not None
        assert state["state"]["behaviors"][0]["state"]["on"] is True

    def test_common_health_shape(self):
        adapter = HybridWifiAdapter()
        health = adapter.health()
        assert "adapter" in health
        assert "mode" in health
