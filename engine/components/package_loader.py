"""Loader for versioned component packages and legacy component documents."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import ComponentSpec
from .schema import ComponentDefinition
from .security import ComponentSecurityScanner, SecurityViolation
from .validator import ComponentValidator
from .versioning import ComponentVersion

logger = logging.getLogger("hhip.components")


@dataclass
class LoadedComponentPackage:
    definition: ComponentDefinition
    spec: ComponentSpec
    path: Path
    metadata: dict[str, Any]


class ComponentPackageLoader:
    """Discover package directories without executing package content."""

    def __init__(
        self,
        scanner: ComponentSecurityScanner | None = None,
        validator: ComponentValidator | None = None,
    ) -> None:
        self.scanner = scanner or ComponentSecurityScanner()
        self.validator = validator or ComponentValidator()

    def load(self, path: Path | str) -> list[LoadedComponentPackage]:
        root = Path(path).expanduser().resolve()
        if not root.is_dir():
            return []
        packages: list[LoadedComponentPackage] = []
        seen_versions: set[str] = set()
        for manifest_path in sorted(root.rglob("manifest.json")):
            if "examples" in manifest_path.relative_to(root).parts:
                continue
            package = manifest_path.parent
            try:
                self.scanner.validate_package(root, package)
                manifest = self.scanner.read_json(root, manifest_path)
                if not isinstance(manifest, dict):
                    raise SecurityViolation("manifest must be a JSON object")
                if not manifest.get("version"):
                    raise ValueError("missing required field: version")
                version = str(manifest["version"])
                ComponentVersion.parse(version)
                package_key = f"{manifest.get('id')}@{version}"
                if package_key in seen_versions:
                    raise ValueError(f"duplicate component package: {package_key}")
                pins = self._read_optional_json(root, package / "pins.json")
                metadata = self._read_optional_json(root, package / "metadata.json")
                firmware = self._read_optional_json(root, package / "firmware.json")
                pins_data = pins.get("pins", pins) if isinstance(pins, dict) else pins
                errors = self.validator.validate(
                    {**manifest, "pins": pins_data or manifest.get("pins", []), "interfaces": manifest.get("interfaces", ["GPIO"])},
                )
                if errors:
                    raise ValueError("; ".join(errors))
                definition = ComponentDefinition.from_documents(
                    manifest,
                    pins_document=pins_data,
                    metadata=metadata if isinstance(metadata, dict) else {},
                    firmware_document=firmware if isinstance(firmware, dict) else {},
                )
                packages.append(LoadedComponentPackage(definition, definition.to_spec(), package, metadata or {}))
                seen_versions.add(package_key)
            except (OSError, TypeError, ValueError, SecurityViolation) as exc:
                logger.warning("Skipping invalid component package %s: %s", package, exc)
        return packages

    def _read_optional_json(self, root: Path, path: Path) -> Any:
        if not path.exists():
            return {}
        return self.scanner.read_json(root, path)


def load_component_packages(path: Path | str = "data/components") -> list[LoadedComponentPackage]:
    return ComponentPackageLoader().load(path)