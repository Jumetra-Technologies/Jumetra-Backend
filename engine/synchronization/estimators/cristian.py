"""CristianOffsetEstimator — classic midpoint offset estimation."""

from __future__ import annotations

from typing import Optional, Sequence

from ..observation import ClockObservation
from .offset_estimate import ClockOffsetEstimate


class CristianOffsetEstimator:
    """Estimate clock offset using Cristian's algorithm (midpoint approximation).

    Formula (HHIP field mapping)::

        host_time   = observation.local_timestamp   # T0 (HHIP / "server" probe time)
        device_time = observation.server_timestamp  # remote clock sample
        RTT         = observation.round_trip_time

        offset = device_time - (host_time + RTT / 2)

    Equivalent to the sprint wording when ``server_time`` means the remote
    clock sample stored in ``server_timestamp`` and ``device_time`` means the
    host probe time (legacy observation field names).

    Does **not** correct clocks — estimation only.
    """

    ALGORITHM = "cristian"

    def estimate(self, observation: ClockObservation) -> ClockOffsetEstimate:
        """Compute a Cristian offset estimate from one ClockObservation."""
        host_time = int(
            observation.request_time
            if observation.request_time is not None
            else observation.local_timestamp
        )
        device_time = int(observation.server_timestamp)
        rtt = int(observation.round_trip_time)
        if rtt < 0:
            rtt = 0
        offset = float(device_time) - (float(host_time) + rtt / 2.0)
        return ClockOffsetEstimate(
            device_id=observation.device_id,
            estimated_offset=offset,
            host_time=host_time,
            device_time=device_time,
            round_trip_time=rtt,
            algorithm=self.ALGORITHM,
            request_id=observation.request_id,
        )

    def estimate_many(
        self, observations: Sequence[ClockObservation]
    ) -> list[ClockOffsetEstimate]:
        """Estimate offset for each observation."""
        return [self.estimate(obs) for obs in observations]

    def estimate_from_fields(
        self,
        *,
        device_id: str,
        host_time: int,
        device_time: int,
        round_trip_time: int,
        request_id: Optional[str] = None,
    ) -> ClockOffsetEstimate:
        """Direct Cristian calculation without a ClockObservation object."""
        rtt = max(0, int(round_trip_time))
        offset = float(device_time) - (float(host_time) + rtt / 2.0)
        return ClockOffsetEstimate(
            device_id=device_id,
            estimated_offset=offset,
            host_time=int(host_time),
            device_time=int(device_time),
            round_trip_time=rtt,
            algorithm=self.ALGORITHM,
            request_id=request_id,
        )
