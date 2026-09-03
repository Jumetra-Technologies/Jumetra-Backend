"""Physical verification loop after correction."""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from typing import Any, Callable, Optional

from .adjuster.models import VerificationResult
from .adjuster.physical_limits import PhysicalCorrectionLimits
from .manager import SynchronizationManager
from .transactions.manager import CorrectionTransactionManager
from .transactions.state import TransactionState
from .transactions.transaction import CorrectionTransaction

logger = logging.getLogger("hhip.synchronization.physical_verification")

AdvanceFn = Callable[[int], None]


@dataclass
class PhysicalVerificationResult:
    """Outcome of post-correction physical verification."""

    transaction_id: str
    device_id: str
    offset_before: float
    offset_after: float
    improvement: float
    verified: bool
    stabilization_ms: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class PhysicalVerificationLoop:
    """Wait, re-measure, and verify correction improvement on physical path."""

    def __init__(
        self,
        sync_manager: SynchronizationManager,
        txn_manager: CorrectionTransactionManager,
        *,
        limits: Optional[PhysicalCorrectionLimits] = None,
    ) -> None:
        self.sync_manager = sync_manager
        self.txn_manager = txn_manager
        self.limits = limits or PhysicalCorrectionLimits()

    def verify_transaction(
        self,
        txn: CorrectionTransaction,
        *,
        advance_clock: Optional[AdvanceFn] = None,
        min_improvement: float = 0.0,
    ) -> PhysicalVerificationResult:
        """Run stabilization wait + SYNC_REQUEST + offset comparison."""
        device_id = txn.device_id
        offset_before = float(txn.offset_before if txn.offset_before is not None else 0.0)

        if txn.state != TransactionState.VERIFYING:
            self.txn_manager.start_verification(txn.transaction_id)

        stabilization = self.limits.stabilization_period_ms
        if advance_clock is not None:
            advance_clock(stabilization)
        # Real-time path: caller must wait externally before verify.

        self.sync_manager.request_sync(device_id)
        history = self.sync_manager.get_sample_history(device_id, limit=1)
        if not history:
            self.txn_manager.fail(txn.transaction_id, "verification measurement missing")
            return PhysicalVerificationResult(
                transaction_id=txn.transaction_id,
                device_id=device_id,
                offset_before=offset_before,
                offset_after=offset_before,
                improvement=0.0,
                verified=False,
                stabilization_ms=stabilization,
            )

        offset_after = float(history[-1].estimated_offset)
        improvement = abs(offset_before) - abs(offset_after)
        verified = improvement > min_improvement

        if verified:
            self.txn_manager.complete_verification(
                txn.transaction_id,
                offset_after=offset_after,
                improvement=improvement,
                verified=True,
            )
        else:
            self.txn_manager.fail(
                txn.transaction_id,
                f"insufficient improvement: {improvement:.2f}",
            )

        logger.info(
            "[PHYS VERIFY] %s before=%.2f after=%.2f improvement=%.2f verified=%s",
            device_id,
            offset_before,
            offset_after,
            improvement,
            verified,
        )
        return PhysicalVerificationResult(
            transaction_id=txn.transaction_id,
            device_id=device_id,
            offset_before=offset_before,
            offset_after=offset_after,
            improvement=improvement,
            verified=verified,
            stabilization_ms=stabilization,
        )

    def to_verification_result(self, result: PhysicalVerificationResult) -> VerificationResult:
        return VerificationResult(
            device_id=result.device_id,
            offset_before=result.offset_before,
            offset_after=result.offset_after,
            improvement=result.improvement,
            verified=result.verified,
            timestamp=0,
            step_applied=0.0,
        )
