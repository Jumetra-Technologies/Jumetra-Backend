from engine.components import ComponentRegistry
from engine.components.models import ComponentSpec
from engine.components.versioning import ComponentVersion, resolve_latest


def test_version_parser_and_latest():
    assert str(ComponentVersion.parse("2.0.0")) == "2.0.0"
    assert resolve_latest(["1.0.0", "2.0.0", "1.5.0"]) == "2.0.0"


def test_registry_supports_multiple_versions():
    registry = ComponentRegistry()
    registry.register(ComponentSpec("dht11", "DHT11", "sensor", "", version="1.0.0"))
    registry.register(ComponentSpec("dht11", "DHT11 v2", "sensor", "", version="2.0.0"))
    assert registry.get("dht11@1.0.0").name == "DHT11"
    assert registry.get("dht11@2.0.0").name == "DHT11 v2"
    assert registry.latest_version("dht11") == "2.0.0"