"""Centralized file storage for the HHIP engine.

No other module should write files directly. Phase 1.4.1 uses append-only
JSONL for events and metrics, and a single JSON snapshot for device state.
Sprint 7 adds experiment export under ``data/experiments/``.

Layout::

    data/
      events/events.jsonl
      metrics/metrics.jsonl
      snapshots/state.json
      experiments/EXP001/
        events.jsonl
        metrics.jsonl
        summary.json
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any, Mapping, Optional, Union

logger = logging.getLogger("hhip.storage.manager")

PathLike = Union[str, os.PathLike]


class StorageManager:
    """Append-oriented JSON/JSONL storage backend."""

    def __init__(self, base_dir: PathLike = "data") -> None:
        """Create a storage manager rooted at ``base_dir``."""
        self.base_dir = Path(base_dir)
        self.events_path = self.base_dir / "events" / "events.jsonl"
        self.metrics_path = self.base_dir / "metrics" / "metrics.jsonl"
        self.snapshot_path = self.base_dir / "snapshots" / "state.json"
        self.experiments_dir = self.base_dir / "experiments"
        self._lock = threading.Lock()

    def _ensure_parent(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)

    def _append_jsonl(self, path: Path, record: Mapping[str, Any]) -> None:
        line = json.dumps(dict(record), separators=(",", ":"), sort_keys=False)
        with self._lock:
            self._ensure_parent(path)
            with path.open("a", encoding="utf-8") as fh:
                fh.write(line)
                fh.write("\n")

    def save_event(self, event: Mapping[str, Any]) -> Path:
        """Append one event record to ``events/events.jsonl``."""
        record = event.to_dict() if hasattr(event, "to_dict") else dict(event)
        self._append_jsonl(self.events_path, record)
        logger.debug("[STORAGE] Saved event %s", record.get("event_id", "?"))
        return self.events_path

    def save_metric(self, metric: Mapping[str, Any]) -> Path:
        """Append one metric record to ``metrics/metrics.jsonl``."""
        self._append_jsonl(self.metrics_path, dict(metric))
        logger.debug("[STORAGE] Saved metric")
        return self.metrics_path

    def save_snapshot(self, state: Mapping[str, Any]) -> Path:
        """Overwrite ``snapshots/state.json`` with the latest state map."""
        with self._lock:
            self._ensure_parent(self.snapshot_path)
            with self.snapshot_path.open("w", encoding="utf-8") as fh:
                json.dump(dict(state), fh, indent=2, sort_keys=True)
                fh.write("\n")
        logger.debug("[STORAGE] Saved state snapshot (%d keys)", len(state))
        return self.snapshot_path

    def load_snapshot(self) -> Optional[dict[str, Any]]:
        """Load the last state snapshot, or ``None`` if it does not exist."""
        if not self.snapshot_path.exists():
            return None
        with self._lock:
            with self.snapshot_path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
        if not isinstance(data, dict):
            raise ValueError(f"snapshot at {self.snapshot_path} is not a JSON object")
        return data

    def experiment_path(self, experiment_id: str) -> Path:
        """Return ``data/experiments/<experiment_id>/``."""
        return self.experiments_dir / experiment_id

    def export_experiment(self, session: Any) -> Path:
        """Export an ExperimentSession under ``data/experiments/EXP###/``."""
        return session.export(base_dir=self.experiments_dir)
