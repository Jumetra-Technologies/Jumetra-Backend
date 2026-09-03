"""Persistence for laboratory projects, circuits, and simulation runs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional


class LaboratoryStorage:
    """File-based persistence under ``data/laboratory/``."""

    def __init__(self, base_dir: Path | str = "data") -> None:
        self.base_dir = Path(base_dir) / "laboratory"
        self.projects_dir = self.base_dir / "projects"
        self.circuits_dir = self.base_dir / "circuits"
        self.runs_dir = self.base_dir / "runs"

    def _ensure(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)

    def save_project(self, laboratory_id: str, data: dict[str, Any]) -> Path:
        path = self.projects_dir / f"{laboratory_id}.json"
        self._ensure(path)
        with path.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, sort_keys=True)
            fh.write("\n")
        return path

    def load_project(self, laboratory_id: str) -> Optional[dict[str, Any]]:
        path = self.projects_dir / f"{laboratory_id}.json"
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)

    def save_circuit(self, laboratory_id: str, circuit: dict[str, Any]) -> Path:
        path = self.circuits_dir / f"{laboratory_id}.json"
        self._ensure(path)
        with path.open("w", encoding="utf-8") as fh:
            json.dump(circuit, fh, indent=2, sort_keys=True)
            fh.write("\n")
        return path

    def load_circuit(self, laboratory_id: str) -> Optional[dict[str, Any]]:
        path = self.circuits_dir / f"{laboratory_id}.json"
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)

    def save_run(self, laboratory_id: str, run_id: str, state: dict[str, Any]) -> Path:
        lab_dir = self.runs_dir / laboratory_id
        lab_dir.mkdir(parents=True, exist_ok=True)
        path = lab_dir / f"{run_id}.json"
        with path.open("w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=2, sort_keys=True)
            fh.write("\n")
        return path

    def list_runs(self, laboratory_id: str) -> list[str]:
        lab_dir = self.runs_dir / laboratory_id
        if not lab_dir.exists():
            return []
        return sorted(p.stem for p in lab_dir.glob("*.json"))
