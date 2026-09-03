"""Persistence for hybrid projects, device assignments, and simulation mappings."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional


class HybridStorage:
    """File-based persistence under ``data/hybrid/``."""

    def __init__(self, base_dir: Path | str = "data") -> None:
        self.base_dir = Path(base_dir) / "hybrid"
        self.projects_dir = self.base_dir / "projects"
        self.assignments_dir = self.base_dir / "assignments"
        self.mappings_dir = self.base_dir / "mappings"
        self.runs_dir = self.base_dir / "runs"

    def _ensure(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)

    def save_project(self, experiment_id: str, data: dict[str, Any]) -> Path:
        path = self.projects_dir / f"{experiment_id}.json"
        self._ensure(path)
        with path.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, sort_keys=True)
            fh.write("\n")
        return path

    def load_project(self, experiment_id: str) -> Optional[dict[str, Any]]:
        path = self.projects_dir / f"{experiment_id}.json"
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)

    def save_assignments(self, experiment_id: str, assignments: list[dict[str, Any]]) -> Path:
        path = self.assignments_dir / f"{experiment_id}.json"
        self._ensure(path)
        with path.open("w", encoding="utf-8") as fh:
            json.dump(assignments, fh, indent=2, sort_keys=True)
            fh.write("\n")
        return path

    def load_assignments(self, experiment_id: str) -> Optional[list[dict[str, Any]]]:
        path = self.assignments_dir / f"{experiment_id}.json"
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)

    def save_mappings(self, experiment_id: str, mappings: dict[str, Any]) -> Path:
        path = self.mappings_dir / f"{experiment_id}.json"
        self._ensure(path)
        with path.open("w", encoding="utf-8") as fh:
            json.dump(mappings, fh, indent=2, sort_keys=True)
            fh.write("\n")
        return path

    def load_mappings(self, experiment_id: str) -> Optional[dict[str, Any]]:
        path = self.mappings_dir / f"{experiment_id}.json"
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)

    def save_run(self, experiment_id: str, run_id: str, state: dict[str, Any]) -> Path:
        run_dir = self.runs_dir / experiment_id
        run_dir.mkdir(parents=True, exist_ok=True)
        path = run_dir / f"{run_id}.json"
        with path.open("w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=2, sort_keys=True)
            fh.write("\n")
        return path

    def list_runs(self, experiment_id: str) -> list[str]:
        run_dir = self.runs_dir / experiment_id
        if not run_dir.exists():
            return []
        return sorted(p.stem for p in run_dir.glob("*.json"))
