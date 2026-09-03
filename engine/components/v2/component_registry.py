"""Component Registry v2 — indexed ComponentDefinition packages."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from .component_definition import ComponentDefinition
from .package_loader import PackageLoader, resolve_packages_dir


class ComponentRegistryV2:
    def __init__(self, packages_dir: Optional[Path | str] = None) -> None:
        self.packages_dir = resolve_packages_dir(packages_dir)
        self._by_id: dict[str, ComponentDefinition] = {}
        self.reload()

    def reload(self) -> int:
        self._by_id.clear()
        loader = PackageLoader(self.packages_dir)
        for definition in loader.load_all():
            self._by_id[definition.id] = definition
        return len(self._by_id)

    def get(self, component_id: str) -> Optional[ComponentDefinition]:
        return self._by_id.get(component_id)

    def require(self, component_id: str) -> ComponentDefinition:
        comp = self.get(component_id)
        if comp is None:
            raise KeyError(f"component package not found: {component_id}")
        return comp

    def list_all(self) -> list[ComponentDefinition]:
        return sorted(self._by_id.values(), key=lambda c: c.name)

    def categories(self) -> list[str]:
        return sorted({c.category for c in self._by_id.values()})

    def search(
        self,
        query: str = "",
        *,
        category: Optional[str] = None,
        interface: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        q = query.strip().lower()
        results: list[tuple[float, ComponentDefinition]] = []
        for comp in self.list_all():
            if category:
                wanted = category.lower().rstrip("s")
                have = comp.category.lower().rstrip("s")
                if wanted != have and category.lower() not in {comp.category.lower(), comp.category.lower() + "s"}:
                    continue
            if interface:
                ifaces = {i.lower() for i in comp.interfaces}
                key = interface.lower()
                if key == "gpio":
                    if not ({"gpio", "digital"} & ifaces) and "gpio" not in ifaces:
                        # still allow if any pin is GPIO
                        if not any(p.type == "GPIO" for p in comp.pins):
                            continue
                elif key not in ifaces and interface.upper() not in {i.upper() for i in comp.interfaces}:
                    continue
            score = self._score(comp, q)
            if q and score <= 0:
                continue
            results.append((score if q else 1.0, comp))
        results.sort(key=lambda x: (-x[0], x[1].name))
        return [c.to_search_hit() for _, c in results[:limit]]

    @staticmethod
    def _score(comp: ComponentDefinition, query: str) -> float:
        if not query:
            return 1.0
        hay = " ".join(
            [
                comp.id,
                comp.name,
                comp.category,
                comp.manufacturer,
                comp.description,
                " ".join(comp.keywords),
                " ".join(comp.aliases),
                " ".join(comp.interfaces),
            ]
        ).lower()
        score = 0.0
        if query == comp.id or query.replace(" ", "-") == comp.id:
            score += 12
        if query in comp.name.lower():
            score += 10
        if any(query == a.lower() or query in a.lower() for a in comp.aliases):
            score += 11
        if any(query == k.lower() or query in k.lower() for k in comp.keywords):
            score += 8
        if query in hay:
            score += 2
        for tok in query.split():
            if tok in hay:
                score += 1
        return score


_default_registry: Optional[ComponentRegistryV2] = None


def default_registry_v2() -> ComponentRegistryV2:
    global _default_registry
    if _default_registry is None:
        _default_registry = ComponentRegistryV2()
    return _default_registry
