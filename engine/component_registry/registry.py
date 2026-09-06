"""Public registry facade for dynamically discovered packages."""
from __future__ import annotations
from pathlib import Path
from .cache import RegistryCache
from .discovery import ComponentDiscovery
from .metadata import ComponentMetadata
from .search import ComponentSearchEngine

class ComponentRegistry:
    def __init__(self, components_dir: Path | str = "components", *, use_cache: bool = True) -> None:
        self.components_dir = Path(components_dir)
        self.discovery = ComponentDiscovery(self.components_dir)
        self.cache = RegistryCache(self.components_dir)
        self.search_engine = ComponentSearchEngine()
        self._components: dict[str, ComponentMetadata] = {}
        self.rejected: list[dict[str, str]] = []
        self.reload(use_cache=use_cache)

    def register(self, component: ComponentMetadata) -> None:
        if component.component_id in self._components: raise ValueError(f"duplicate component id: {component.component_id}")
        self._components[component.component_id] = component

    def get(self, component_id: str) -> ComponentMetadata | None: return self._components.get(component_id)
    def list_all(self) -> list[ComponentMetadata]: return sorted(self._components.values(), key=lambda c: c.name.lower())
    def list_categories(self) -> list[str]: return sorted({c.category for c in self._components.values()})
    def list_manufacturers(self) -> list[str]: return sorted({c.manufacturer for c in self._components.values()})
    def search(self, query: str = "", **filters: object) -> list[ComponentMetadata]: return self.search_engine.search(self.list_all(), query, **filters)  # type: ignore[arg-type]

    def reload(self, *, use_cache: bool = True) -> int:
        roots = [self.components_dir / item for item in ("official", "community", "marketplace")]
        cached = self.cache.load_cache() if use_cache and self.cache.is_fresh(roots) else None
        components = cached if cached is not None else self.discovery.scan()
        self._components = {}
        for component in components:
            if component.component_id not in self._components: self.register(component)
            else: self.rejected.append({"location": str(component.location), "reason": f"duplicate component id: {component.component_id}"})
        self.rejected = [*self.discovery.last_rejected, *self.rejected]
        if cached is None: self.cache.build_cache(self.list_all())
        return len(self._components)

    def statistics(self) -> dict[str, object]:
        return {"components": len(self._components), "categories": len(self.list_categories()), "manufacturers": len(self.list_manufacturers()), "rejected": len(self.rejected), "cache_path": str(self.cache.path)}
