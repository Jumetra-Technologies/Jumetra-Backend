"""Crash recovery for unfinished correction transactions."""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Callable, Optional, TYPE_CHECKING

from ...protocol.reliability import WireReliabilityPolicy
from .state import TransactionState
from .storage import CorrectionTransactionStorage, UNFINISHED_STATES
from .transaction import CorrectionTransaction

if TYPE_CHECKING:
    from ..physical_bridge import PhysicalCorrectionBridge

logger = logging.getLogger("hhip.synchronization.transactions.recovery")

AdvanceFn = Callable[[int], None]


class RecoveryAction(str, Enum):
    """Recovery outcome for one transaction."""

    RESUMED_VERIFICATION = "RESUMED_VERIFICATION"
    CONTINUED_VERIFICATION = "CONTINUED_VERIFICATION"
    RETRIED_SEND = "RETRIED_SEND"
    FAILED_TIMEOUT = "FAILED_TIMEOUT"
    FAILED_INVALID = "FAILED_INVALID"
    NO_ACTION = "NO_ACTION"


@dataclass
class RecoveryResult:
    """Result of recovering one transaction."""

    transaction_id: str
    device_id: str
    previous_state: TransactionState
    action: RecoveryAction
    final_state: TransactionState
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["previous_state"] = self.previous_state.value
        data["final_state"] = self.final_state.value
        data["action"] = self.action.value
        return data


class TransactionRecovery:
    """Load and recover unfinished correction transactions on startup."""

    def __init__(
        self,
        bridge: "PhysicalCorrectionBridge",
        storage: CorrectionTransactionStorage,
        *,
        reliability: Optional[WireReliabilityPolicy] = None,
    ) -> None:
        self.bridge = bridge
        self.storage = storage
        self.reliability = reliability or WireReliabilityPolicy()

    def recover_on_startup(
        self,
        *,
        advance_clock: Optional[AdvanceFn] = None,
    ) -> list[RecoveryResult]:
        """Load unfinished transactions and attempt recovery."""
        self.bridge.load_persisted_transactions()
        results: list[RecoveryResult] = []
        for txn in self.bridge.txn_manager.list_unfinished():
            results.append(self.recover_transaction(txn, advance_clock=advance_clock))
        return results

    def recover_transaction(
        self,
        txn: CorrectionTransaction,
        *,
        advance_clock: Optional[AdvanceFn] = None,
    ) -> RecoveryResult:
        """Recover a single unfinished transaction based on its state."""
        previous = txn.state
        manager = self.bridge.txn_manager

        if txn.state == TransactionState.VERIFYING:
            final = self.bridge.continue_verification(txn, advance_clock=advance_clock)
            return RecoveryResult(
                transaction_id=txn.transaction_id,
                device_id=txn.device_id,
                previous_state=previous,
                action=RecoveryAction.RESUMED_VERIFICATION,
                final_state=final.state,
            )

        if txn.state == TransactionState.APPLIED:
            final = self.bridge.continue_verification(txn, advance_clock=advance_clock)
            return RecoveryResult(
                transaction_id=txn.transaction_id,
                device_id=txn.device_id,
                previous_state=previous,
                action=RecoveryAction.CONTINUED_VERIFICATION,
                final_state=final.state,
            )

        if txn.state == TransactionState.SENT:
            result = self.bridge.retry_or_fail_sent(txn)
            return RecoveryResult(
                transaction_id=txn.transaction_id,
                device_id=txn.device_id,
                previous_state=previous,
                action=result["action"],
                final_state=manager.get(txn.transaction_id).state,  # type: ignore[union-attr]
                reason=result.get("reason", ""),
            )

        if txn.state == TransactionState.CREATED:
            manager.fail(txn.transaction_id, "recovery: transaction never sent")
            self.bridge.health.record_failure()
            return RecoveryResult(
                transaction_id=txn.transaction_id,
                device_id=txn.device_id,
                previous_state=previous,
                action=RecoveryAction.FAILED_INVALID,
                final_state=TransactionState.FAILED,
                reason="transaction never sent",
            )

        return RecoveryResult(
            transaction_id=txn.transaction_id,
            device_id=txn.device_id,
            previous_state=previous,
            action=RecoveryAction.NO_ACTION,
            final_state=txn.state,
        )

    def list_recoverable(self) -> list[CorrectionTransaction]:
        return [
            txn
            for txn in self.storage.load_unfinished()
            if txn.state in UNFINISHED_STATES
        ]
