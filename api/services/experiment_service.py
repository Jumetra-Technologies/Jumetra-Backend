"""Experiment control service — platform lifecycle without sync algorithm changes."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from engine.events.dashboard_publisher import DashboardEventPublisher, DashboardEventType
from engine.experiments.session import ExperimentSession
from engine.storage.storage_manager import StorageManager


class ExperimentRunStatus(str, Enum):
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    COMPLETED = "completed"


@dataclass
class ManagedExperiment:
    session: ExperimentSession
    status: ExperimentRunStatus = ExperimentRunStatus.RUNNING
    progress: float = 0.0
    devices: list[str] = field(default_factory=list)
    strategy: str = "fixed"
    metadata: dict[str, Any] = field(default_factory=dict)
    started_at: int = field(default_factory=lambda: int(time.time() * 1000))
    paused_at: Optional[int] = None


class ExperimentService:
    """Manage experiment start/pause/stop and publish platform events."""

    def __init__(
        self,
        data_dir: Path | str,
        publisher: DashboardEventPublisher,
    ) -> None:
        self._data_dir = Path(data_dir)
        self._storage = StorageManager(self._data_dir)
        self._publisher = publisher
        self._experiments: dict[str, ManagedExperiment] = {}
        self._lock = threading.Lock()

    @property
    def active_count(self) -> int:
        with self._lock:
            return sum(
                1
                for m in self._experiments.values()
                if m.status in {ExperimentRunStatus.RUNNING, ExperimentRunStatus.PAUSED}
            )

    def start(
        self,
        *,
        name: str,
        devices: Optional[list[str]] = None,
        strategy: str = "fixed",
        duration_ms: Optional[int] = None,
        sync_interval_ms: Optional[int] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        device_list = list(devices or [])
        session = ExperimentSession(name=name)
        session.metadata.update(metadata or {})
        session.metadata["strategy"] = strategy
        session.metadata["active"] = True
        session.start(
            devices=device_list,
            duration_ms=duration_ms,
            sync_interval_ms=sync_interval_ms,
        )

        managed = ManagedExperiment(
            session=session,
            status=ExperimentRunStatus.RUNNING,
            devices=device_list,
            strategy=strategy,
            metadata=dict(session.metadata),
        )

        with self._lock:
            self._experiments[session.experiment_id] = managed

        for device_id in device_list:
            self._publisher.publish_device_connected(device_id, experiment_id=session.experiment_id)

        self._publisher.publish_sync_started(
            session.experiment_id,
            payload={"name": name, "strategy": strategy, "devices": device_list},
        )
        self._publisher.publish_sync_progress(
            session.experiment_id,
            progress=0.0,
            payload={"status": ExperimentRunStatus.RUNNING.value},
        )

        return self.status(session.experiment_id)

    def pause(self, experiment_id: str) -> dict[str, Any]:
        managed = self._require_managed(experiment_id)
        if managed.status != ExperimentRunStatus.RUNNING:
            raise ValueError(f"experiment {experiment_id} is not running")

        managed.status = ExperimentRunStatus.PAUSED
        managed.paused_at = int(time.time() * 1000)
        managed.session.metadata["active"] = False

        self._publisher.publish_sync_progress(
            experiment_id,
            progress=managed.progress,
            payload={"status": ExperimentRunStatus.PAUSED.value},
        )
        return self.status(experiment_id)

    def stop(self, experiment_id: str) -> dict[str, Any]:
        managed = self._require_managed(experiment_id)
        if managed.status == ExperimentRunStatus.COMPLETED:
            return self.status(experiment_id)

        if managed.session.is_active:
            managed.session.finish()
        managed.status = ExperimentRunStatus.COMPLETED
        managed.progress = 100.0
        managed.session.metadata["active"] = False

        export_path = self._storage.export_experiment(managed.session)

        self._publisher.publish_sync_completed(
            experiment_id,
            payload={"export_path": str(export_path)},
        )
        self._publisher.publish_experiment_completed(
            experiment_id,
            payload={
                "name": managed.session.name,
                "strategy": managed.strategy,
                "devices": managed.devices,
            },
        )

        for device_id in managed.devices:
            self._publisher.publish_device_disconnected(
                device_id, experiment_id=experiment_id, reason="experiment_completed"
            )

        return self.status(experiment_id)

    def status(self, experiment_id: str) -> dict[str, Any]:
        managed = self._require_managed(experiment_id)
        session = managed.session
        return {
            "experiment_id": session.experiment_id,
            "name": session.name,
            "status": managed.status.value,
            "strategy": managed.strategy,
            "devices": list(managed.devices),
            "progress": managed.progress,
            "start_time": session.start_time,
            "end_time": session.end_time,
            "elapsed_ms": session.elapsed_ms() if session.is_active else None,
            "event_count": len(session.events),
            "sync_measurement_count": len(session.sync_measurements),
            "metadata": dict(managed.metadata),
        }

    def update_progress(self, experiment_id: str, progress: float, **payload: Any) -> None:
        """Platform hook for external progress reporting (does not run sync)."""
        managed = self._require_managed(experiment_id)
        if managed.status != ExperimentRunStatus.RUNNING:
            return
        managed.progress = max(0.0, min(100.0, progress))
        self._publisher.publish_sync_progress(
            experiment_id,
            progress=managed.progress,
            payload=payload,
        )

    def publish_correction(self, experiment_id: str, device_id: str, **payload: Any) -> None:
        """Platform hook when a correction is observed elsewhere."""
        self._publisher.publish_correction_applied(experiment_id, device_id, **payload)

    def get_managed(self, experiment_id: str) -> Optional[ManagedExperiment]:
        with self._lock:
            return self._experiments.get(experiment_id)

    def _require_managed(self, experiment_id: str) -> ManagedExperiment:
        with self._lock:
            managed = self._experiments.get(experiment_id)
        if managed is None:
            raise KeyError(f"experiment not found: {experiment_id}")
        return managed
