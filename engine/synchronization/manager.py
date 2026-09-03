"""SynchronizationManager — RTT / offset measurement over the EventBus.

Does **not** correct clocks. Collects SYNC_REQUEST / SYNC_RESPONSE
exchanges, computes RTT and estimated offset, and stores observations.

Sprint 9 adds multi-sample history, measurement windows, jitter, and
SyncQuality — still measurement only.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Deque, Mapping, Optional, Sequence, Union

from ..devices.base.device import Device, DeviceMode
from ..events.event import Event, EventStatus
from ..events.event_bus import EventBus
from ..events.subscriber import EventSubscriber
from ..time.timestamp_service import TimestampService, get_timestamp_service
from .agent import SyncAgent, create_sync_agent
from .events import SyncEventType
from .observation import ClockObservation
from .protocol import SyncRequest, SyncResponse
from .quality import SyncQuality

logger = logging.getLogger("hhip.synchronization.manager")

PathLike = Union[str, Path]


def _new_request_id() -> str:
    return f"sync_{uuid.uuid4().hex[:10]}"


class SynchronizationManager(EventSubscriber):
    """Create sync requests, process responses, record clock observations."""

    def __init__(
        self,
        event_bus: EventBus,
        *,
        timestamp_service: Optional[TimestampService] = None,
        device_manager: Optional[Any] = None,
        echo_virtual: bool = True,
        history_limit: int = 500,
        default_window_size: int = 100,
        network_model: Optional[Any] = None,
        clock_domains: Optional[Any] = None,
    ) -> None:
        self._bus = event_bus
        self._ts = timestamp_service or get_timestamp_service()
        self._device_manager = device_manager
        self._echo_virtual = echo_virtual
        self._pending: dict[str, dict[str, Any]] = {}
        self._observations: list[ClockObservation] = []
        self._history: dict[str, Deque[ClockObservation]] = defaultdict(
            lambda: deque(maxlen=history_limit)
        )
        self._sequence_by_device: dict[str, int] = defaultdict(int)
        self._agents: dict[str, SyncAgent] = {}
        self._history_limit = history_limit
        self._default_window_size = default_window_size
        self._experiment: Optional[Any] = None
        self._network = network_model
        self._clock_domains = clock_domains

    def set_network_model(self, model: Optional[Any]) -> None:
        """Attach optional NetworkConditionModel for virtual/simulator echoes."""
        self._network = model

    def set_clock_domains(self, registry: Optional[Any]) -> None:
        """Attach optional ClockDomainRegistry for observation bookkeeping."""
        self._clock_domains = registry

    # --- ExperimentSession binding -------------------------------------

    def bind_experiment(self, experiment: Optional[Any]) -> None:
        """Attach an active ExperimentSession to receive sync samples."""
        self._experiment = experiment

    # --- Agents --------------------------------------------------------

    def get_agent(self, device: Union[Device, str]) -> Optional[SyncAgent]:
        """Return a cached SyncAgent for ``device``, creating one if registered."""
        if isinstance(device, Device):
            device_obj = device
            device_id = device.device_id
        else:
            device_id = str(device)
            device_obj = None
            if self._device_manager is not None:
                device_obj = self._device_manager.get_device(device_id)
            if device_obj is None or not isinstance(device_obj, Device):
                return self._agents.get(device_id)

        if device_id not in self._agents:
            self._agents[device_id] = create_sync_agent(
                device_obj, timestamp_service=self._ts
            )
        return self._agents[device_id]

    # --- EventSubscriber -----------------------------------------------

    def handle_event(self, event: Event) -> None:
        """React to sync protocol events on the bus."""
        if event.event_type == SyncEventType.SYNC_REQUEST and self._echo_virtual:
            self._maybe_echo_response(event)
        elif event.event_type == SyncEventType.SYNC_RESPONSE:
            self.process_response(event)

    # --- Public API ----------------------------------------------------

    def request_sync(self, device: Union[Device, str]) -> Event:
        """Publish a SYNC_REQUEST targeting ``device`` and track it as pending."""
        device_id = device.device_id if isinstance(device, Device) else str(device)

        agent = self.get_agent(device)
        if agent is not None:
            request = agent.send_sync_request()
            self._sequence_by_device[device_id] = request.sequence_number
        else:
            self._sequence_by_device[device_id] += 1
            request = SyncRequest(
                sequence_number=self._sequence_by_device[device_id],
                device_id=device_id,
                server_timestamp=self._ts.now(),
            )

        request_id = request.request_id
        request_time = request.server_timestamp

        event = Event.create(
            event_type=SyncEventType.SYNC_REQUEST,
            source="hhip",
            target=device_id,
            payload=request.to_event_payload(),
            metadata={"origin": "synchronization"},
            correlation_id=request.correlation_id,
        )
        self._pending[request_id] = {
            "device_id": device_id,
            "request_time": request_time,
            "correlation_id": event.correlation_id,
            "event_id": event.event_id,
            "sequence_number": request.sequence_number,
        }

        logger.info(
            "[SYNC] REQUEST → %s request_id=%s seq=%s request_time=%s",
            device_id,
            request_id,
            request.sequence_number,
            request_time,
        )
        self._publish(event)
        return event

    def collect_samples(
        self,
        device: Union[Device, str],
        count: int = 100,
        *,
        advance_clock_ms: int = 0,
    ) -> list[ClockObservation]:
        """Issue ``count`` sync probes and return new observations.

        For virtual/simulator devices, echoes produce immediate samples.
        For physical devices, only requests are published — responses must
        arrive on the wire and be processed separately.
        """
        before = len(self._observations)
        for _ in range(max(0, count)):
            self.request_sync(device)
            if advance_clock_ms > 0:
                clock = getattr(self._ts, "_clock", None)
                if clock is not None and hasattr(clock, "advance"):
                    clock.advance(advance_clock_ms)
        return list(self._observations[before:])

    def process_response(self, event: Event) -> Optional[ClockObservation]:
        """Process a SYNC_RESPONSE Event: compute RTT and store observation.

        RTT = response_time - request_time

        estimated_offset is recorded only (Cristian-style midpoint estimate).
        Clocks are **not** adjusted.
        """
        if event.event_type != SyncEventType.SYNC_RESPONSE:
            raise ValueError(f"expected SYNC_RESPONSE, got {event.event_type}")

        payload = event.payload if isinstance(event.payload, dict) else {}
        from ..protocol.sync_wire import normalize_sync_response_payload

        payload = normalize_sync_response_payload(payload)
        request_id = payload.get("request_id")
        pending = self._pending.pop(request_id, None) if request_id else None

        request_time = payload.get("request_time")
        if request_time is None:
            request_time = payload.get("server_timestamp_host")
        if request_time is None and pending:
            request_time = pending["request_time"]
        if request_time is None:
            logger.warning("[SYNC] RESPONSE missing request_time; dropping")
            return None

        response_time = self._ts.now()

        # Prefer explicit device clock sample; fall back to Sprint 8 field name.
        device_timestamp = payload.get("device_timestamp")
        if device_timestamp is None:
            device_timestamp = payload.get("server_timestamp")
        if device_timestamp is None:
            logger.warning("[SYNC] RESPONSE missing device/server timestamp; dropping")
            return None

        request_time = int(request_time)
        response_time = int(response_time)
        device_timestamp = int(device_timestamp)
        rtt = response_time - request_time
        if rtt < 0:
            logger.warning("[SYNC] Negative RTT (%s); clamping to 0", rtt)
            rtt = 0

        # Observation only — classic midpoint estimate, no correction applied.
        estimated_offset = float(device_timestamp) - (float(request_time) + rtt / 2.0)
        device_id = event.source or (pending["device_id"] if pending else "")
        measurement_time = response_time

        observation = ClockObservation(
            device_id=device_id,
            local_timestamp=request_time,
            server_timestamp=device_timestamp,
            round_trip_time=rtt,
            estimated_offset=estimated_offset,
            measurement_time=measurement_time,
            request_time=request_time,
            response_time=response_time,
            request_id=str(request_id) if request_id else None,
            correlation_id=event.correlation_id,
            experiment_id=getattr(self._experiment, "experiment_id", None),
        )
        self._store_observation(observation)

        logger.info(
            "[SYNC] MEASUREMENT device=%s RTT=%sms offset_est=%.2f",
            device_id,
            rtt,
            estimated_offset,
        )
        return observation

    def record_agent_measurement(
        self,
        request: SyncRequest,
        response: SyncResponse,
        *,
        response_time: Optional[int] = None,
    ) -> ClockObservation:
        """Record a measurement built via SyncAgent.create_measurement."""
        agent = self.get_agent(request.device_id)
        if agent is None:
            # Ephemeral path when device is not registered.
            t0 = int(request.server_timestamp)
            t3 = int(response_time if response_time is not None else self._ts.now())
            device_ts = int(response.device_timestamp)
            rtt = max(0, t3 - t0)
            observation = ClockObservation(
                device_id=request.device_id,
                local_timestamp=t0,
                server_timestamp=device_ts,
                round_trip_time=rtt,
                estimated_offset=float(device_ts) - (float(t0) + rtt / 2.0),
                measurement_time=t3,
                request_time=t0,
                response_time=t3,
                request_id=request.request_id,
                correlation_id=response.correlation_id or request.correlation_id,
                experiment_id=getattr(self._experiment, "experiment_id", None),
            )
        else:
            observation = agent.create_measurement(
                request, response, response_time=response_time
            )
            observation.experiment_id = getattr(self._experiment, "experiment_id", None)

        self._store_observation(observation)
        return observation

    def get_measurements(self) -> list[ClockObservation]:
        """Return all recorded clock observations."""
        return list(self._observations)

    def get_sample_history(
        self,
        device_id: Optional[str] = None,
        *,
        limit: Optional[int] = None,
    ) -> list[ClockObservation]:
        """Return sample history for one device or all devices."""
        if device_id is None:
            samples = list(self._observations)
        else:
            samples = list(self._history.get(device_id, ()))
        if limit is not None:
            samples = samples[-limit:]
        return samples

    def get_measurement_window(
        self,
        device_id: str,
        *,
        window_size: Optional[int] = None,
    ) -> list[ClockObservation]:
        """Return the latest measurement window for ``device_id``."""
        size = window_size if window_size is not None else self._default_window_size
        history = self._history.get(device_id)
        if not history:
            return []
        items = list(history)
        return items[-size:] if size > 0 else items

    def compute_rtt_stats(
        self,
        device_id: Optional[str] = None,
        *,
        window_size: Optional[int] = None,
    ) -> dict[str, Any]:
        """Calculate average / min / max RTT and jitter for a sample set."""
        if device_id is None:
            samples = list(self._observations)
            if window_size is not None and window_size > 0:
                samples = samples[-window_size:]
        else:
            samples = self.get_measurement_window(device_id, window_size=window_size)

        if not samples:
            return {
                "device_id": device_id,
                "sample_count": 0,
                "average_rtt": None,
                "min_rtt": None,
                "max_rtt": None,
                "jitter": None,
            }

        rtts = [float(s.round_trip_time) for s in samples]
        avg = sum(rtts) / len(rtts)
        if len(rtts) >= 2:
            diffs = [abs(rtts[i] - rtts[i - 1]) for i in range(1, len(rtts))]
            jitter = sum(diffs) / len(diffs)
        else:
            jitter = 0.0
        return {
            "device_id": device_id,
            "sample_count": len(rtts),
            "average_rtt": avg,
            "min_rtt": min(rtts),
            "max_rtt": max(rtts),
            "jitter": jitter,
        }

    def get_quality(
        self,
        device_id: str,
        *,
        window_size: Optional[int] = None,
        target_samples: int = 100,
    ) -> SyncQuality:
        """Compute SyncQuality for ``device_id`` over the latest window."""
        samples = self.get_measurement_window(device_id, window_size=window_size)
        rtts = [float(s.round_trip_time) for s in samples]
        offsets = [float(s.estimated_offset) for s in samples]
        return SyncQuality.from_samples(
            device_id, rtts, offsets, target_samples=target_samples
        )

    def quality_summary(
        self,
        *,
        window_size: Optional[int] = None,
        target_samples: int = 100,
    ) -> dict[str, Any]:
        """Build a multi-device quality summary dict."""
        device_ids = sorted(self._history.keys())
        qualities = [
            self.get_quality(did, window_size=window_size, target_samples=target_samples)
            for did in device_ids
        ]
        return {
            "device_count": len(qualities),
            "total_samples": len(self._observations),
            "devices": [q.to_dict() for q in qualities],
        }

    def export_results(self, path: PathLike) -> Path:
        """Write observations to a JSON file (or directory + measurements.json)."""
        target = Path(path)
        if target.suffix.lower() != ".json":
            target.mkdir(parents=True, exist_ok=True)
            target = target / "sync_measurements.json"
        else:
            target.parent.mkdir(parents=True, exist_ok=True)

        payload = {
            "measurement_count": len(self._observations),
            "measurements": [obs.to_dict() for obs in self._observations],
            "summary": self.measurement_summary(),
            "quality": self.quality_summary(),
        }
        with target.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True)
            fh.write("\n")
        logger.info("[SYNC] Exported %d measurements → %s", len(self._observations), target)
        return target

    def export_samples_jsonl(self, path: PathLike) -> Path:
        """Export all samples as JSONL (``sync_samples.jsonl``)."""
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8") as fh:
            for obs in self._observations:
                fh.write(json.dumps(obs.to_dict(), separators=(",", ":")))
                fh.write("\n")
        return target

    def export_quality_summary(self, path: PathLike, **kwargs: Any) -> Path:
        """Export ``quality_summary.json``."""
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8") as fh:
            json.dump(self.quality_summary(**kwargs), fh, indent=2, sort_keys=True)
            fh.write("\n")
        return target

    def measurement_summary(self) -> dict[str, Any]:
        """Aggregate RTT / offset stats across all observations."""
        if not self._observations:
            return {
                "count": 0,
                "average_rtt": None,
                "min_rtt": None,
                "max_rtt": None,
                "jitter": None,
                "offset_samples": [],
            }
        stats = self.compute_rtt_stats()
        offsets = [o.estimated_offset for o in self._observations]
        return {
            "count": len(self._observations),
            "average_rtt": stats["average_rtt"],
            "min_rtt": stats["min_rtt"],
            "max_rtt": stats["max_rtt"],
            "jitter": stats["jitter"],
            "offset_samples": offsets,
            "average_offset_estimate": sum(offsets) / len(offsets),
        }

    def clear_measurements(self) -> None:
        """Drop pending requests and stored observations (tests / new runs)."""
        self._pending.clear()
        self._observations.clear()
        self._history.clear()
        self._sequence_by_device.clear()

    # --- Internals -----------------------------------------------------

    def _store_observation(self, observation: ClockObservation) -> None:
        self._observations.append(observation)
        self._history[observation.device_id].append(observation)
        self._update_device_metadata(observation.device_id, observation)
        if self._clock_domains is not None:
            self._clock_domains.record_observation(
                observation.device_id,
                observation,
                clock_type="device",
            )
        self._emit_measurement_events(observation)

        if self._experiment is not None and getattr(self._experiment, "is_active", False):
            self._experiment.record_sync_measurement(observation)

    def _publish(self, event: Event) -> None:
        if event.current_status == EventStatus.CREATED:
            event.set_status(EventStatus.QUEUED)
        self._bus.publish(event)

    def _maybe_echo_response(self, request: Event) -> None:
        """For VIRTUAL/SIMULATED devices, emit an in-process SYNC_RESPONSE.

        Physical devices must answer on the wire (see firmware sync_agent).
        """
        if self._device_manager is None:
            return
        device = self._device_manager.get_device(request.target)
        if device is None or not isinstance(device, Device):
            return
        if device.device_mode == DeviceMode.PHYSICAL:
            return

        # Optional virtual/simulator network impairment (measurement realism).
        if self._network is not None:
            if self._network.should_drop():
                logger.info(
                    "[SYNC] RESPONSE dropped by network model for %s", device.device_id
                )
                return
            clock = getattr(self._ts, "clock", None)
            self._network.apply_delay(clock)

        payload = request.payload if isinstance(request.payload, dict) else {}
        agent = self.get_agent(device)
        if agent is not None and hasattr(agent, "echo_response"):
            sync_req = SyncRequest.from_dict(
                {
                    **payload,
                    "device_id": device.device_id,
                    "server_timestamp": payload.get(
                        "server_timestamp", payload.get("request_time", self._ts.now())
                    ),
                    "sequence_number": payload.get("sequence_number", 0),
                    "correlation_id": request.correlation_id
                    or payload.get("correlation_id"),
                    "request_id": payload.get("request_id") or _new_request_id(),
                }
            )
            sync_resp = agent.echo_response(sync_req)
            response_payload = sync_resp.to_event_payload()
            # Sprint 8 compat: server_timestamp remains the device clock sample.
            response_payload["server_timestamp"] = sync_resp.device_timestamp
            response_payload["request_time"] = sync_req.server_timestamp
        else:
            skew = int(
                device.metadata.get("clock_offset_estimate")
                or device.metadata.get("clock_offset")
                or 0
            )
            device_timestamp = self._ts.now() + skew
            response_payload = {
                "request_id": payload.get("request_id"),
                "request_time": payload.get("request_time"),
                "server_timestamp": device_timestamp,
                "device_timestamp": device_timestamp,
                "sequence_number": payload.get("sequence_number", 0),
                "device_id": device.device_id,
                "correlation_id": request.correlation_id,
            }

        response = Event.create(
            event_type=SyncEventType.SYNC_RESPONSE,
            source=device.device_id,
            target="hhip",
            payload=response_payload,
            metadata={"origin": "synchronization", "echo": True},
            correlation_id=request.correlation_id,
        )
        logger.info(
            "[SYNC] RESPONSE (echo) ← %s device_timestamp=%s",
            device.device_id,
            response_payload.get("device_timestamp", response_payload.get("server_timestamp")),
        )
        self._publish(response)

    def _update_device_metadata(self, device_id: str, observation: ClockObservation) -> None:
        if self._device_manager is None:
            return
        device = self._device_manager.get_device(device_id)
        if device is None or not isinstance(device, Device):
            return
        device.metadata["clock_offset_estimate"] = observation.estimated_offset
        device.metadata["clock_drift_estimate"] = device.metadata.get("clock_drift_estimate", 0.0)
        device.metadata["last_sync_measurement"] = observation.to_dict()
        # Keep Sprint 7 aliases updated as observations only.
        device.metadata["clock_offset"] = observation.estimated_offset
        device.metadata["last_sync_time"] = observation.measurement_time
        quality = self.get_quality(device_id)
        device.metadata["sync_quality"] = quality.to_dict()

    def _emit_measurement_events(self, observation: ClockObservation) -> None:
        sample = Event.create(
            event_type=SyncEventType.CLOCK_SAMPLE,
            source=observation.device_id,
            target="hhip",
            payload=observation.to_dict(),
            metadata={"origin": "synchronization"},
            correlation_id=observation.correlation_id,
        )
        measurement = Event.create(
            event_type=SyncEventType.SYNC_MEASUREMENT,
            source="hhip",
            target=observation.device_id,
            payload={
                "round_trip_time": observation.round_trip_time,
                "estimated_offset": observation.estimated_offset,
                "request_id": observation.request_id,
            },
            metadata={"origin": "synchronization"},
            correlation_id=observation.correlation_id,
        )
        # Avoid re-entrancy storms: publish measurement events without echoing.
        echo = self._echo_virtual
        self._echo_virtual = False
        try:
            self._publish(sample)
            self._publish(measurement)
        finally:
            self._echo_virtual = echo
