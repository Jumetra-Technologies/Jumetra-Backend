from __future__ import annotations

from engine.components.validator import ComponentValidator


def valid_document() -> dict:
    return {
        "id": "soil_sensor",
        "name": "Soil Sensor",
        "category": "sensor",
        "interfaces": ["GPIO"],
        "pins": [{"name": "DATA", "type": "GPIO"}],
        "voltage": {"min": 3.3, "max": 5},
    }


def test_missing_fields_fail():
    assert ComponentValidator().validate({})


def test_invalid_pin_and_voltage_fail():
    document = valid_document()
    document["pins"] = [{"name": "DATA", "type": "NOT_A_PIN"}]
    document["voltage"] = {"min": 5, "max": 3.3}
    errors = ComponentValidator().validate(document)
    assert any("invalid type" in error for error in errors)
    assert "invalid voltage range" in errors


def test_duplicate_and_invalid_ids_fail():
    validator = ComponentValidator()
    assert any("duplicate" in error for error in validator.validate(valid_document(), {"soil_sensor"}))
    assert any("invalid component id" in error for error in validator.validate({**valid_document(), "id": "../../hack"}))