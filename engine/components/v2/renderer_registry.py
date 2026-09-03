"""Renderer registry — maps component ids to SVG content / paths."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .component_registry import ComponentRegistryV2, default_registry_v2


class RendererRegistry:
    def __init__(self, registry: Optional[ComponentRegistryV2] = None) -> None:
        self.registry = registry or default_registry_v2()

    def get_svg(self, component_id: str) -> Optional[str]:
        comp = self.registry.get(component_id)
        if not comp:
            return None
        if comp.renderer_svg:
            return comp.renderer_svg
        path = comp.renderer_path()
        if path and path.exists():
            return path.read_text(encoding="utf-8")
        return None

    def get_path(self, component_id: str) -> Optional[Path]:
        comp = self.registry.get(component_id)
        return comp.renderer_path() if comp else None

    def has_renderer(self, component_id: str) -> bool:
        return self.get_svg(component_id) is not None

    def list_renderers(self) -> list[str]:
        return [c.id for c in self.registry.list_all() if self.has_renderer(c.id)]
