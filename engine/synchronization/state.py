"""Synchronization state machine — control lifecycle (no correction)."""

from __future__ import annotations

from enum import Enum
from typing import Mapping, Set


class SyncState(str, Enum):
    """Synchronization control states for a device session."""

    UNKNOWN = "UNKNOWN"
    MEASURING = "MEASURING"
    CALIBRATED = "CALIBRATED"
    MONITORING = "MONITORING"
    CORRECTION_READY = "CORRECTION_READY"
    FAILED = "FAILED"


# Valid state transitions (Sprint 13 control framework).
VALID_TRANSITIONS: Mapping[SyncState, Set[SyncState]] = {
    SyncState.UNKNOWN: {SyncState.MEASURING, SyncState.FAILED},
    SyncState.MEASURING: {
        SyncState.CALIBRATED,
        SyncState.MONITORING,
        SyncState.FAILED,
    },
    SyncState.CALIBRATED: {SyncState.MONITORING, SyncState.MEASURING, SyncState.FAILED},
    SyncState.MONITORING: {
        SyncState.MEASURING,
        SyncState.CORRECTION_READY,
        SyncState.CALIBRATED,
        SyncState.FAILED,
    },
    SyncState.CORRECTION_READY: {
        SyncState.MONITORING,
        SyncState.MEASURING,
        SyncState.FAILED,
    },
    SyncState.FAILED: {SyncState.MEASURING, SyncState.UNKNOWN},
}


class InvalidSyncTransition(Exception):
    """Raised when a state transition is not permitted."""


class SyncStateMachine:
    """Enforces valid synchronization control state transitions."""

    def __init__(self, initial: SyncState = SyncState.UNKNOWN) -> None:
        self._state = initial
        self._history: list[SyncState] = [initial]

    @property
    def state(self) -> SyncState:
        return self._state

    @property
    def history(self) -> list[SyncState]:
        return list(self._history)

    def can_transition(self, target: SyncState) -> bool:
        return target in VALID_TRANSITIONS.get(self._state, set())

    def transition(self, target: SyncState) -> SyncState:
        if not self.can_transition(target):
            raise InvalidSyncTransition(
                f"invalid transition {self._state.value} → {target.value}"
            )
        self._state = target
        self._history.append(target)
        return self._state

    def reset(self, *, to: SyncState = SyncState.UNKNOWN) -> SyncState:
        self._state = to
        self._history.append(to)
        return self._state
