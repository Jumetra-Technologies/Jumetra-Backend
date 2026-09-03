"""Sprint 23 — component intelligence tests."""

from __future__ import annotations

import pytest

from engine.components import ComponentRegistry, ComponentSearch, default_registry
from engine.controllers import CompatibilityEngine, ControllerRegistry, default_controller_registry


@pytest.fixture
def component_registry():
    reg = ComponentRegistry()
    reg.load_seed()
    return reg


@pytest.fixture
def controller_registry():
    reg = ControllerRegistry()
    reg.load_seed()
    return reg


class TestComponentRegistry:
    def test_seed_loads_ten_components(self, component_registry):
        assert len(component_registry.list_all()) == 10

    def test_get_dht11(self, component_registry):
        comp = component_registry.require("dht11")
        assert comp.name == "DHT11"
        assert "digital" in comp.interfaces


class TestComponentSearch:
    def test_search_by_name(self, component_registry):
        search = ComponentSearch(component_registry)
        results = search.search("dht")
        ids = [r.component.component_id for r in results]
        assert "dht11" in ids
        assert "dht22" in ids

    def test_search_by_tag(self, component_registry):
        search = ComponentSearch(component_registry)
        results = search.search("humidity")
        assert len(results) >= 2

    def test_filter_category(self, component_registry):
        search = ComponentSearch(component_registry)
        results = search.search("", category="actuator")
        assert all(r.component.category == "actuator" for r in results)


class TestCompatibilityEngine:
    def test_dht11_compatible_with_esp32(self, component_registry, controller_registry):
        engine = CompatibilityEngine()
        comp = component_registry.require("dht11")
        ctrl = controller_registry.require("esp32")
        result = engine.check(comp, ctrl)
        assert result.compatible

    def test_hc_sr04_compatible_with_arduino_uno(self, component_registry, controller_registry):
        engine = CompatibilityEngine()
        comp = component_registry.require("hc-sr04")
        ctrl = controller_registry.require("arduino-uno")
        result = engine.check(comp, ctrl)
        assert result.compatible

    def test_compatible_controllers_list(self, component_registry, controller_registry):
        engine = CompatibilityEngine()
        comp = component_registry.require("led")
        results = engine.compatible_controllers(comp, controller_registry)
        assert len(results) == 6

    def test_default_registries(self):
        assert len(default_registry().list_all()) >= 10
        assert len(default_controller_registry().list_all()) == 6
