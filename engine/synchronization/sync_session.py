"""SyncSession — per-device synchronization control session (no correction)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Optional

from .calibration import ClockCalibrationReport
from .policy import CorrectionDecision, CorrectionPolicy
from .quality import SyncQuality
from .result import SynchronizationResult
from .state import SyncState, SyncStateMachine


@dataclass
class SyncSession:
    """Control session tracking sync state, quality, and calibration for one device."""

    device_id: str
    state: SyncState = SyncState.UNKNOWN
    last_sync_time: Optional[int] = None
    quality: Optional[dict[str, Any]] = None
    calibration: Optional[dict[str, Any]] = None
    last_decision: Optional[dict[str, Any]] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    _state_machine: SyncStateMachine = field(default_factory=SyncStateMachine, repr=False)

    def __post_init__(self) -> None:
        if self.state != SyncState.UNKNOWN:
            self._state_machine = SyncStateMachine(initial=self.state)

    def to_dict(self) -> dict[str, Any]:
        return {
            "device_id": self.device_id,
            "state": self.state.value,
            "last_sync_time": self.last_sync_time,
            "quality": self.quality,
            "calibration": self.calibration,
            "last_decision": self.last_decision,
            "metadata": dict(self.metadata),
            "state_history": [s.value for s in self._state_machine.history],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SyncSession":
        state = SyncState(str(data.get("state", SyncState.UNKNOWN.value)))
        session = cls(
            device_id=str(data["device_id"]),
            state=state,
            last_sync_time=data.get("last_sync_time"),
            quality=dict(data["quality"]) if isinstance(data.get("quality"), Mapping) else None,
            calibration=(
                dict(data["calibration"])
                if isinstance(data.get("calibration"), Mapping)
                else None
            ),
            last_decision=(
                dict(data["last_decision"])
                if isinstance(data.get("last_decision"), Mapping)
                else None
            ),
            metadata=dict(data.get("metadata") or {}),
        )
        return session

    def transition_to(self, target: SyncState) -> SyncState:
        """Move to ``target`` if the transition is valid."""
        self.state = self._state_machine.transition(target)
        return self.state

    def start_measurement(self) -> SyncState:
        """Begin a measurement cycle."""
        return self.transition_to(SyncState.MEASURING)

    def begin(self) -> SyncState:
        """Start session lifecycle from UNKNOWN."""
        if self.state == SyncState.UNKNOWN:
            return self.start_measurement()
        return self.state

    def record_sync_result(self, result: SynchronizationResult | Mapping[str, Any]) -> None:
        """Record a synchronization result and update last sync time."""
        if hasattr(result, "to_dict"):
            record = result.to_dict()
            self.last_sync_time = int(getattr(result, "timestamp"))
        else:
            record = dict(result)
            ts = record.get("timestamp")
            self.last_sync_time = int(ts) if ts is not None else self.last_sync_time
        self.metadata["last_sync_result"] = record

    def record_quality(self, quality: SyncQuality | Mapping[str, Any]) -> None:
        """Attach quality metrics to the session."""
        self.quality = quality.to_dict() if hasattr(quality, "to_dict") else dict(quality)

    def record_calibration(self, report: ClockCalibrationReport | Mapping[str, Any]) -> None:
        """Attach calibration report and transition to CALIBRATED when valid."""
        self.calibration = report.to_dict() if hasattr(report, "to_dict") else dict(report)
        if self.state in (SyncState.MEASURING, SyncState.MONITORING):
            self.transition_to(SyncState.CALIBRATED)

    def enter_monitoring(self) -> SyncState:
        """Move to ongoing monitoring after calibration."""
        if self.state == SyncState.CALIBRATED:
            return self.transition_to(SyncState.MONITORING)
        if self.state == SyncState.CORRECTION_READY:
            return self.transition_to(SyncState.MONITORING)
        return self.state

    def evaluate_policy(
        self,
        policy: CorrectionPolicy,
        *,
        offset: float,
        drift: float,
        confidence: float,
        uncertainty: float = 0.0,
    ) -> CorrectionDecision:
        """Run correction policy and update session state (decision only)."""
        decision = policy.evaluate(
            offset, drift, confidence, uncertainty=uncertainty
        )
        self.last_decision = decision.to_dict()

        if decision.action.value == "reject":
            self.transition_to(SyncState.FAILED)
        elif decision.action.value == "ready" and self.state == SyncState.MONITORING:
            self.transition_to(SyncState.CORRECTION_READY)
        elif decision.action.value in ("defer", "monitor") and self.state == SyncState.FAILED:
            pass  # remain failed until explicit recovery

        return decision

    def mark_failed(self, reason: str = "") -> SyncState:
        """Transition to FAILED."""
        if reason:
            self.metadata["failure_reason"] = reason
        if self.state != SyncState.FAILED:
            if self._state_machine.can_transition(SyncState.FAILED):
                return self.transition_to(SyncState.FAILED)
        return self.state

    def recover(self) -> SyncState:
        """Attempt recovery from FAILED → MEASURING."""
        if self.state == SyncState.FAILED:
            return self.transition_to(SyncState.MEASURING)
        return self.state
