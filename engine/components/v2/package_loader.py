"""Load component packages from data/component_packages/."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from engine.components.paths import project_root

from .component_definition import ComponentDefinition

logger = logging.getLogger("hhip.components.v2")


def resolve_packages_dir(explicit: Optional[Path | str] = None) -> Path:
    if explicit is not None:
        path = Path(explicit).expanduser().resolve()
        if path.is_dir():
            return path
    root = project_root()
    candidates = [
        root / "data" / "component_packages",
        root.parent / "data" / "component_packages",
        Path.cwd() / "hhip" / "data" / "component_packages",
        Path.cwd() / "data" / "component_packages",
    ]
    for c in candidates:
        resolved = c.resolve()
        if resolved.is_dir():
            return resolved
    fallback = (root / "data" / "component_packages").resolve()
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


class PackageLoader:
    """Discover and load component package folders."""

    def __init__(self, packages_dir: Optional[Path | str] = None) -> None:
        self.packages_dir = resolve_packages_dir(packages_dir)

    def discover(self) -> list[Path]:
        if not self.packages_dir.exists():
            return []
        return sorted(
            p for p in self.packages_dir.iterdir() if p.is_dir() and (p / "manifest.json").exists()
        )

    def load_package(self, package_path: Path) -> ComponentDefinition:
        manifest_path = package_path / "manifest.json"
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        datasheet = ""
        ds_path = package_path / "datasheet.md"
        if ds_path.exists():
            datasheet = ds_path.read_text(encoding="utf-8")
        renderer_svg = ""
        visual = data.get("visual") or {}
        renderer_name = str(visual.get("renderer") or "renderer.svg")
        renderer_path = package_path / renderer_name
        if renderer_path.exists():
            renderer_svg = renderer_path.read_text(encoding="utf-8")
        definition = ComponentDefinition.from_manifest(
            data,
            package_path=package_path,
            datasheet_md=datasheet,
            renderer_svg=renderer_svg,
        )
        errors = definition.validate()
        if errors:
            raise ValueError(f"{package_path.name}: {'; '.join(errors)}")
        return definition

    def load_all(self) -> list[ComponentDefinition]:
        loaded: list[ComponentDefinition] = []
        for path in self.discover():
            try:
                loaded.append(self.load_package(path))
            except (OSError, json.JSONDecodeError, ValueError) as exc:
                logger.warning("Failed to load package %s: %s", path, exc)
        logger.info("Loaded component packages: %s from %s", len(loaded), self.packages_dir)
        print(f"Loaded component packages: {len(loaded)}", flush=True)
        return loaded
