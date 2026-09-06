"""JSON Schema validation for declarative component packages."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from jsonschema import Draft202012Validator

class ComponentValidator:
    def __init__(self, schemas_dir: Path | str | None = None, engine_version: str = "1.0") -> None:
        self.schemas_dir = Path(schemas_dir) if schemas_dir else Path(__file__).resolve().parents[2] / "schemas"
        self.engine_version = engine_version
        self._schemas = {name: json.loads((self.schemas_dir / f"{name}.schema.json").read_text(encoding="utf-8")) for name in ("component", "manifest", "pins")}

    def validate(self, component: dict[str, Any], manifest: dict[str, Any], pins: Any) -> list[str]:
        errors: list[str] = []
        for label, payload in (("component", component), ("manifest", manifest), ("pins", pins)):
            errors.extend(f"{label}: {err.message}" for err in Draft202012Validator(self._schemas[label]).iter_errors(payload))
        if isinstance(manifest, dict) and manifest.get("engine_version") != self.engine_version:
            errors.append(f"manifest: unsupported engine_version {manifest.get('engine_version')!r}")
        if isinstance(component, dict) and component.get("pins") != "pins.json":
            errors.append("component: pins must reference pins.json")
        return errors
