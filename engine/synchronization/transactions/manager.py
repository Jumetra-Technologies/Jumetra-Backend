"""CorrectionTransactionManager — physical correction lifecycle."""

from __future__ import annotations

import logging
from typing import Any, Mapping, Optional

from ...protocol.correction import SyncCorrectionRequest, SyncCorrectionResponse
from ...time.timestamp_service import TimestampService, get_timestamp_service
from ..adjuster.physical_limits import PhysicalCorrectionLimits
from .state import (
    InvalidTransactionTransition,
    TransactionState,
    VALID_TRANSACTION_TRANSITIONS,
)
from .storage import CorrectionTransactionStorage, UNFINISHED_STATES
from .transaction import CorrectionTransaction

logger = logging.getLogger("hhip.synchronization.transactions")


class UnknownCorrectionTransaction(KeyError):
    """Raised when a correction transaction id is not registered."""


class CorrectionTransactionManager:
    """Manage correction transaction state transitions (physical-safe)."""

    def __init__(
        self,
        *,
        limits: Optional[PhysicalCorrectionLimits] = None,
        timestamp_service: Optional[TimestampService] = None,
        storage: Optional[CorrectionTransactionStorage] = None,
    ) -> None:
        self.limits = limits or PhysicalCorrectionLimits()
        self._ts = timestamp_service or get_timestamp_service()
        self._storage = storage
        self._transactions: dict[str, CorrectionTransaction] = {}
        self._by_device: dict[str, list[str]] = {}
        self._last_correction_time: dict[str, int] = {}
        self._accumulated: dict[str, float] = {}

    @property
    def accumulated_by_device(self) -> dict[str, float]:
        return dict(self._accumulated)

    def get(self, transaction_id: str) -> Optional[CorrectionTransaction]:
        return self._transactions.get(transaction_id)

    def list_for_device(self, device_id: str) -> list[CorrectionTransaction]:
        ids = self._by_device.get(device_id, [])
        return [self._transactions[tid] for tid in ids if tid in self._transactions]

    def list_unfinished(self) -> list[CorrectionTransaction]:
        return [
            txn
            for txn in self._transactions.values()
            if txn.state in UNFINISHED_STATES
        ]

    def list_all(self) -> list[CorrectionTransaction]:
        return list(self._transactions.values())

    def restore(
        self,
        transactions: Mapping[str, CorrectionTransaction],
        *,
        accumulated_by_device: Optional[Mapping[str, float]] = None,
        last_correction_time: Optional[Mapping[str, int]] = None,
    ) -> None:
        """Load transactions from persistent storage."""
        self._transactions = dict(transactions)
        self._by_device.clear()
        for txn in self._transactions.values():
            self._by_device.setdefault(txn.device_id, []).append(txn.transaction_id)
        if accumulated_by_device is not None:
            self._accumulated = dict(accumulated_by_device)
        if last_correction_time is not None:
            self._last_correction_time = dict(last_correction_time)

    def create(
        self,
        device_id: str,
        correction_step: float,
        *,
        offset_before: Optional[float] = None,
        timestamp: Optional[int] = None,
    ) -> CorrectionTransaction:
        """Create a new correction transaction after safety checks."""
        device_id = str(device_id)
        step = float(correction_step)
        now = int(timestamp if timestamp is not None else self._ts.now())

        reason = self.limits.check_step(step)
        if reason:
            raise ValueError(reason)

        reason = self.limits.check_cooldown(
            self._last_correction_time.get(device_id, 0), now
        )
        if reason:
            raise ValueError(reason)

        projected = self._accumulated.get(device_id, 0.0) + abs(step)
        reason = self.limits.check_accumulated(projected)
        if reason:
            raise ValueError(reason)

        request = SyncCorrectionRequest.create(
            device_id, step, now, correlation_id=f"corr-{device_id}-{now}"
        )
        txn = CorrectionTransaction(
            transaction_id=request.transaction_id,
            device_id=device_id,
            correction_step=step,
            timestamp=now,
            state=TransactionState.CREATED,
            offset_before=offset_before,
            metadata={"request": request.to_dict(), "retry_count": 0},
        )
        self._register(txn)
        logger.info(
            "[TXN] CREATED %s device=%s step=%.2f",
            txn.transaction_id,
            device_id,
            step,
        )
        return txn

    def build_request(self, transaction_id: str) -> SyncCorrectionRequest:
        txn = self._require(transaction_id)
        data = txn.metadata.get("request") or {}
        return SyncCorrectionRequest.from_dict(
            {
                **data,
                "transaction_id": txn.transaction_id,
                "device_id": txn.device_id,
                "correction_step": txn.correction_step,
                "timestamp": txn.timestamp,
            }
        )

    def mark_sent(self, transaction_id: str, *, sent_at: Optional[int] = None) -> CorrectionTransaction:
        txn = self._transition(transaction_id, TransactionState.SENT)
        txn.metadata["wire_sent_at"] = int(sent_at if sent_at is not None else self._ts.now())
        self._persist(txn)
        return txn

    def mark_applied(
        self,
        transaction_id: str,
        response: SyncCorrectionResponse | Mapping[str, Any],
    ) -> CorrectionTransaction:
        existing = self._require(transaction_id)
        if existing.state in {
            TransactionState.APPLIED,
            TransactionState.VERIFYING,
            TransactionState.COMPLETED,
            TransactionState.ROLLED_BACK,
        }:
            logger.info("[TXN] duplicate response ignored for %s (state=%s)", transaction_id, existing.state.value)
            return existing

        txn = self._transition(transaction_id, TransactionState.APPLIED)
        if hasattr(response, "to_dict"):
            payload = response.to_dict()
        else:
            payload = dict(response)
        txn.metadata["response"] = payload
        txn.accumulated_correction = float(
            payload.get("accumulated_correction", txn.accumulated_correction)
        )
        self._accumulated[txn.device_id] = txn.accumulated_correction
        self._last_correction_time[txn.device_id] = self._ts.now()
        self._persist(txn)
        return txn

    def start_verification(self, transaction_id: str) -> CorrectionTransaction:
        txn = self._transition(transaction_id, TransactionState.VERIFYING)
        self._persist(txn)
        return txn

    def complete_verification(
        self,
        transaction_id: str,
        *,
        offset_after: float,
        improvement: float,
        verified: bool = True,
    ) -> CorrectionTransaction:
        txn = self._transition(transaction_id, TransactionState.COMPLETED)
        txn.offset_after = float(offset_after)
        txn.improvement = float(improvement)
        txn.verified = verified
        self._persist(txn)
        return txn

    def fail(self, transaction_id: str, reason: str) -> CorrectionTransaction:
        txn = self._transition(transaction_id, TransactionState.FAILED)
        txn.failure_reason = reason
        self._persist(txn)
        return txn

    def rollback(self, transaction_id: str, *, reason: str = "") -> CorrectionTransaction:
        txn = self._transition(transaction_id, TransactionState.ROLLED_BACK)
        if reason:
            txn.failure_reason = reason
        self._accumulated[txn.device_id] = max(
            0.0, self._accumulated.get(txn.device_id, 0.0) - abs(txn.correction_step)
        )
        self._persist(txn)
        return txn

    def increment_retry(self, transaction_id: str) -> int:
        txn = self._require(transaction_id)
        count = int(txn.metadata.get("retry_count", 0)) + 1
        txn.metadata["retry_count"] = count
        self._persist(txn)
        return count

    def update_wire_sent(self, transaction_id: str, *, sent_at: Optional[int] = None) -> CorrectionTransaction:
        """Refresh wire timestamp for an in-flight SENT transaction (retry resend)."""
        txn = self._require(transaction_id)
        if txn.state != TransactionState.SENT:
            raise InvalidTransactionTransition(
                f"cannot update wire_sent for state {txn.state.value}"
            )
        txn.metadata["wire_sent_at"] = int(sent_at if sent_at is not None else self._ts.now())
        self._persist(txn)
        return txn

    def _register(self, txn: CorrectionTransaction) -> None:
        self._transactions[txn.transaction_id] = txn
        self._by_device.setdefault(txn.device_id, []).append(txn.transaction_id)
        self._persist(txn)

    def _transition(
        self, transaction_id: str, target: TransactionState
    ) -> CorrectionTransaction:
        txn = self._require(transaction_id)
        allowed = VALID_TRANSACTION_TRANSITIONS.get(txn.state, set())
        if target not in allowed:
            raise InvalidTransactionTransition(
                f"invalid transaction transition {txn.state.value} → {target.value}"
            )
        txn.state = target
        logger.info("[TXN] %s → %s", transaction_id, target.value)
        return txn

    def _persist(self, txn: Optional[CorrectionTransaction] = None) -> None:
        if self._storage is None:
            return
        if txn is not None:
            self._storage.save_transaction(txn)
        self._storage.save_all(
            self._transactions,
            accumulated_by_device=self._accumulated,
            last_correction_time=self._last_correction_time,
        )

    def _require(self, transaction_id: str) -> CorrectionTransaction:
        txn = self._transactions.get(transaction_id)
        if txn is None:
            raise UnknownCorrectionTransaction(f"unknown transaction: {transaction_id}")
        return txn
