"""MinimumRTTSelector — prefer lowest-RTT samples for Cristian estimation."""

from __future__ import annotations

from typing import Optional, Sequence

from .observation import ClockObservation


class MinimumRTTSelector:
    """Select the lowest-RTT observations from a sample window.

    Rules:
        - Reject invalid measurements (negative RTT, missing timestamps).
        - Consider only the latest ``window_size`` samples when configured.
        - Return up to ``top_k`` samples with the smallest RTT (stable by order).
    """

    def __init__(
        self,
        *,
        window_size: Optional[int] = None,
        top_k: int = 1,
        max_rtt: Optional[int] = None,
    ) -> None:
        if top_k < 1:
            raise ValueError("top_k must be >= 1")
        if window_size is not None and window_size < 1:
            raise ValueError("window_size must be >= 1 when set")
        self.window_size = window_size
        self.top_k = top_k
        self.max_rtt = max_rtt

    def is_valid(self, observation: ClockObservation) -> bool:
        """Return True if the observation is usable for offset estimation."""
        if observation.round_trip_time < 0:
            return False
        if self.max_rtt is not None and observation.round_trip_time > self.max_rtt:
            return False
        if observation.local_timestamp < 0 or observation.server_timestamp < 0:
            return False
        return True

    def select(self, observations: Sequence[ClockObservation]) -> list[ClockObservation]:
        """Return the lowest-RTT valid samples (up to ``top_k``)."""
        samples = list(observations)
        if self.window_size is not None:
            samples = samples[-self.window_size :]

        valid = [obs for obs in samples if self.is_valid(obs)]
        if not valid:
            return []

        # Stable sort: lower RTT first; preserve relative order for ties.
        ranked = sorted(
            enumerate(valid),
            key=lambda pair: (pair[1].round_trip_time, pair[0]),
        )
        return [obs for _, obs in ranked[: self.top_k]]

    def select_best(self, observations: Sequence[ClockObservation]) -> Optional[ClockObservation]:
        """Return the single lowest-RTT valid sample, or None."""
        selected = self.select(observations)
        return selected[0] if selected else None
