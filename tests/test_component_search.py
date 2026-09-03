"""Sprint 31 — component catalog search tests."""

from __future__ import annotations

from engine.components.search import ComponentIndex, ComponentSearchEngine, SearchFilters
from engine.lab_workspace.bus import build_bus_metadata
from engine.lab_workspace.catalog import get_component, search_catalog
from engine.lab_workspace.models import CanvasNode, CanvasWire, DeviceMode
from engine.lab_workspace.wire import validate_wire


def test_keyword_search_temperature():
    engine = ComponentSearchEngine()
    hits = engine.search("temperature")
    ids = {h["component_id"] for h in hits}
    assert "dht11" in ids or "dht22" in ids
    assert any("dht" in i for i in ids)


def test_alias_search_dht():
    engine = ComponentSearchEngine()
    hits = engine.search("dht")
    ids = {h["component_id"] for h in hits}
    assert "dht11" in ids
    assert "dht22" in ids
    assert "am2302" in ids


def test_wifi_search():
    engine = ComponentSearchEngine()
    hits = engine.search("wifi")
    ids = {h["component_id"] for h in hits}
    assert "esp32" in ids
    assert "esp8266" in ids
    assert "raspberry-pi-4" in ids


def test_motor_search():
    engine = ComponentSearchEngine()
    hits = engine.search("motor")
    ids = {h["component_id"] for h in hits}
    assert "servo" in ids
    assert "dc-motor" in ids
    assert "stepper-motor" in ids


def test_category_filter():
    engine = ComponentSearchEngine()
    hits = engine.search("", filters=SearchFilters(category="sensor"))
    assert hits
    assert all(h.get("catalog_category") == "sensor" for h in hits)


def test_interface_filter_gpio():
    engine = ComponentSearchEngine()
    hits = engine.search("", filters=SearchFilters(interfaces=["GPIO"]))
    assert hits
    assert any(h["component_id"] == "dht22" for h in hits)


def test_controller_compatibility():
    engine = ComponentSearchEngine()
    hits = engine.search("dht", filters=SearchFilters(controller_id="esp32"))
    ids = {h["component_id"] for h in hits}
    assert "dht22" in ids


def test_catalog_index_loads_json():
    index = ComponentIndex()
    assert index.reload() >= 30
    assert index.get("dht22") is not None


def test_search_catalog_workspace_bridge():
    items = search_catalog("temperature")
    ids = {i["component_id"] for i in items}
    assert "dht22" in ids or "dht11" in ids


def test_get_component_enriched_pins():
    spec = get_component("dht22")
    assert spec is not None
    assert spec["name"]
    assert isinstance(spec.get("pins"), (list, int))


def test_i2c_bus_metadata():
    meta = build_bus_metadata(
        protocol="i2c",
        source_handle="SDA",
        target_handle="SDA",
        source_component_id="esp32",
        target_component_id="oled-ssd1306",
    )
    assert meta["type"] == "I2C"
    assert meta["address"] == "0x3C"


def test_voltage_mismatch_rejects_5v_to_33_only():
    nodes = {
        "N1": CanvasNode(
            node_id="N1",
            component_id="arduino-uno",
            label="Uno",
            category="arduino",
            position={"x": 0, "y": 0},
            device_mode=DeviceMode.VIRTUAL,
        ),
        "N2": CanvasNode(
            node_id="N2",
            component_id="oled-ssd1306",
            label="OLED",
            category="displays",
            position={"x": 100, "y": 0},
            device_mode=DeviceMode.VIRTUAL,
        ),
    }
    wire = CanvasWire(
        wire_id="W1",
        source="N1",
        source_handle="5V",
        target="N2",
        target_handle="VCC",
        protocol="power",
        voltage_v=5.0,
    )
    result = validate_wire(wire, nodes)
    assert result.valid is False
    assert any("Voltage mismatch" in i for i in result.issues)


def test_gpio_to_dht_allowed():
    nodes = {
        "N1": CanvasNode(
            node_id="N1",
            component_id="esp32",
            label="ESP32",
            category="esp32",
            position={"x": 0, "y": 0},
            device_mode=DeviceMode.VIRTUAL,
        ),
        "N2": CanvasNode(
            node_id="N2",
            component_id="dht22",
            label="DHT22",
            category="sensors",
            position={"x": 100, "y": 0},
            device_mode=DeviceMode.VIRTUAL,
        ),
    }
    wire = CanvasWire(
        wire_id="W1",
        source="N1",
        source_handle="D4",
        target="N2",
        target_handle="DATA",
        protocol="digital",
        voltage_v=3.3,
    )
    result = validate_wire(wire, nodes)
    assert result.valid is True
