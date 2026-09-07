"""Metadata-aware search over the component registry."""

from __future__ import annotations

from .models import ComponentSpec
from .registry import ComponentRegistry


class ComponentSearchIndex:
    """Search names, metadata, interfaces, and compatibility declarations."""

    def __init__(self, registry: ComponentRegistry) -> None:
        self.registry = registry

    def search(
        self,
        query: str = "",
        *,
        category: str | None = None,
        manufacturer: str | None = None,
        compatibility: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        tokens = [token for token in query.lower().replace(",", " ").split() if token]
        results: list[dict] = []
        for component in self.registry.list_all():
            if category and component.category.lower() not in {category.lower(), category.lower().rstrip("s")}: 
                continue
            if manufacturer and manufacturer.lower() not in component.manufacturer.lower():
                continue
            document = self.registry_document(component)
            compatible = [str(item).lower() for item in document.get("compatible_controllers", [])]
            if compatibility and compatibility.lower() not in compatible:
                continue
            fields = {
                "id": component.component_id,
                "name": component.name,
                "category": component.category,
                "manufacturer": component.manufacturer,
                "description": component.description,
                "interfaces": " ".join(component.interfaces),
                "tags": " ".join(component.tags),
                "keywords": " ".join(document.get("keywords", [])),
                "compatibility": " ".join(compatible),
            }
            haystack = " ".join(fields.values()).lower()
            score = 1.0 if not tokens else sum(self._token_score(token, fields, haystack) for token in tokens)
            if tokens and score <= 0:
                continue
            results.append({
                "component_id": component.component_id,
                "name": component.name,
                "category": component.category,
                "manufacturer": component.manufacturer,
                "version": component.version,
                "score": score,
            })
        return sorted(results, key=lambda item: (-item["score"], item["name"]))[:limit]

    def registry_document(self, component: ComponentSpec) -> dict:
        index = getattr(self.registry, "_metadata_index", None)
        if index is None:
            from .search.index import ComponentIndex

            index = ComponentIndex(self.registry.components_dir)
            self.registry._metadata_index = index
        return index.get(component.component_id) or {}

    @staticmethod
    def _token_score(token: str, fields: dict[str, str], haystack: str) -> float:
        if token not in haystack:
            return 0.0
        score = 1.0
        for field in ("id", "name"):
            if token in fields[field].lower():
                score += 3.0
        if token in fields["tags"].lower() or token in fields["keywords"].lower():
            score += 2.0
        return score