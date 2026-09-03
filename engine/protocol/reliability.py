"""Wire reliability — timeout, retry, and exponential backoff."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Optional


@dataclass
class WireReliabilityConfig:
    """Configuration for correction wire operations."""

    timeout_ms: int = 5_000
    max_retries: int = 3
    initial_backoff_ms: int = 100
    backoff_multiplier: float = 2.0
    max_backoff_ms: int = 2_000

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "WireReliabilityConfig":
        return cls(
            timeout_ms=int(data.get("timeout_ms", 5_000)),
            max_retries=int(data.get("max_retries", 3)),
            initial_backoff_ms=int(data.get("initial_backoff_ms", 100)),
            backoff_multiplier=float(data.get("backoff_multiplier", 2.0)),
            max_backoff_ms=int(data.get("max_backoff_ms", 2_000)),
        )


@dataclass
class WireAttempt:
    """One wire send attempt for a correction transaction."""

    transaction_id: str
    attempt: int
    sent_at: int
    next_retry_at: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class WireReliabilityPolicy:
    """Timeout detection, retry eligibility, and backoff delays."""

    def __init__(self, config: Optional[WireReliabilityConfig] = None) -> None:
        self.config = config or WireReliabilityConfig()

    def is_timed_out(self, sent_at: int, now_ms: int) -> bool:
        if sent_at <= 0:
            return False
        return (now_ms - sent_at) >= self.config.timeout_ms

    def should_retry(self, attempt: int) -> bool:
        """Return True if another attempt is allowed (attempt is 0-based)."""
        return attempt < self.config.max_retries

    def backoff_delay_ms(self, attempt: int) -> int:
        """Exponential backoff for retry ``attempt`` (0-based)."""
        if attempt <= 0:
            return 0
        delay = int(
            self.config.initial_backoff_ms
            * (self.config.backoff_multiplier ** (attempt - 1))
        )
        return min(delay, self.config.max_backoff_ms)

    def next_retry_at(self, sent_at: int, attempt: int) -> int:
        return sent_at + self.config.timeout_ms + self.backoff_delay_ms(attempt + 1)

    def record_attempt(self, transaction_id: str, attempt: int, sent_at: int) -> WireAttempt:
        return WireAttempt(
            transaction_id=transaction_id,
            attempt=attempt,
            sent_at=sent_at,
            next_retry_at=self.next_retry_at(sent_at, attempt),
        )
