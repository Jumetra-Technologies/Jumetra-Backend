"""Resolve package, versioned, and legacy component candidates."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from .versioning import ComponentVersion


class ComponentResolver:
    """Select the highest-priority definition for each component ID."""

    def resolve(
        self,
        packages: Iterable[Any],
        legacy: Iterable[Any],
    ) -> list[Any]:
        candidates: dict[str, tuple[int, ComponentVersion | None, Any]] = {}
        for package in packages:
            component = getattr(package, "spec", package)
            self._consider(candidates, component.component_id, 3, component.version, package)
        for component in legacy:
            priority = 2 if self._is_versioned(component.version) else 1
            self._consider(candidates, component.component_id, priority, component.version, component)
        return [candidate[2] for candidate in candidates.values()]

    @staticmethod
    def _is_versioned(version: str) -> bool:
        return str(version) not in {"", "1.0.0"}

    @staticmethod
    def _consider(
        candidates: dict[str, tuple[int, ComponentVersion | None, Any]],
        component_id: str,
        priority: int,
        version: str,
        candidate: Any,
    ) -> None:
        try:
            parsed_version = ComponentVersion.parse(version)
        except ValueError:
            parsed_version = None
        current = candidates.get(component_id)
        if current is None or (priority, parsed_version or ComponentVersion(0, 0, 0)) > (
            current[0], current[1] or ComponentVersion(0, 0, 0)
        ):
            candidates[component_id] = (priority, parsed_version, candidate)
