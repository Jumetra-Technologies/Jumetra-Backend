"""Full-text component search engine."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from .filters import SearchFilters
from .index import ComponentIndex


class ComponentSearchEngine:
    """
    Professional catalog search:

    - full text over name, aliases, category, manufacturer, description,
      interfaces, keywords, compatible controllers
    - structured filters (category / interface / voltage / controller)
    """

    def __init__(self, index: Optional[ComponentIndex] = None, *, components_dir: Path | str | None = None) -> None:
        self.index = index or ComponentIndex(components_dir)

    def search(
        self,
        query: str = "",
        *,
        filters: Optional[SearchFilters] = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        filters = filters or SearchFilters()
        q = query.strip().lower()
        tokens = [t for t in q.replace(",", " ").split() if t]
        results: list[dict[str, Any]] = []

        for doc in self.index.all():
            if not filters.matches(doc):
                continue
            score = self._score(doc, q, tokens)
            if tokens and score <= 0:
                continue
            item = self.index.to_explorer_item(doc)
            item["score"] = score if tokens else 1.0
            results.append(item)

        results.sort(key=lambda r: (-float(r.get("score") or 0), str(r.get("name") or "")))
        return results[:limit]

    def get(self, component_id: str) -> Optional[dict[str, Any]]:
        doc = self.index.get(component_id)
        return self.index.to_explorer_item(doc) if doc else None

    def list_categories(self) -> list[str]:
        return sorted({str(d.get("category") or "") for d in self.index.all() if d.get("category")})

    def _score(self, doc: dict[str, Any], query: str, tokens: list[str]) -> float:
        if not tokens:
            return 1.0
        hay = self.index.haystack(str(doc.get("id") or ""))
        name = str(doc.get("name") or "").lower()
        cid = str(doc.get("id") or "").lower()
        aliases = [str(a).lower() for a in (doc.get("aliases") or [])]
        keywords = [str(k).lower() for k in (doc.get("keywords") or [])]
        score = 0.0

        if query and query in cid:
            score += 12
        if query and query in name:
            score += 10
        for a in aliases:
            if query == a or query in a:
                score += 11
                break
        for k in keywords:
            if query == k or query in k:
                score += 8
                break

        for tok in tokens:
            if tok in cid:
                score += 5
            if tok in name:
                score += 4
            if any(tok in a or a in tok for a in aliases):
                score += 5
            if tok in keywords:
                score += 3
            if tok in hay:
                score += 1
        return score
