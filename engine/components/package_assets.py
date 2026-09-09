"""Secure, lazy discovery of files belonging to component packages.

This module deliberately deals only in paths. It does not open, parse, or
decode any discovered asset.
"""

from __future__ import annotations

from pathlib import Path
import re
from typing import TypedDict

from .paths import resolve_components_dir


_COMPONENT_ID = re.compile(r"^[A-Za-z0-9]+(?:[._-][A-Za-z0-9]+)*(?:@[0-9]+(?:\.[0-9]+){0,2})?$")
_SAFE_FILENAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_FIRMWARE_SUFFIXES = frozenset({".ino", ".cpp", ".c", ".py"})


class AssetMetadata(TypedDict):
    """Metadata returned for one discovered asset."""

    kind: str
    path: Path


class PackageAssets:
    """Locate package assets without loading their contents.

    ``components_root`` may point at ``data/components`` or a temporary test
    catalog. Package roots are indexed lazily and cached for the lifetime of
    this object; individual asset directories are never scanned until their
    corresponding accessor is called.
    """

    def __init__(self, components_root: Path | str | None = None) -> None:
        self.components_root = self._resolved_directory(
            Path(components_root).expanduser() if components_root is not None else resolve_components_dir()
        )
        self._package_roots: dict[str, Path | None] | None = None

    def get_board_svg(self, component_id: str) -> Path | None:
        """Return the package board SVG, if it is a valid regular file."""
        return self._named_asset(component_id, "assets", "board.svg")

    def get_breadboard_svg(self, component_id: str) -> Path | None:
        """Return the package breadboard SVG, if it is a valid regular file."""
        return self._named_asset(component_id, "assets", "breadboard.svg")

    def get_schematic_svg(self, component_id: str) -> Path | None:
        """Return the package schematic SVG, if it is a valid regular file."""
        return self._named_asset(component_id, "assets", "schematic.svg")

    def get_icon(self, component_id: str) -> Path | None:
        """Return the package icon, if it is a valid regular file."""
        return self._named_asset(component_id, "assets", "icon.png")

    def get_thumbnail(self, component_id: str) -> Path | None:
        """Return the package thumbnail, if it is a valid regular file."""
        return self._named_asset(component_id, "assets", "thumbnail.png")

    def get_datasheet(self, component_id: str) -> Path | None:
        """Return the first valid PDF in the package datasheets directory."""
        return self._first_matching_file(component_id, "datasheets", {".pdf"})

    def get_examples(self, component_id: str) -> Path | None:
        """Return the examples directory when it is a valid package directory."""
        return self._directory_asset(component_id, "examples")

    def get_firmware_templates(self, component_id: str) -> Path | None:
        """Return the first valid firmware source file in the package."""
        return self._first_matching_file(component_id, "firmware", _FIRMWARE_SUFFIXES)

    def get_library_metadata(self, component_id: str) -> Path | None:
        """Return the first valid JSON library metadata file in the package."""
        return self._first_matching_file(component_id, "libraries", {".json"})

    def list_assets(self, component_id: str) -> list[AssetMetadata]:
        """Return discovered asset paths and their categories.

        The result contains paths only; no asset content is read. Missing or
        invalid packages produce an empty list.
        """
        package = self._package_root(component_id)
        if package is None:
            return []

        assets: list[AssetMetadata] = []
        for relative_root, kind, suffixes in (
            ("assets", "asset", None),
            ("datasheets", "datasheet", {".pdf"}),
            ("firmware", "firmware", _FIRMWARE_SUFFIXES),
            ("libraries", "library", {".json"}),
        ):
            directory = self._safe_child(package, relative_root)
            if directory is None or not directory.is_dir():
                continue
            for path in sorted(directory.iterdir()):
                if self._valid_file(path, package) and (suffixes is None or path.suffix.lower() in suffixes):
                    assets.append({"kind": kind, "path": path})

        examples = self._directory_asset(component_id, "examples")
        if examples is not None:
            assets.append({"kind": "examples", "path": examples})
        return assets

    def _named_asset(self, component_id: str, directory: str, filename: str) -> Path | None:
        if not _SAFE_FILENAME.fullmatch(filename):
            return None
        package = self._package_root(component_id)
        return self._safe_child(package, directory, filename) if package is not None else None

    def _directory_asset(self, component_id: str, directory: str) -> Path | None:
        package = self._package_root(component_id)
        candidate = self._safe_child(package, directory) if package is not None else None
        return candidate if candidate is not None and candidate.is_dir() else None

    def _first_matching_file(self, component_id: str, directory: str, suffixes: set[str] | frozenset[str]) -> Path | None:
        package = self._package_root(component_id)
        candidate = self._safe_child(package, directory) if package is not None else None
        if candidate is None or not candidate.is_dir():
            return None
        for path in sorted(candidate.iterdir()):
            if self._valid_file(path) and path.suffix.lower() in suffixes:
                return path
        return None

    def _package_root(self, component_id: str) -> Path | None:
        if not isinstance(component_id, str) or not _COMPONENT_ID.fullmatch(component_id):
            return None
        if self._package_roots is None:
            self._package_roots = {}
            if self.components_root.is_dir():
                for manifest in self.components_root.rglob("manifest.json"):
                    package = manifest.parent
                    if self._valid_package(package):
                        self._package_roots.setdefault(package.name, package)
        return self._package_roots.get(component_id)

    def _safe_child(self, package: Path | None, *parts: str) -> Path | None:
        if package is None or any(not part or part in {".", ".."} or not _SAFE_FILENAME.fullmatch(part) for part in parts):
            return None
        candidate = package.joinpath(*parts)
        if not self._inside(package, candidate):
            return None
        return candidate if self._valid_file(candidate) or candidate.is_dir() else None

    def _valid_package(self, package: Path) -> bool:
        manifest = package / "manifest.json"
        return self._inside(self.components_root, package) and self._inside(package, manifest) and manifest.is_file()

    def _valid_file(self, path: Path, package: Path | None = None) -> bool:
        root = package or self.components_root
        return _SAFE_FILENAME.fullmatch(path.name) is not None and self._inside(root, path) and path.is_file()

    @staticmethod
    def _resolved_directory(path: Path) -> Path:
        try:
            return path.resolve()
        except OSError:
            return Path()

    @staticmethod
    def _inside(root: Path, candidate: Path) -> bool:
        try:
            candidate.resolve().relative_to(root.resolve())
            return True
        except (OSError, ValueError):
            return False