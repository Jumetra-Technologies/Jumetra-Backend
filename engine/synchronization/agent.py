"""SyncAgent interface and mode-specific agents (measurement only)."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Optional, TYPE_CHECKING

from ..devices.base.device import Device, DeviceMode
from ..time.timestamp_service import TimestampService, get_timestamp_service
from .observation import ClockObservation
from .protocol import SyncRequest, SyncResponse

if TYPE_CHECKING:
    from ..events.event import Event

logger = logging.getLogger("hhip.synchronization.agent")


class SyncAgent(ABC):
    """Abstract synchronization agent for virtual / simulator / physical devices."""

    def __init__(
        self,
        device: Device,
        *,
        timestamp_service: Optional[TimestampService] = None,
    ) -> None:
        self.device = device
        self._ts = timestamp_service or get_timestamp_service()
        self._sequence = 0

    @property
    def device_id(self) -> str:
        return self.device.device_id

    def _next_sequence(self) -> int:
        self._sequence += 1
        return self._sequence

    @abstractmethod
    def send_sync_request(self) -> SyncRequest:
        """Build (and optionally transmit) a SYNC_REQUEST for this device."""

    @abstractmethod
    def receive_sync_response(self, response: SyncResponse | dict[str, Any]) -> SyncResponse:
        """Accept a SYNC_RESPONSE (object or mapping) for this device."""

    def create_measurement(
        self,
        request: SyncRequest,
        response: SyncResponse,
        *,
        response_time: Optional[int] = None,
    ) -> ClockObservation:
        """Create a ClockObservation from a request/response pair (no correction)."""
        t0 = int(request.server_timestamp)
        t3 = int(response_time if response_time is not None else self._ts.now())
        device_ts = int(response.device_timestamp)
        rtt = t3 - t0
        if rtt < 0:
            rtt = 0
        estimated_offset = float(device_ts) - (float(t0) + rtt / 2.0)
        return ClockObservation(
            device_id=self.device_id,
            local_timestamp=t0,
            server_timestamp=device_ts,
            round_trip_time=rtt,
            estimated_offset=estimated_offset,
            measurement_time=t3,
            request_time=t0,
            response_time=t3,
            request_id=request.request_id,
            correlation_id=response.correlation_id or request.correlation_id,
        )


class VirtualSyncAgent(SyncAgent):
    """In-process agent for VIRTUAL devices — echoes a local response."""

    def send_sync_request(self) -> SyncRequest:
        return SyncRequest(
            sequence_number=self._next_sequence(),
            device_id=self.device_id,
            server_timestamp=self._ts.now(),
        )

    def receive_sync_response(self, response: SyncResponse | dict[str, Any]) -> SyncResponse:
        if isinstance(response, SyncResponse):
            return response
        return SyncResponse.from_dict(response)

    def echo_response(self, request: SyncRequest) -> SyncResponse:
        """Simulate a device reply using optional metadata skew (observation only)."""
        skew = int(
            self.device.metadata.get("clock_offset_estimate")
            or self.device.metadata.get("clock_offset")
            or 0
        )
        device_timestamp = self._ts.now() + skew
        return SyncResponse(
            sequence_number=request.sequence_number,
            device_id=self.device_id,
            server_timestamp=request.server_timestamp,
            device_timestamp=device_timestamp,
            correlation_id=request.correlation_id,
            request_id=request.request_id,
        )


class SimulatorSyncAgent(SyncAgent):
    """Agent for SIMULATED devices (Wokwi/Proteus later) — local echo for now."""

    def send_sync_request(self) -> SyncRequest:
        return SyncRequest(
            sequence_number=self._next_sequence(),
            device_id=self.device_id,
            server_timestamp=self._ts.now(),
        )

    def receive_sync_response(self, response: SyncResponse | dict[str, Any]) -> SyncResponse:
        if isinstance(response, SyncResponse):
            return response
        return SyncResponse.from_dict(response)

    def echo_response(self, request: SyncRequest) -> SyncResponse:
        skew = int(
            self.device.metadata.get("clock_offset_estimate")
            or self.device.metadata.get("clock_offset")
            or 0
        )
        return SyncResponse(
            sequence_number=request.sequence_number,
            device_id=self.device_id,
            server_timestamp=request.server_timestamp,
            device_timestamp=self._ts.now() + skew,
            correlation_id=request.correlation_id,
            request_id=request.request_id,
        )


class PhysicalSyncAgent(SyncAgent):
    """Agent for PHYSICAL devices — builds wire-ready messages; no auto-echo.

    Transmission is owned by the communication layer / engine. This agent
    only constructs protocol objects and measurements.
    """

    def send_sync_request(self) -> SyncRequest:
        return SyncRequest(
            sequence_number=self._next_sequence(),
            device_id=self.device_id,
            server_timestamp=self._ts.now(),
        )

    def receive_sync_response(self, response: SyncResponse | dict[str, Any]) -> SyncResponse:
        if isinstance(response, SyncResponse):
            parsed = response
        else:
            parsed = SyncResponse.from_dict(response)
        if parsed.device_id and parsed.device_id != self.device_id:
            logger.warning(
                "[SYNC AGENT] Response device_id %s != agent %s",
                parsed.device_id,
                self.device_id,
            )
        return parsed

    def to_wire_request(self, request: SyncRequest) -> dict[str, Any]:
        """HHIP Protocol Version 1 envelope for serial transport."""
        return {
            "version": 1,
            "type": "SYNC_REQUEST",
            "source": "hhip",
            "target": self.device_id,
            "sequence": request.sequence_number,
            "timestamp": request.server_timestamp,
            "payload": request.to_event_payload(),
            "message_id": request.request_id,
        }


def create_sync_agent(
    device: Device,
    *,
    timestamp_service: Optional[TimestampService] = None,
) -> SyncAgent:
    """Factory: pick an agent implementation from ``device.device_mode``."""
    ts = timestamp_service or get_timestamp_service()
    if device.device_mode == DeviceMode.PHYSICAL:
        return PhysicalSyncAgent(device, timestamp_service=ts)
    if device.device_mode == DeviceMode.SIMULATED:
        return SimulatorSyncAgent(device, timestamp_service=ts)
    return VirtualSyncAgent(device, timestamp_service=ts)
