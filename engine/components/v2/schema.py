"""JSON schema helpers / constants for Component Engine v2 manifests."""

from __future__ import annotations

from typing import Any

MANIFEST_REQUIRED_FIELDS = ("id", "name", "category", "pins")

MANIFEST_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": list(MANIFEST_REQUIRED_FIELDS),
    "properties": {
        "id": {"type": "string"},
        "name": {"type": "string"},
        "category": {"type": "string"},
        "manufacturer": {"type": "string"},
        "description": {"type": "string"},
        "visual": {
            "type": "object",
            "properties": {
                "renderer": {"type": "string"},
                "width": {"type": "number"},
                "height": {"type": "number"},
            },
        },
        "pins": {"type": "array"},
        "interfaces": {"type": "array"},
        "simulation": {"type": "object"},
        "hardware": {"type": "object"},
        "keywords": {"type": "array"},
        "aliases": {"type": "array"},
    },
}


def validate_manifest_shape(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for field in MANIFEST_REQUIRED_FIELDS:
        if field not in data:
            errors.append(f"missing required field: {field}")
            continue
        if field != "pins" and data[field] in (None, ""):
            errors.append(f"missing required field: {field}")
    if "pins" in data and not isinstance(data["pins"], list):
        errors.append("pins must be a list")
    return errors
