from engine.component_registry import ComponentDiscovery
from component_package_helpers import make_package

def test_discovery_finds_valid_component(tmp_path):
    make_package(tmp_path, "temp-sensor")
    components = ComponentDiscovery(tmp_path).scan()
    assert [c.component_id for c in components] == ["temp-sensor"]

def test_discovery_rejects_invalid_package(tmp_path):
    make_package(tmp_path, valid=False)
    discovery = ComponentDiscovery(tmp_path)
    assert discovery.scan() == []
    assert discovery.last_rejected
