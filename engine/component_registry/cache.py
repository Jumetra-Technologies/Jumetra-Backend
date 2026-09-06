"""On-disk cache for already validated component metadata."""
from __future__ import annotations
import json
import time
from pathlib import Path
from .metadata import ComponentMetadata

class RegistryCache:
    def __init__(self, components_dir: Path | str = "components") -> None:
        self.path = Path(components_dir) / "cache" / "registry.json"

    def build_cache(self, components: list[ComponentMetadata]) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"created_at": time.time(), "components": [c.to_dict() for c in components]}, indent=2), encoding="utf-8")
        return self.path

    def load_cache(self) -> list[ComponentMetadata] | None:
        if not self.path.exists(): return None
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return [ComponentMetadata.from_dict(raw) for raw in data.get("components", [])]
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
            return None

    def is_fresh(self, roots: list[Path]) -> bool:
        if not self.path.exists(): return False
        cache_time = self.path.stat().st_mtime
        return all(path.stat().st_mtime <= cache_time for root in roots if root.exists() for path in root.rglob("*") if path.is_file() and path != self.path)

    def invalidate_cache(self) -> None:
        if self.path.exists(): self.path.unlink()
