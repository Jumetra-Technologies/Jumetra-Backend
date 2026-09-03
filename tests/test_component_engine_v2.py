"""Sprint 32 — Component Engine v2 tests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from engine.components.v2 import (
    ComponentDefinition,
    ComponentRegistryV2,
    HardwareBinding,
    HardwareBindingStore,
    PackageLoader,
    PinDefinition,
    RendererRegistry,
    default_behavior_registry,
    default_registry_v2,
    publish_component_signal,
    resolve_packages_dir,
    validate_manifest_shape,
)
from engine.events.event_bus import EventBus
from engine.simulation.component_v2_adapter import ComponentSimulationAdapter


@pytest.fixture
def client(tmp_path):
    app = create_app(data_dir=tmp_path)
    with TestClient(app) as test_client:
        yield test_client


def test_packages_dir_resolves():
    path = resolve_packages_dir()
    assert path.is_absolute()
    assert path.is_dir()


def test_manifest_loading():
    loader = PackageLoader()
    packages = loader.load_all()
    assert len(packages) >= 15
    dht = next(p for p in packages if p.id == "dht22")
    assert dht.name
    assert len(dht.pins) >= 3


def test_svg_renderer_discovery():
    registry = default_registry_v2()
    renderers = RendererRegistry(registry)
    assert renderers.has_renderer("dht22")
    assert renderers.has_renderer("esp32")
    svg = renderers.get_svg("dht22")
    assert svg and "<svg" in svg


def test_pin_validation():
    pin = PinDefinition(id="data", name="DATA", type="GPIO", voltage=3.3)
    assert pin.validate() == []
    bad = PinDefinition(id="", name="X", type="NOT_A_TYPE", voltage=-1)
    errors = bad.validate()
    assert errors


def test_behavior_loading():
    behavior = default_behavior_registry.create(
        "temperature_sensor", component_id="dht22", instance_id="dht22_1"
    )
    signal = behavior.tick(1.0)
    assert "temperature" in signal
    assert "humidity" in signal


def test_component_search_v2():
    registry = ComponentRegistryV2()
    hits = registry.search("dht")
    ids = {h["id"] for h in hits}
    assert "dht22" in ids
    assert "dht11" in ids
    temp = registry.search("temperature")
    assert any(h["id"].startswith("dht") for h in temp)


def test_physical_binding():
    store = HardwareBindingStore()
    binding = HardwareBinding(component_id="dht22", instance_id="dht22_1", mode="virtual")
    store.upsert(binding)
    physical = store.switch_mode("dht22_1", "physical", device_id="dev1", transport="serial")
    assert physical.mode == "physical"
    assert physical.device_id == "dev1"
    hybrid = store.switch_mode("dht22_1", "hybrid", device_id="dev1")
    assert hybrid.mode == "hybrid"
    # wiring identity preserved
    assert hybrid.instance_id == "dht22_1"
    assert hybrid.component_id == "dht22"


def test_validate_manifest_shape():
    assert validate_manifest_shape({"id": "x", "name": "X", "category": "sensor", "pins": []}) == []
    errs = validate_manifest_shape({})
    assert any("id" in e for e in errs)


def test_component_signal_event():
    bus = EventBus()
    event = publish_component_signal(
        bus,
        component_id="dht22",
        instance_id="dht22_1",
        signal={"temperature": 25, "humidity": 60},
    )
    assert event.event_type == "COMPONENT_SIGNAL_CHANGED"
    assert event.payload["signal"]["temperature"] == 25


def test_simulation_adapter():
    adapter = ComponentSimulationAdapter()
    signal = adapter.tick("dht22", "dht22_1", 2.5)
    assert "temperature" in signal or "temperature_c" in signal


def test_api_search_v2(client):
    resp = client.get("/components/v2/search", params={"q": "dht"})
    assert resp.status_code == 200
    body = resp.json()
    assert "results" in body
    ids = {r["id"] for r in body["results"]}
    assert "dht22" in ids


def test_api_get_and_renderer(client):
    detail = client.get("/components/v2/dht22")
    assert detail.status_code == 200
    assert detail.json()["id"] == "dht22"
    assert detail.json()["pins"]
    svg = client.get("/components/v2/dht22/renderer.svg")
    assert svg.status_code == 200
    assert "svg" in svg.headers.get("content-type", "")


def test_api_debug_and_binding(client):
    dbg = client.get("/components/v2/debug")
    assert dbg.status_code == 200
    assert dbg.json()["total_packages"] >= 15
    created = client.post(
        "/components/v2/bindings",
        json={"component_id": "dht22", "instance_id": "inst1", "mode": "virtual"},
    )
    assert created.status_code == 200
    switched = client.post(
        "/components/v2/bindings/inst1/mode",
        json={"mode": "physical", "device_id": "COM3"},
    )
    assert switched.status_code == 200
    assert switched.json()["mode"] == "physical"


def test_api_simulate(client):
    resp = client.post("/components/v2/dht22/simulate", json={"instance_id": "n1", "t_s": 1.0})
    assert resp.status_code == 200
    assert "signal" in resp.json()


def test_definition_from_manifest_roundtrip():
    data = {
        "id": "demo",
        "name": "Demo",
        "category": "sensor",
        "pins": [{"id": "a", "name": "A", "type": "GPIO", "position": {"x": 1, "y": 2}}],
        "interfaces": ["GPIO"],
        "simulation": {"behavior": "temperature_sensor"},
        "hardware": {"physical_supported": True},
    }
    definition = ComponentDefinition.from_manifest(data)
    assert definition.validate() == []
    hit = definition.to_search_hit()
    assert hit["id"] == "demo"
    assert hit["pins"][0]["id"] == "a"


@pytest.mark.parametrize(
    "cid",
    [
        "esp32",
        "arduino-uno",
        "arduino-mega",
        "stm32",
        "raspberry-pi-pico",
        "raspberry-pi-4",
        "dht11",
        "dht22",
        "hc-sr04",
        "pir",
        "mq2",
        "soil-moisture",
        "led",
        "rgb-led",
        "relay",
        "servo",
        "buzzer",
    ],
)
def test_each_migrated_package_loads(cid):
    registry = default_registry_v2()
    comp = registry.require(cid)
    assert comp.id == cid
    assert comp.pins
    assert RendererRegistry(registry).has_renderer(cid)


@pytest.mark.parametrize(
    "behavior,key",
    [
        ("digital_output", "on"),
        ("servo_motor", "angle"),
        ("display", "display_text"),
        ("ultrasonic", "distance_cm"),
        ("motion_sensor", "motion"),
        ("analog_sensor", "adc"),
        ("relay", "closed"),
        ("mcu", "power_on"),
    ],
)
def test_behavior_variants(behavior, key):
    b = default_behavior_registry.create(behavior, component_id="x", instance_id="x1")
    signal = b.tick(0.5)
    assert key in signal


def test_search_category_sensor():
    hits = default_registry_v2().search("", category="sensor")
    assert hits
    assert all(h["category"] == "sensor" for h in hits)


def test_search_interface_gpio():
    hits = default_registry_v2().search("", interface="GPIO")
    assert any(h["id"] == "dht22" for h in hits)


def test_pin_aliases_normalize():
    pin = PinDefinition(id="sda", name="SDA", type="SDA")
    assert pin.type == "I2C_SDA"


def test_packages_list_api(client):
    resp = client.get("/components/v2/packages")
    assert resp.status_code == 200
    assert len(resp.json()) >= 15


def test_binding_to_virtual(client):
    client.post(
        "/components/v2/bindings",
        json={"component_id": "led", "instance_id": "led1", "mode": "physical", "device_id": "d1"},
    )
    back = client.post("/components/v2/bindings/led1/mode", json={"mode": "virtual"})
    assert back.json()["mode"] == "virtual"
    assert back.json()["device_id"] == ""
