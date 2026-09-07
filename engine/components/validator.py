"""Validation for untrusted external component JSON documents."""

from __future__ import annotations

import re
from typing import Any, Iterable

from .definitions import SUPPORTED_CATEGORIES, SUPPORTED_INTERFACES, SUPPORTED_PIN_TYPES

COMPONENT_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:[_-][a-z0-9]+)*$")
MAX_PINS = 200
MAX_JSON_DEPTH = 10
REQUIRED_FIELDS = ("id", "name", "category", "pins", "interfaces")


def json_depth(value: Any, current: int = 0) -> int:
    if isinstance(value, dict):
        children = value.values()
    elif isinstance(value, list):
        children = value
    else:
        return current
    return max((json_depth(child, current + 1) for child in children), default=current)


class ComponentValidator:
    """Validate the schema and safety limits of a component definition."""

    def validate(
        self,
        document: Any,
        seen_ids: Iterable[str] | None = None,
    ) -> list[str]:
        errors: list[str] = []
        if not isinstance(document, dict):
            return ["component definition must be a JSON object"]

        missing = [field for field in REQUIRED_FIELDS if field not in document]
        errors.extend(f"missing required field: {field}" for field in missing)
        if json_depth(document) > MAX_JSON_DEPTH:
            errors.append(f"JSON nesting exceeds {MAX_JSON_DEPTH} levels")

        component_id = document.get("id")
        if not isinstance(component_id, str) or not COMPONENT_ID_PATTERN.fullmatch(component_id):
            errors.append("invalid component id")
        elif seen_ids is not None and component_id in set(seen_ids):
            errors.append(f"duplicate component id: {component_id}")

        category = document.get("category")
        if not isinstance(category, str) or category.lower() not in SUPPORTED_CATEGORIES:
            errors.append(f"unsupported category: {category}")

        interfaces = document.get("interfaces")
        if not isinstance(interfaces, list) or not interfaces:
            errors.append("interfaces must be a non-empty list")
        else:
            for interface in interfaces:
                if not isinstance(interface, str) or interface.lower() not in SUPPORTED_INTERFACES:
                    errors.append(f"unsupported interface: {interface}")

        pins = document.get("pins")
        if not isinstance(pins, list):
            errors.append("pins must be a list")
        elif len(pins) > MAX_PINS:
            errors.append(f"pin count exceeds {MAX_PINS}")
        else:
            for index, pin in enumerate(pins):
                if not isinstance(pin, dict):
                    errors.append(f"pin {index} must be an object")
                    continue
                if not isinstance(pin.get("name"), str) or not pin["name"].strip():
                    errors.append(f"pin {index} name is required")
                pin_type = str(pin.get("type", "")).upper()
                if pin_type not in SUPPORTED_PIN_TYPES:
                    errors.append(f"pin {index} has invalid type: {pin.get('type')}")

        voltage = document.get("voltage")
        if voltage is not None:
            if not isinstance(voltage, dict):
                errors.append("voltage must be an object")
            else:
                minimum = voltage.get("min")
                maximum = voltage.get("max")
                if not isinstance(minimum, (int, float)) or not isinstance(maximum, (int, float)):
                    errors.append("voltage min and max must be numbers")
                elif minimum < 0 or maximum < 0 or minimum > maximum:
                    errors.append("invalid voltage range")
        return errors

    def validate_file(self, document: Any, seen_ids: Iterable[str] | None = None) -> list[str]:
        return self.validate(document, seen_ids)