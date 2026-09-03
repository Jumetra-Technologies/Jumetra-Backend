"""CorrectionSafetyGate — pre-apply safety checks."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from ..policy import CorrectionPolicy, SynchronizationSafetyConfig
from ..state import SyncState
from .models import SafetyGateResult

if TYPE_CHECKING:
    from ..sync_session import SyncSession


class CorrectionSafetyGate:
    """Verify session state and safety config before any correction."""

    def __init__(
        self,
        *,
        safety: Optional[SynchronizationSafetyConfig] = None,
        policy: Optional[CorrectionPolicy] = None,
        require_correction_ready: bool = True,
    ) -> None:
        self.safety = safety or SynchronizationSafetyConfig()
        self.policy = policy or CorrectionPolicy(self.safety)
        self.require_correction_ready = require_correction_ready

    def check(
        self,
        session: "SyncSession",
        offset: float,
        drift: float,
        confidence: float,
        *,
        uncertainty: float = 0.0,
    ) -> SafetyGateResult:
        """Return passed=True only when correction may proceed."""
        if self.require_correction_ready and session.state != SyncState.CORRECTION_READY:
            return SafetyGateResult(
                passed=False,
                reason=f"session state {session.state.value} != CORRECTION_READY",
            )

        decision = self.policy.evaluate(
            offset, drift, confidence, uncertainty=uncertainty
        )
        if not decision.allowed:
            return SafetyGateResult(passed=False, reason=decision.reason)

        return SafetyGateResult(passed=True, reason="safety gate passed")
