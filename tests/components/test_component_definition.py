from engine.components.models import ComponentSpec
from engine.components.schema import ComponentDefinition, component_definition_from_spec


def test_definition_round_trips_component_spec():
    spec = ComponentSpec("dht11", "DHT11", "sensor", "temperature", tags=["humidity"])
    definition = component_definition_from_spec(spec)
    assert definition.component_id == "dht11"
    assert definition.to_spec().tags == ["humidity"]


def test_definition_requires_identity_fields():
    definition = ComponentDefinition.from_documents({"id": "led", "name": "LED", "category": "actuator"})
    assert definition.identity.id == "led"
    assert definition.identity.version == "1.0.0"