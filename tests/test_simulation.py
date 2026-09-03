"""Sprint 23 — virtual simulation tests."""

from __future__ import annotations

import pytest

from engine.components import default_registry
from engine.controllers import default_controller_registry
from engine.simulation import (
    InProcessSimulatorAdapter,
    VirtualComponentFactory,
    VirtualLaboratoryService,
)


@pytest.fixture
def lab_service():
    return VirtualLaboratoryService(default_registry(), default_controller_registry())


class TestVirtualComponentFactory:
    def test_create_led_instance(self):
        components = default_registry()
        controllers = default_controller_registry()
        factory = VirtualComponentFactory()
        inst = factory.create(components.require("led"), controllers.require("esp32"))
        assert inst.component.component_id == "led"
        assert "pin_0" in inst.pin_map

    def test_create_batch_assigns_pins(self):
        components = default_registry()
        controllers = default_controller_registry()
        factory = VirtualComponentFactory()
        specs = [components.require("led"), components.require("dht11")]
        instances = factory.create_batch(specs, controllers.require("arduino-uno"))
        assert len(instances) == 2
        pins = [v for inst in instances for v in inst.pin_map.values()]
        assert len(set(pins)) == len(pins)


class TestSimulatorAdapter:
    def test_in_process_step(self):
        adapter = InProcessSimulatorAdapter()
        adapter.connect()
        adapter.load_circuit({"nodes": [{"id": "D2", "default_value": 0}]})
        result = adapter.step(10)
        assert result["tick_ms"] == 10
        adapter.write_pin("D2", 1)
        assert adapter.read_pin("D2") == 1
        adapter.disconnect()


class TestVirtualLaboratory:
    def test_create_laboratory(self, lab_service):
        lab = lab_service.create(
            name="Greenhouse Sim",
            controller_id="esp32",
            component_ids=["dht22", "soil-moisture", "relay"],
        )
        assert lab["laboratory_id"].startswith("LAB")
        assert lab["session"] is not None
        assert len(lab["session"]["components"]) == 3
        assert len(lab["session"]["circuit"]["nodes"]) >= 4

    def test_start_laboratory(self, lab_service):
        lab = lab_service.create(
            name="Test Lab",
            controller_id="arduino-uno",
            component_ids=["led"],
        )
        result = lab_service.start(lab["laboratory_id"])
        assert result["status"] == "running"
        assert result["state"]["behaviors"]
        step = lab_service.advance_simulation(lab["laboratory_id"], 100)
        assert step["step"]["sim_time_ms"] == 100

    def test_missing_component_rejected(self, lab_service):
        with pytest.raises(KeyError):
            lab_service.create(
                name="Bad Lab",
                controller_id="esp32",
                component_ids=["nonexistent-sensor"],
            )
