import json

from engine.components.package_loader import ComponentPackageLoader


def write_package(root, version="1.0.0"):
    package = root / "sensors" / "dht11"
    package.mkdir(parents=True)
    (package / "manifest.json").write_text(json.dumps({
        "id": "dht11", "name": "DHT11", "version": version,
        "category": "sensor", "interfaces": ["GPIO"]
    }), encoding="utf-8")
    (package / "pins.json").write_text(json.dumps([{"name": "DATA", "type": "GPIO"}]), encoding="utf-8")
    (package / "metadata.json").write_text(json.dumps({"tags": ["temperature", "humidity"]}), encoding="utf-8")
    return package


def test_load_component_package(tmp_path):
    package = ComponentPackageLoader().load(tmp_path)
    assert package == []
    write_package(tmp_path)
    loaded = ComponentPackageLoader().load(tmp_path)
    assert len(loaded) == 1
    assert loaded[0].spec.component_id == "dht11"
    assert "humidity" in loaded[0].spec.tags


def test_malformed_package_is_ignored(tmp_path):
    package = tmp_path / "sensors" / "broken"
    package.mkdir(parents=True)
    (package / "manifest.json").write_text("{", encoding="utf-8")
    assert ComponentPackageLoader().load(tmp_path) == []