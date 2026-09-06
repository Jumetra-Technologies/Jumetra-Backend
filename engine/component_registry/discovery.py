"""Filesystem discovery for official, community and marketplace packages."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from .checksum import ChecksumVerifier
from .manifest import ComponentManifest
from .metadata import ComponentMetadata
from .security import ComponentSecurityManager
from .validator import ComponentValidator

class ComponentDiscovery:
    def __init__(self, components_dir: Path | str = "components", *, validator: ComponentValidator | None = None, security: ComponentSecurityManager | None = None) -> None:
        self.components_dir = Path(components_dir)
        self.validator = validator or ComponentValidator()
        self.security = security or ComponentSecurityManager()
        self.last_rejected: list[dict[str, str]] = []

    def scan(self) -> list[ComponentMetadata]:
        self.last_rejected = []
        found: list[ComponentMetadata] = []
        for source in ("official", "community", "marketplace"):
            root = self.components_dir / source
            if not root.exists():
                continue
            for component_file in sorted(root.rglob("component.json")):
                package = component_file.parent
                try:
                    metadata = self._load(package, source)
                except (OSError, ValueError, json.JSONDecodeError) as exc:
                    self.last_rejected.append({"location": str(package), "reason": str(exc)})
                    continue
                found.append(metadata)
        return found

    def _load(self, package: Path, source: str) -> ComponentMetadata:
        manifest_path, pins_path = package / "manifest.json", package / "pins.json"
        if not manifest_path.exists() or not pins_path.exists():
            raise ValueError("component package requires manifest.json and pins.json")
        component = json.loads((package / "component.json").read_text(encoding="utf-8"))
        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        pins = json.loads(pins_path.read_text(encoding="utf-8"))
        errors = self.validator.validate(component, manifest_data, pins)
        if errors:
            raise ValueError("; ".join(errors))
        renderer = package / str(component["renderer"])
        if not renderer.is_file():
            raise ValueError(f"renderer not found: {component['renderer']}")
        trusted, trust_level, reason = self.security.verify(package, source, str(manifest_data["trust_level"]))
        if not trusted:
            raise ValueError(reason)
        manifest = ComponentManifest.from_dict(manifest_data)
        return ComponentMetadata(component_id=str(component["id"]), name=str(component["name"]), category=str(component["category"]), manufacturer=str(component["manufacturer"]), interfaces=[str(v) for v in component["interfaces"]], voltage=[float(v) for v in component["voltage"]], behavior=str(component["behavior"]), renderer=str(component["renderer"]), pins=list(pins), keywords=[str(v) for v in component["keywords"]], manifest=manifest, location=package.resolve(), checksum=ChecksumVerifier.calculate(package), source=source, trusted=True, extras={"trust_level": trust_level})
