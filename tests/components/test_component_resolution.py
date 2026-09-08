import json

from engine.components import ComponentRegistry
from engine.components.loader import ComponentLoader


def _document(component_id: str, name: str) -> dict:
    return {
        "id": component_id,
        "name": name,
        "category": "sensor",
        "interfaces": ["GPIO"],
        "pins": [{"name": "DATA", "type": "GPIO"}],
    }


def _package(root, component_id: str, name: str = "Package Sensor") -> None:
    package = root / "sensors" / component_id
    package.mkdir(parents=True)
    (package / "manifest.json").write_text(
        json.dumps({
            **_document(component_id, name),
            "version": "1.0.0",
        }),
        encoding="utf-8",
    )
    (package / "pins.json").write_text(
        json.dumps([{"name": "DATA", "type": "GPIO"}]),
        encoding="utf-8",
    )
    (package / "metadata.json").write_text(
        json.dumps({"tags": ["package-tag"]}),
        encoding="utf-8",
    )


def test_package_overrides_legacy(tmp_path):
    (tmp_path / "dht11.json").write_text(
        json.dumps(_document("dht11", "Legacy DHT11")), encoding="utf-8"
    )
    _package(tmp_path, "dht11")

    registry = ComponentRegistry()
    assert registry.load_components(tmp_path) == 1
    assert registry.require("dht11").name == "Package Sensor"


def test_pins_and_metadata_are_ignored_as_components(tmp_path):
    package = tmp_path / "controllers" / "esp32"
    package.mkdir(parents=True)
    (package / "pins.json").write_text(json.dumps(_document("pins", "Pins")), encoding="utf-8")
    (package / "metadata.json").write_text(json.dumps(_document("metadata", "Metadata")), encoding="utf-8")

    assert ComponentLoader().load(tmp_path) == []


def test_duplicate_ids_resolve_to_one_component(tmp_path):
    (tmp_path / "a.json").write_text(json.dumps(_document("same", "First")), encoding="utf-8")
    (tmp_path / "b.json").write_text(json.dumps(_document("same", "Second")), encoding="utf-8")

    registry = ComponentRegistry()
    assert registry.load_components(tmp_path) == 1
    assert len(registry.list_all()) == 1


def test_legacy_components_still_load(tmp_path):
    (tmp_path / "servo.json").write_text(
        json.dumps(_document("servo", "Legacy Servo")), encoding="utf-8"
    )

    registry = ComponentRegistry()
    assert registry.load_components(tmp_path) == 1
    assert registry.require("servo").name == "Legacy Servo"


def test_search_returns_package_components(tmp_path):
    _package(tmp_path, "dht11", "DHT11 Package")

    registry = ComponentRegistry()
    registry.load_components(tmp_path)
    results = registry.search("dht11")

    assert [result.component.component_id for result in results] == ["dht11"]
