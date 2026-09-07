from __future__ import annotations

from engine.components import default_registry
from engine.components.paths import resolve_components_dir


def test_catalog_has_category_storage_and_migrated_components():
    root = resolve_components_dir()
    assert (root / "sensors").is_dir()
    assert (root / "actuators").is_dir()
    assert (root / "displays").is_dir()
    registry = default_registry()
    assert registry.get("dht11") is not None
    assert registry.get("bmp280") is not None


def test_component_id_and_path_traversal_are_rejected(tmp_path):
    outside = tmp_path / "secret.json"
    outside.write_text("{}", encoding="utf-8")
    registry = default_registry()
    assert registry.load_components(tmp_path / ".." / "secret.json") == 0