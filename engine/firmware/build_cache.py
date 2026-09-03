"""Build artifact cache."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Optional


class BuildCache:
    """Cache build results keyed by project content hash."""

    def __init__(self, data_dir: Path | str) -> None:
        self.root = Path(data_dir) / "firmware" / "build_cache"
        self.root.mkdir(parents=True, exist_ok=True)

    def content_hash(self, files: list[dict[str, str]], board_type: str) -> str:
        h = hashlib.sha256()
        h.update(board_type.encode())
        for f in sorted(files, key=lambda x: x.get("path", "")):
            h.update(f.get("path", "").encode())
            h.update(f.get("content", "").encode())
        return h.hexdigest()[:24]

    def get(self, key: str) -> Optional[dict[str, Any]]:
        path = self.root / f"{key}.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def put(self, key: str, result: dict[str, Any]) -> None:
        path = self.root / f"{key}.json"
        payload = {**result, "cached_at_ms": int(time.time() * 1000), "cache_key": key}
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def clear(self) -> int:
        n = 0
        for p in self.root.glob("*.json"):
            p.unlink(missing_ok=True)
            n += 1
        return n
