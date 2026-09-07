from __future__ import annotations

import json

from engine.components import ComponentRegistry


def _document(component_id: str = "bmp280") -> dict:
    return {
        "id": component_id,
        "name": "BMP280",
        "category": "sensor",
        "interfaces": ["I2C"],
        "pins": [{"name": "SDA", "type": "I2C"}],
        "voltage": {"min": 3.3, "max": 3.3},
    }


def test_loader_scans_nested_json_and_searches(tmp_path):
    target = tmp_path / "sensors" / "bmp280.json"
    target.parent.mkdir()
    target.write_text(json.dumps(_document()), encoding="utf-8")

    registry = ComponentRegistry()
    assert registry.load_components(tmp_path) == 1
    assert registry.get("bmp280") is not None
    assert registry.search("bmp280")


def test_loader_ignores_invalid_json(tmp_path):
    (tmp_path / "sensors").mkdir()
    (tmp_path / "sensors" / "broken.json").write_text("{", encoding="utf-8")
    (tmp_path / "sensors" / "valid.json").write_text(json.dumps(_document()), encoding="utf-8")

    registry = ComponentRegistry()
    assert registry.load_components(tmp_path) == 1


def test_loader_rejects_duplicate_ids(tmp_path):
    (tmp_path / "sensors").mkdir()
    for name in ("a.json", "b.json"):
        (tmp_path / "sensors" / name).write_text(json.dumps(_document()), encoding="utf-8")

    registry = ComponentRegistry()
    assert registry.load_components(tmp_path) == 1