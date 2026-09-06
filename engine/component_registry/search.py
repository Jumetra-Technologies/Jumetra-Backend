"""Metadata-only component search."""
from __future__ import annotations
from typing import Iterable
from .metadata import ComponentMetadata

class ComponentSearchEngine:
    def search(self, components: Iterable[ComponentMetadata], query: str = "", *, category: str | None = None, manufacturer: str | None = None, interface: str | None = None, voltage: float | None = None) -> list[ComponentMetadata]:
        q = query.strip().lower()
        hits: list[tuple[int, ComponentMetadata]] = []
        for item in components:
            if category and item.category.lower() != category.lower(): continue
            if manufacturer and item.manufacturer.lower() != manufacturer.lower(): continue
            if interface and interface.lower() not in {x.lower() for x in item.interfaces}: continue
            if voltage is not None and float(voltage) not in item.voltage: continue
            terms = " ".join([item.component_id, item.name, item.category, item.manufacturer, *item.keywords, *item.interfaces]).lower()
            if q and q not in terms: continue
            score = (10 if q and q in item.name.lower() else 0) + (8 if q in {x.lower() for x in item.keywords} else 0) + (1 if q else 0)
            hits.append((score, item))
        return [item for _, item in sorted(hits, key=lambda pair: (-pair[0], pair[1].name.lower()))]
