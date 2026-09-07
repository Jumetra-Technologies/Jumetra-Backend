from engine.components import ComponentRegistry, ComponentSearchIndex
from engine.components.models import ComponentSpec


def test_search_indexes_metadata_and_compatibility():
    registry = ComponentRegistry()
    registry.register(ComponentSpec("esp32", "ESP32", "mcu", "WiFi controller", manufacturer="Espressif", interfaces=["wifi"], tags=["wifi", "controller"]))
    registry.register(ComponentSpec("dht11", "DHT11", "sensor", "temperature humidity", tags=["temperature", "humidity"]))
    assert ComponentSearchIndex(registry).search("humidity")[0]["component_id"] == "dht11"
    assert ComponentSearchIndex(registry).search("wifi controller")[0]["component_id"] == "esp32"