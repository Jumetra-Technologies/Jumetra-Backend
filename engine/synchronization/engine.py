"""SynchronizationEngine — Cristian offset estimation pipeline (v1)."""

from __future__ import annotations

import logging
from typing import Any, Optional, Sequence, Union

from ..time.timestamp_service import TimestampService, get_timestamp_service
from .adjuster import ClockAdjuster, NullClockAdjuster
from .estimators.cristian import CristianOffsetEstimator
from .estimators.offset_estimate import ClockOffsetEstimate
from .filtering import FilterMode, OffsetFilter
from .observation import ClockObservation
from .quality import SyncQuality
from .result import SynchronizationResult
from .selection import MinimumRTTSelector

logger = logging.getLogger("hhip.synchronization.engine")


class SynchronizationEngine:
    """Consume ClockObservation samples and produce a SynchronizationResult.

    Pipeline:
        observations → MinimumRTTSelector → CristianOffsetEstimator
                    → OffsetFilter → SynchronizationResult

    Does **not** apply clock correction. An optional ClockAdjuster may be
    attached for future use; by default a NullClockAdjuster records intent only.
    """

    def __init__(
        self,
        *,
        estimator: Optional[CristianOffsetEstimator] = None,
        selector: Optional[MinimumRTTSelector] = None,
        offset_filter: Optional[OffsetFilter] = None,
        adjuster: Optional[ClockAdjuster] = None,
        timestamp_service: Optional[TimestampService] = None,
        apply_correction: bool = False,
    ) -> None:
        self.estimator = estimator or CristianOffsetEstimator()
        self.selector = selector or MinimumRTTSelector(window_size=100, top_k=5)
        self.offset_filter = offset_filter or OffsetFilter(
            FilterMode.MEDIAN, window=5
        )
        self.adjuster = adjuster or NullClockAdjuster()
        self._ts = timestamp_service or get_timestamp_service()
        # Sprint 11: keep False — estimation only.
        self.apply_correction = apply_correction
        self._last_result: Optional[SynchronizationResult] = None

    def synchronize(
        self,
        observations: Sequence[ClockObservation],
        *,
        device_id: Optional[str] = None,
        before_offset: Optional[float] = None,
    ) -> SynchronizationResult:
        """Run Cristian estimation over ``observations`` and return a result."""
        samples = list(observations)
        if device_id is None:
            if not samples:
                raise ValueError("device_id required when observations are empty")
            device_id = samples[0].device_id
        else:
            samples = [s for s in samples if s.device_id == device_id]

        if before_offset is None and samples:
            before_offset = float(samples[0].estimated_offset)

        selected = self.selector.select(samples)
        if not selected:
            result = SynchronizationResult(
                device_id=device_id,
                estimated_offset=float(before_offset or 0.0),
                sample_count=len(samples),
                selected_samples=0,
                confidence=0.0,
                timestamp=self._ts.now(),
                algorithm_used=CristianOffsetEstimator.ALGORITHM,
                before_offset=before_offset,
                filter_mode=self.offset_filter.mode.value,
            )
            self._last_result = result
            return result

        estimates = self.estimator.estimate_many(selected)
        offsets = [e.estimated_offset for e in estimates]
        filtered_offset = self.offset_filter.filter(offsets)

        rtts = [float(s.round_trip_time) for s in selected]
        quality = SyncQuality.from_samples(
            device_id,
            rtts,
            offsets,
            target_samples=max(len(samples), 1),
        )

        result = SynchronizationResult(
            device_id=device_id,
            estimated_offset=float(filtered_offset),
            sample_count=len(samples),
            selected_samples=len(selected),
            confidence=float(quality.confidence_score),
            timestamp=self._ts.now(),
            algorithm_used=CristianOffsetEstimator.ALGORITHM,
            before_offset=before_offset,
            min_rtt_selected=min(rtts) if rtts else None,
            filter_mode=self.offset_filter.mode.value,
            selected_offsets=list(offsets),
            metadata={
                "window_size": self.selector.window_size,
                "top_k": self.selector.top_k,
                "quality": quality.to_dict(),
            },
        )
        self._last_result = result

        if self.apply_correction:
            from .sync_session import SyncSession

            session = SyncSession(device_id=device_id)
            session.begin()
            estimate = self.adjuster.estimate_correction(
                device_id,
                result.estimated_offset,
                session,
                confidence=result.confidence,
            )
            self.adjuster.apply_correction(
                device_id,
                estimate,
                metadata={"algorithm": result.algorithm_used},
            )

        logger.info(
            "[SYNC ENGINE] device=%s offset=%.3f selected=%d/%d confidence=%.3f",
            device_id,
            result.estimated_offset,
            result.selected_samples,
            result.sample_count,
            result.confidence,
        )
        return result

    def synchronize_from_manager(
        self,
        manager: Any,
        device_id: str,
        *,
        before_offset: Optional[float] = None,
    ) -> SynchronizationResult:
        """Convenience: pull sample history from a SynchronizationManager."""
        samples = manager.get_sample_history(device_id)
        return self.synchronize(
            samples, device_id=device_id, before_offset=before_offset
        )

    @property
    def last_result(self) -> Optional[SynchronizationResult]:
        return self._last_result

    def estimate_one(self, observation: ClockObservation) -> ClockOffsetEstimate:
        """Estimate offset from a single observation (no selection/filter)."""
        return self.estimator.estimate(observation)
