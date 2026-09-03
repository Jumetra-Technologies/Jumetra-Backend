"""Physical correction bridge — wire transactions to devices."""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional, Union

from ..protocol.correction import SyncCorrectionResponse
from ..protocol.correction_wire import build_wire_correction_request
from ..protocol.reliability import WireReliabilityConfig, WireReliabilityPolicy
from ..time.timestamp_service import TimestampService, get_timestamp_service
from .adjuster.mode import CorrectionMode
from .adjuster.physical_limits import PhysicalCorrectionLimits
from .adjuster.safe_adjuster import SafeClockAdjuster
from .health_monitor import CorrectionHealthMonitor, CorrectionHealthReport
from .manager import SynchronizationManager
from .physical_verification import PhysicalVerificationLoop
from .state import SyncState
from .storage import SynchronizationStorage
from .sync_session import SyncSession
from .transactions.manager import CorrectionTransactionManager, UnknownCorrectionTransaction
from .transactions.recovery import RecoveryAction, RecoveryResult, TransactionRecovery
from .transactions.state import TransactionState
from .transactions.storage import CorrectionTransactionStorage
from .transactions.transaction import CorrectionTransaction

logger = logging.getLogger("hhip.synchronization.physical_bridge")

WireSendCallback = Callable[[dict[str, Any]], None]
AdvanceFn = Callable[[int], None]
SimulateResponse = Union[
    SyncCorrectionResponse,
    dict[str, Any],
    Callable[[CorrectionTransaction], SyncCorrectionResponse | dict[str, Any]],
]


class PhysicalCorrectionBridge:
    """Coordinate physical correction transactions with safety boundaries."""

    def __init__(
        self,
        sync_manager: SynchronizationManager,
        *,
        send_callback: Optional[WireSendCallback] = None,
        storage: Optional[SynchronizationStorage] = None,
        txn_storage: Optional[CorrectionTransactionStorage] = None,
        limits: Optional[PhysicalCorrectionLimits] = None,
        adjuster: Optional[SafeClockAdjuster] = None,
        reliability: Optional[WireReliabilityPolicy] = None,
        timestamp_service: Optional[TimestampService] = None,
    ) -> None:
        self.sync_manager = sync_manager
        self.send = send_callback
        self.storage = storage
        self.limits = limits or PhysicalCorrectionLimits()
        self._ts = timestamp_service or get_timestamp_service()
        self.reliability = reliability or WireReliabilityPolicy()
        self.txn_storage = txn_storage or (
            CorrectionTransactionStorage(storage.base_dir)
            if storage is not None
            else CorrectionTransactionStorage()
        )
        self.txn_manager = CorrectionTransactionManager(
            limits=self.limits,
            timestamp_service=self._ts,
            storage=self.txn_storage,
        )
        self.adjuster = adjuster or SafeClockAdjuster(
            mode=CorrectionMode.STEP,
            max_step_ms=self.limits.max_step_ms,
            storage=storage,
            timestamp_service=self._ts,
        )
        self.verifier = PhysicalVerificationLoop(
            sync_manager, self.txn_manager, limits=self.limits
        )
        self.health = CorrectionHealthMonitor()
        self.recovery = TransactionRecovery(self, self.txn_storage, reliability=self.reliability)
        self._sequence = 0

    def load_persisted_transactions(self) -> int:
        """Restore transactions from JSON storage."""
        accumulated, last_time = self.txn_storage.load_bookkeeping()
        self.txn_manager.restore(
            self.txn_storage.load_all(),
            accumulated_by_device=accumulated,
            last_correction_time=last_time,
        )
        count = len(self.txn_manager.list_unfinished())
        if count:
            logger.info("[PHYS BRIDGE] Loaded %d unfinished transaction(s)", count)
        return count

    def recover_on_startup(self, *, advance_clock: Optional[AdvanceFn] = None) -> list[RecoveryResult]:
        """Load and recover unfinished transactions after crash/restart."""
        return self.recovery.recover_on_startup(advance_clock=advance_clock)

    def health_report(self) -> CorrectionHealthReport:
        return self.health.report()

    def execute_correction(
        self,
        session: SyncSession,
        *,
        offset: float,
        drift: float = 0.0,
        confidence: float = 0.0,
        advance_clock: Optional[AdvanceFn] = None,
        simulate_response: Optional[SimulateResponse] = None,
    ) -> CorrectionTransaction:
        """Full physical correction lifecycle for one bounded step."""
        device_id = session.device_id

        if session.state != SyncState.CORRECTION_READY:
            raise ValueError(f"session must be CORRECTION_READY, got {session.state.value}")

        estimate = self.adjuster.estimate_correction(
            device_id, offset, session, drift=drift, confidence=confidence
        )
        if estimate.rejected or not estimate.allowed:
            raise ValueError(estimate.reason or "correction estimate rejected")

        txn = self.txn_manager.create(
            device_id,
            estimate.step_size,
            offset_before=offset,
            timestamp=self._ts.now(),
        )

        self._audit("correction_attempt", device_id, transaction_id=txn.transaction_id, step=estimate.step_size)

        self._send_correction_request(txn)

        if simulate_response is not None:
            payload = (
                simulate_response(txn)
                if callable(simulate_response)
                else simulate_response
            )
            self.handle_correction_response(payload)
        elif self.send is None:
            self.txn_manager.fail(txn.transaction_id, "no transport path")
            self.health.record_failure()
            return self.txn_manager.get(txn.transaction_id)  # type: ignore[return-value]

        final = self._finalize_after_response(txn.transaction_id, device_id, advance_clock=advance_clock)
        return final

    def poll_pending_wire(self) -> list[RecoveryResult]:
        """Check SENT transactions for timeout and retry or fail."""
        results: list[RecoveryResult] = []
        for txn in list(self.txn_manager.list_unfinished()):
            if txn.state != TransactionState.SENT:
                continue
            outcome = self.retry_or_fail_sent(txn)
            results.append(
                RecoveryResult(
                    transaction_id=txn.transaction_id,
                    device_id=txn.device_id,
                    previous_state=TransactionState.SENT,
                    action=outcome["action"],
                    final_state=self.txn_manager.get(txn.transaction_id).state,  # type: ignore[union-attr]
                    reason=outcome.get("reason", ""),
                )
            )
        return results

    def retry_or_fail_sent(self, txn: CorrectionTransaction) -> dict[str, Any]:
        """Retry a SENT transaction or fail after max retries."""
        sent_at = int(txn.metadata.get("wire_sent_at", txn.timestamp))
        now = self._ts.now()
        retry_count = int(txn.metadata.get("retry_count", 0))

        if not self.reliability.is_timed_out(sent_at, now):
            return {"action": RecoveryAction.NO_ACTION, "reason": "not timed out"}

        if self.reliability.should_retry(retry_count):
            self.txn_manager.increment_retry(txn.transaction_id)
            self._resend_correction_request(self.txn_manager.get(txn.transaction_id))  # type: ignore[arg-type]
            return {"action": RecoveryAction.RETRIED_SEND, "reason": f"retry {retry_count + 1}"}

        self.txn_manager.fail(txn.transaction_id, "wire timeout: max retries exceeded")
        self.health.record_failure()
        self._audit(
            "correction_failed",
            txn.device_id,
            transaction_id=txn.transaction_id,
            reason="wire timeout",
        )
        return {"action": RecoveryAction.FAILED_TIMEOUT, "reason": "wire timeout"}

    def continue_verification(
        self,
        txn: CorrectionTransaction,
        *,
        advance_clock: Optional[AdvanceFn] = None,
    ) -> CorrectionTransaction:
        """Resume or start verification for APPLIED/VERIFYING transactions."""
        current = self.txn_manager.get(txn.transaction_id)
        if current is None:
            raise UnknownCorrectionTransaction(txn.transaction_id)

        if current.state == TransactionState.APPLIED:
            verify = self.verifier.verify_transaction(current, advance_clock=advance_clock)
        elif current.state == TransactionState.VERIFYING:
            verify = self.verifier.verify_transaction(current, advance_clock=advance_clock)
        else:
            return current

        return self._record_verification_outcome(
            txn.transaction_id, current.device_id, verify.verified, verify.improvement
        )

    def handle_correction_response(
        self, response: SyncCorrectionResponse | dict[str, Any]
    ) -> CorrectionTransaction:
        """Process inbound SYNC_CORRECTION_RESPONSE from wire."""
        if isinstance(response, SyncCorrectionResponse):
            parsed = response
        else:
            parsed = SyncCorrectionResponse.from_dict(response)

        existing = self.txn_manager.get(parsed.transaction_id)
        if existing is None:
            logger.warning("[PHYS BRIDGE] response for unknown transaction %s", parsed.transaction_id)
            raise UnknownCorrectionTransaction(parsed.transaction_id)

        txn = self.txn_manager.mark_applied(parsed.transaction_id, parsed)
        self._audit(
            "correction_applied",
            parsed.device_id,
            transaction_id=parsed.transaction_id,
            step=parsed.correction_step,
            accumulated=parsed.accumulated_correction,
        )
        return txn

    def _finalize_after_response(
        self,
        transaction_id: str,
        device_id: str,
        *,
        advance_clock: Optional[AdvanceFn] = None,
    ) -> CorrectionTransaction:
        current = self.txn_manager.get(transaction_id)
        if current is not None and current.state == TransactionState.APPLIED:
            verify = self.verifier.verify_transaction(current, advance_clock=advance_clock)
            self._audit(
                "correction_verified",
                device_id,
                transaction_id=transaction_id,
                verified=verify.verified,
                improvement=verify.improvement,
            )
            return self._record_verification_outcome(
                transaction_id, device_id, verify.verified, verify.improvement
            )

        final = self.txn_manager.get(transaction_id)
        assert final is not None
        return final

    def _record_verification_outcome(
        self,
        transaction_id: str,
        device_id: str,
        verified: bool,
        improvement: float,
    ) -> CorrectionTransaction:
        final = self.txn_manager.get(transaction_id)
        assert final is not None
        if verified:
            self.health.record_success(improvement=improvement)
        else:
            self.health.record_failure()
            if final.state == TransactionState.FAILED:
                self.txn_manager.rollback(transaction_id, reason="verification failed")
                self.health.record_rollback()
                self._audit("rollback", device_id, transaction_id=transaction_id)
            final = self.txn_manager.get(transaction_id)
        assert final is not None
        return final

    def _send_correction_request(self, txn: CorrectionTransaction) -> None:
        request = self.txn_manager.build_request(txn.transaction_id)
        wire = build_wire_correction_request(request, sequence=self._next_sequence())
        self.txn_manager.mark_sent(txn.transaction_id, sent_at=self._ts.now())
        if self.send is not None:
            self.send(wire)

    def _resend_correction_request(self, txn: CorrectionTransaction) -> None:
        request = self.txn_manager.build_request(txn.transaction_id)
        wire = build_wire_correction_request(request, sequence=self._next_sequence())
        self.txn_manager.update_wire_sent(txn.transaction_id, sent_at=self._ts.now())
        if self.send is not None:
            self.send(wire)

    def _next_sequence(self) -> int:
        self._sequence += 1
        return self._sequence

    def _audit(self, event: str, device_id: str, **fields: Any) -> None:
        if self.storage is None:
            return
        self.storage.append_correction_event(
            event,
            timestamp=self._ts.now(),
            device_id=device_id,
            **fields,
        )
