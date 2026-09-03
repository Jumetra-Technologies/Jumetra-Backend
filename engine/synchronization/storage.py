"""SynchronizationStorage — JSON persistence for sync control state."""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any, Mapping, Optional, Union

from ..time.clock_model import ClockModel
from .calibration import ClockCalibrationReport
from .policy import CorrectionDecision
from .scheduler import ScheduledDevice
from .sync_session import SyncSession

logger = logging.getLogger("hhip.synchronization.storage")

PathLike = Union[str, Path]


class SynchronizationStorage:
    """Persist SyncSession, ClockModel, calibration, and decision audit logs.

    Layout::

        {base_dir}/
          state.json              # sessions, clock_models, schedules
          sync_decisions.jsonl    # audit log
    """

    def __init__(self, base_dir: PathLike = "data/synchronization") -> None:
        self.base_dir = Path(base_dir)
        self.state_path = self.base_dir / "state.json"
        self.decisions_path = self.base_dir / "sync_decisions.jsonl"
        self._lock = threading.Lock()

    def _ensure_dir(self) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save_session(self, session: SyncSession) -> None:
        """Merge one session into persisted state."""
        state = self.load_state()
        state.setdefault("sessions", {})[session.device_id] = session.to_dict()
        self.save_state(state)

    def save_clock_model(self, model: ClockModel) -> None:
        state = self.load_state()
        state.setdefault("clock_models", {})[model.clock_id] = model.to_dict()
        self.save_state(state)

    def save_calibration(
        self, device_id: str, report: ClockCalibrationReport | Mapping[str, Any]
    ) -> None:
        data = report.to_dict() if hasattr(report, "to_dict") else dict(report)
        state = self.load_state()
        state.setdefault("calibrations", {})[device_id] = data
        self.save_state(state)

    def save_schedule(self, schedule: ScheduledDevice) -> None:
        state = self.load_state()
        state.setdefault("schedules", {})[schedule.device_id] = schedule.to_dict()
        self.save_state(state)

    def append_decision(
        self,
        decision: CorrectionDecision | Mapping[str, Any],
        *,
        device_id: str,
        timestamp: int,
        offset: Optional[float] = None,
        drift: Optional[float] = None,
        confidence: Optional[float] = None,
    ) -> Path:
        """Append one row to ``sync_decisions.jsonl``."""
        if hasattr(decision, "to_dict"):
            record = decision.to_dict()
        else:
            record = dict(decision)
        record.setdefault("timestamp", timestamp)
        record.setdefault("device_id", device_id)
        if offset is not None:
            record.setdefault("offset", offset)
        if drift is not None:
            record.setdefault("drift", drift)
        if confidence is not None:
            record.setdefault("confidence", confidence)
        return self._append_jsonl(self.decisions_path, record)

    def append_audit(
        self,
        *,
        timestamp: int,
        device_id: str,
        decision: str,
        offset: float,
        drift: float,
        confidence: float,
        **extra: Any,
    ) -> Path:
        """Convenience audit entry matching sprint field requirements."""
        record = {
            "timestamp": timestamp,
            "device_id": device_id,
            "decision": decision,
            "offset": offset,
            "drift": drift,
            "confidence": confidence,
            **extra,
        }
        return self._append_jsonl(self.decisions_path, record)

    def append_correction_event(self, event: str, **fields: Any) -> Path:
        """Append a correction lifecycle event to ``sync_decisions.jsonl``."""
        record = {"event": event, **fields}
        return self._append_jsonl(self.decisions_path, record)

    def save_state(self, state: Mapping[str, Any]) -> Path:
        """Write the full synchronization state snapshot."""
        with self._lock:
            self._ensure_dir()
            with self.state_path.open("w", encoding="utf-8") as fh:
                json.dump(dict(state), fh, indent=2, sort_keys=True)
                fh.write("\n")
        logger.debug("[SYNC STORAGE] Saved state → %s", self.state_path)
        return self.state_path

    def load_state(self) -> dict[str, Any]:
        """Load state snapshot or return empty structure."""
        if not self.state_path.exists():
            return {
                "sessions": {},
                "clock_models": {},
                "calibrations": {},
                "schedules": {},
                "sync_profiles": {},
            }
        with self.state_path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            return {
                "sessions": {},
                "clock_models": {},
                "calibrations": {},
                "schedules": {},
                "sync_profiles": {},
            }
        data.setdefault("sessions", {})
        data.setdefault("clock_models", {})
        data.setdefault("calibrations", {})
        data.setdefault("schedules", {})
        data.setdefault("sync_profiles", {})
        return data

    def load_sessions(self) -> dict[str, SyncSession]:
        return {
            did: SyncSession.from_dict(raw)
            for did, raw in self.load_state().get("sessions", {}).items()
        }

    def load_clock_models(self) -> dict[str, ClockModel]:
        return {
            cid: ClockModel.from_dict(raw)
            for cid, raw in self.load_state().get("clock_models", {}).items()
        }

    def load_calibrations(self) -> dict[str, dict[str, Any]]:
        return dict(self.load_state().get("calibrations", {}))

    def load_schedules(self) -> dict[str, ScheduledDevice]:
        return {
            did: ScheduledDevice.from_dict(raw)
            for did, raw in self.load_state().get("schedules", {}).items()
        }

    def save_sync_profiles(self, profiles: Mapping[str, Mapping[str, Any]]) -> Path:
        state = self.load_state()
        state["sync_profiles"] = {str(k): dict(v) for k, v in profiles.items()}
        return self.save_state(state)

    def load_sync_profiles(self) -> dict[str, dict[str, Any]]:
        return dict(self.load_state().get("sync_profiles", {}))

    def load_decisions(self) -> list[dict[str, Any]]:
        if not self.decisions_path.exists():
            return []
        lines = self.decisions_path.read_text(encoding="utf-8").strip().splitlines()
        return [json.loads(line) for line in lines if line.strip()]

    def save_all(
        self,
        *,
        sessions: Mapping[str, SyncSession],
        clock_models: Mapping[str, ClockModel],
        schedules: Mapping[str, ScheduledDevice],
        calibrations: Optional[Mapping[str, Mapping[str, Any]]] = None,
    ) -> Path:
        """Persist a full coordinator snapshot."""
        state = {
            "sessions": {did: s.to_dict() for did, s in sessions.items()},
            "clock_models": {cid: m.to_dict() for cid, m in clock_models.items()},
            "calibrations": dict(calibrations or {}),
            "schedules": {did: sch.to_dict() for did, sch in schedules.items()},
        }
        return self.save_state(state)

    def _append_jsonl(self, path: Path, record: Mapping[str, Any]) -> Path:
        line = json.dumps(dict(record), separators=(",", ":"), sort_keys=False)
        with self._lock:
            self._ensure_dir()
            with path.open("a", encoding="utf-8") as fh:
                fh.write(line)
                fh.write("\n")
        return path
