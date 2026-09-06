from engine.component_registry import ComponentValidator

def test_validator_requires_component_fields_and_valid_pins():
    validator = ComponentValidator()
    errors = validator.validate({}, {}, [])
    assert errors

def test_validator_accepts_minimal_valid_documents():
    validator = ComponentValidator()
    component = {"id":"led", "name":"LED", "category":"actuator", "manufacturer":"HHIP", "interfaces":["GPIO"], "voltage":[3.3], "behavior":"digital_output", "renderer":"renderer.svg", "pins":"pins.json", "keywords":["light"]}
    manifest = {"package":"community.led", "version":"1.0.0", "author":"HHIP", "license":"MIT", "engine_version":"1.0", "trust_level":"community"}
    assert validator.validate(component, manifest, [{"name":"IN", "type":"GPIO"}]) == []
