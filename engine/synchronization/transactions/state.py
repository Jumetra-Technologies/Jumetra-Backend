"""Correction transaction state and models."""

from __future__ import annotations

from enum import Enum


class TransactionState(str, Enum):
    """Physical correction transaction lifecycle."""

    CREATED = "CREATED"
    SENT = "SENT"
    APPLIED = "APPLIED"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    ROLLED_BACK = "ROLLED_BACK"


VALID_TRANSACTION_TRANSITIONS: dict[TransactionState, set[TransactionState]] = {
    TransactionState.CREATED: {TransactionState.SENT, TransactionState.FAILED},
    TransactionState.SENT: {
        TransactionState.APPLIED,
        TransactionState.FAILED,
        TransactionState.ROLLED_BACK,
    },
    TransactionState.APPLIED: {
        TransactionState.VERIFYING,
        TransactionState.FAILED,
        TransactionState.ROLLED_BACK,
    },
    TransactionState.VERIFYING: {
        TransactionState.COMPLETED,
        TransactionState.FAILED,
        TransactionState.ROLLED_BACK,
    },
    TransactionState.COMPLETED: set(),
    TransactionState.FAILED: {TransactionState.ROLLED_BACK, TransactionState.CREATED},
    TransactionState.ROLLED_BACK: set(),
}


class InvalidTransactionTransition(Exception):
    """Raised when a transaction state change is not permitted."""
