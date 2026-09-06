from engine.component_registry import ComponentRegistry
from component_package_helpers import make_package

def test_registry_retrieves_and_reloads(tmp_path):
    make_package(tmp_path, "dht11")
    registry = ComponentRegistry(tmp_path, use_cache=False)
    assert registry.get("dht11").manufacturer == "Aosong"
    make_package(tmp_path, "dht22")
    assert registry.reload(use_cache=False) == 2
    assert {c.component_id for c in registry.list_all()} == {"dht11", "dht22"}

def test_registry_lists_metadata_dimensions(tmp_path):
    make_package(tmp_path, manufacturer="Aosong")
    registry = ComponentRegistry(tmp_path, use_cache=False)
    assert registry.list_categories() == ["sensor"]
    assert registry.list_manufacturers() == ["Aosong"]
    assert registry.statistics()["components"] == 1
