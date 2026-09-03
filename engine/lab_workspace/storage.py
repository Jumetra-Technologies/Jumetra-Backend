"""Persistence for engineering laboratory workspaces."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional


class LabWorkspaceStorage:
    """File-based persistence under ``data/lab_workspace/``."""

    def __init__(self, base_dir: Path | str = "data") -> None:
        self.base_dir = Path(base_dir) / "lab_workspace"
        self.sessions_dir = self.base_dir / "sessions"

    def _ensure(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)

    def save(self, workspace_id: str, data: dict[str, Any]) -> Path:
        path = self.sessions_dir / f"{workspace_id}.json"
        self._ensure(path)
        with path.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, sort_keys=True)
            fh.write("\n")
        return path

    def load(self, workspace_id: str) -> Optional[dict[str, Any]]:
        path = self.sessions_dir / f"{workspace_id}.json"
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)

    def list_ids(self) -> list[str]:
        if not self.sessions_dir.exists():
            return []
        return sorted(p.stem for p in self.sessions_dir.glob("*.json"))
