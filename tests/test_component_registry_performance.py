"""Regression guard for a large declarative component catalog."""
from __future__ import annotations
import time
from engine.component_registry import ComponentRegistry
from component_package_helpers import make_package

def test_registry_handles_thousand_packages_and_uses_cache(tmp_path, monkeypatch):
    for index in range(1000):
        make_package(tmp_path, f"sensor-{index}")
    started = time.perf_counter()
    registry = ComponentRegistry(tmp_path, use_cache=False)
    uncached = time.perf_counter() - started
    assert len(registry.list_all()) == 1000
    assert registry.search("sensor-999")[0].component_id == "sensor-999"

    monkeypatch.setattr(registry.discovery, "scan", lambda: (_ for _ in ()).throw(AssertionError("cache was not used")))
    started = time.perf_counter()
    assert registry.reload(use_cache=True) == 1000
    assert time.perf_counter() - started < uncached
