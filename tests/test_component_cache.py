from engine.component_registry import ComponentRegistry
from component_package_helpers import make_package

def test_cache_create_load_and_invalidate(tmp_path):
    make_package(tmp_path)
    registry = ComponentRegistry(tmp_path, use_cache=False)
    assert registry.cache.path.exists()
    assert registry.cache.load_cache()[0].component_id == "dht11"
    registry.cache.invalidate_cache()
    assert registry.cache.load_cache() is None

def test_cache_reduces_discovery_work(tmp_path, monkeypatch):
    make_package(tmp_path)
    ComponentRegistry(tmp_path, use_cache=False)
    registry = ComponentRegistry(tmp_path, use_cache=False)
    monkeypatch.setattr(registry.discovery, "scan", lambda: (_ for _ in ()).throw(AssertionError("scan should not run")))
    assert registry.reload(use_cache=True) == 1
