"""Synchronization / latency experiment recording (measurement only)."""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Union

from engine.time.timestamp_service import get_timestamp_service

logger = logging.getLogger("hhip.experiments.session")

PathLike = Union[str, Path]

SyncResultFactory = Callable[[], Any]
ClockAdvance = Callable[[int], None]


def _new_experiment_id() -> str:
    return f"EXP{uuid.uuid4().hex[:6].upper()}"


@dataclass
class ExperimentSession:
    """Records events and metrics for a synchronization / latency experiment.

    Does not run synchronization algorithms — only captures timing data
    for later analysis.
    """

    name: str
    experiment_id: str = field(default_factory=_new_experiment_id)
    start_time: Optional[int] = None
    end_time: Optional[int] = None
    devices: list[str] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    metrics: list[dict[str, Any]] = field(default_factory=list)
    sync_measurements: list[dict[str, Any]] = field(default_factory=list)
    sync_results: list[dict[str, Any]] = field(default_factory=list)
    sync_time_series: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    planned_duration_ms: Optional[int] = None
    sync_interval_ms: Optional[int] = None
    _active: bool = field(default=False, repr=False)

    def start(
        self,
        *,
        devices: Optional[list[str]] = None,
        duration_ms: Optional[int] = None,
        sync_interval_ms: Optional[int] = None,
    ) -> "ExperimentSession":
        """Mark the experiment as running and record start_time."""
        if self._active:
            raise RuntimeError(f"experiment {self.experiment_id} already started")
        ts = get_timestamp_service()
        self.start_time = ts.now()
        if devices:
            self.devices = list(devices)
        if duration_ms is not None:
            self.planned_duration_ms = int(duration_ms)
            self.metadata["planned_duration_ms"] = self.planned_duration_ms
        if sync_interval_ms is not None:
            self.sync_interval_ms = int(sync_interval_ms)
            self.metadata["sync_interval_ms"] = self.sync_interval_ms
        self._active = True
        logger.info(
            "[EXPERIMENT] Started %s (%s) devices=%s duration_ms=%s",
            self.experiment_id,
            self.name,
            self.devices,
            self.planned_duration_ms,
        )
        return self

    def start_duration(
        self,
        duration_ms: int,
        *,
        devices: Optional[list[str]] = None,
        sync_interval_ms: Optional[int] = None,
    ) -> "ExperimentSession":
        """Start a duration-based long-running calibration experiment."""
        return self.start(
            devices=devices,
            duration_ms=duration_ms,
            sync_interval_ms=sync_interval_ms,
        )

    def elapsed_ms(self) -> int:
        """Milliseconds since experiment start (0 if not started)."""
        if self.start_time is None:
            return 0
        return max(0, get_timestamp_service().now() - self.start_time)

    def is_duration_complete(self) -> bool:
        """Return True when planned duration has elapsed."""
        if self.planned_duration_ms is None or self.start_time is None:
            return False
        return self.elapsed_ms() >= self.planned_duration_ms

    def record_event(self, event: Any) -> dict[str, Any]:
        """Record one event (Event or mapping) with timing + latencies."""
        if not self._active:
            raise RuntimeError(f"experiment {self.experiment_id} is not active")

        if hasattr(event, "to_dict"):
            record = event.to_dict()
        else:
            record = dict(event)

        from engine.time.timestamp_service import get_timestamp_service as _get_ts

        svc = _get_ts()
        if hasattr(event, "timing"):
            record["timing"] = svc.get_timing(event)
            record["latencies"] = svc.compute_latencies(event)
        else:
            record.setdefault("timing", {})
            record.setdefault("latencies", {})

        self.events.append(record)
        return record

    def record_metric(self, metric: Mapping[str, Any]) -> None:
        """Append a metric snapshot to the experiment."""
        if not self._active:
            raise RuntimeError(f"experiment {self.experiment_id} is not active")
        self.metrics.append(dict(metric))

    def record_sync_measurement(self, observation: Any) -> dict[str, Any]:
        """Record a ClockObservation (or mapping) from SynchronizationManager."""
        if not self._active:
            raise RuntimeError(f"experiment {self.experiment_id} is not active")
        record = observation.to_dict() if hasattr(observation, "to_dict") else dict(observation)
        record.setdefault("experiment_id", self.experiment_id)
        self.sync_measurements.append(record)
        return record

    def record_sync_result(self, result: Any) -> dict[str, Any]:
        """Record a SynchronizationResult (estimation only — no clock adjust).

        Stores before_offset, estimated_offset, algorithm_used, sample_count.
        """
        if not self._active:
            raise RuntimeError(f"experiment {self.experiment_id} is not active")
        record = result.to_dict() if hasattr(result, "to_dict") else dict(result)
        record.setdefault("experiment_id", self.experiment_id)
        # Ensure sprint-required analysis fields are present.
        record.setdefault("before_offset", record.get("before_offset"))
        record.setdefault("estimated_offset", record.get("estimated_offset"))
        record.setdefault("algorithm_used", record.get("algorithm_used", "cristian"))
        record.setdefault("sample_count", record.get("sample_count", 0))
        self.sync_results.append(record)
        return record

    def record_sync_time_point(self, result: Any) -> dict[str, Any]:
        """Record a periodic sync result into the time series."""
        record = self.record_sync_result(result)
        point = {
            "sequence": len(self.sync_time_series),
            "timestamp": record.get("timestamp"),
            "elapsed_ms": self.elapsed_ms(),
            "device_id": record.get("device_id"),
            "estimated_offset": record.get("estimated_offset"),
            "confidence": record.get("confidence"),
            "sample_count": record.get("sample_count"),
            "algorithm_used": record.get("algorithm_used"),
        }
        self.sync_time_series.append(point)
        return point

    def run_periodic_sync(
        self,
        sync_fn: SyncResultFactory,
        *,
        interval_ms: int,
        duration_ms: int,
        advance_clock: Optional[ClockAdvance] = None,
    ) -> list[dict[str, Any]]:
        """Run periodic sync measurements over a simulated or real duration.

        ``sync_fn`` is called once per interval and should return a
        SynchronizationResult (or mapping). ``advance_clock`` is optional
        and used in tests with SimulationClock to step host time forward.
        """
        if not self._active:
            self.start_duration(duration_ms, sync_interval_ms=interval_ms)
        elif self.planned_duration_ms is None:
            self.planned_duration_ms = int(duration_ms)
            self.metadata["planned_duration_ms"] = self.planned_duration_ms
        if self.sync_interval_ms is None:
            self.sync_interval_ms = int(interval_ms)
            self.metadata["sync_interval_ms"] = self.sync_interval_ms

        points: list[dict[str, Any]] = []
        elapsed = 0
        while elapsed < duration_ms:
            result = sync_fn()
            points.append(self.record_sync_time_point(result))
            elapsed += interval_ms
            if advance_clock is not None:
                advance_clock(interval_ms)
            else:
                # Real-time path: rely on host clock between probes.
                if self.is_duration_complete():
                    break
        return points

    def finish(self) -> "ExperimentSession":
        """Mark the experiment complete and record end_time."""
        if not self._active:
            raise RuntimeError(f"experiment {self.experiment_id} is not active")
        self.end_time = get_timestamp_service().now()
        self._active = False
        logger.info(
            "[EXPERIMENT] Finished %s events=%d metrics=%d duration_ms=%s",
            self.experiment_id,
            len(self.events),
            len(self.metrics),
            (self.end_time - self.start_time) if self.start_time else None,
        )
        return self

    @property
    def is_active(self) -> bool:
        return self._active

    def summary(self) -> dict[str, Any]:
        """Build a summary dict suitable for summary.json."""
        totals = [
            e.get("latencies", {}).get("total_latency")
            for e in self.events
            if isinstance(e.get("latencies"), dict)
        ]
        totals_f = [float(t) for t in totals if t is not None]
        rtts = [
            int(s["round_trip_time"])
            for s in self.sync_measurements
            if s.get("round_trip_time") is not None
        ]
        offsets = [
            float(s["estimated_offset"])
            for s in self.sync_measurements
            if s.get("estimated_offset") is not None
        ]
        jitter = None
        if len(rtts) >= 2:
            diffs = [abs(rtts[i] - rtts[i - 1]) for i in range(1, len(rtts))]
            jitter = sum(diffs) / len(diffs)
        elif rtts:
            jitter = 0.0

        quality = self._quality_by_device()
        return {
            "experiment_id": self.experiment_id,
            "name": self.name,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": (
                (self.end_time - self.start_time)
                if self.start_time is not None and self.end_time is not None
                else None
            ),
            "devices": list(self.devices),
            "event_count": len(self.events),
            "metric_count": len(self.metrics),
            "sync_measurement_count": len(self.sync_measurements),
            "total_latency_avg_ms": (sum(totals_f) / len(totals_f)) if totals_f else 0.0,
            "total_latency_min_ms": min(totals_f) if totals_f else None,
            "total_latency_max_ms": max(totals_f) if totals_f else None,
            "average_rtt": (sum(rtts) / len(rtts)) if rtts else None,
            "min_rtt": min(rtts) if rtts else None,
            "max_rtt": max(rtts) if rtts else None,
            "jitter": jitter,
            "offset_samples": offsets,
            "quality": quality,
            "sync_result_count": len(self.sync_results),
            "sync_results": list(self.sync_results),
            "sync_time_series_count": len(self.sync_time_series),
            "planned_duration_ms": self.planned_duration_ms,
            "sync_interval_ms": self.sync_interval_ms,
            "metadata": dict(self.metadata),
        }

    def build_calibration_report(self, device_id: Optional[str] = None) -> dict[str, Any]:
        """Build a ClockCalibrationReport dict from recorded sync results."""
        from engine.synchronization.calibration import ClockCalibrationReport
        from engine.synchronization.drift import ClockDriftEstimator
        from engine.synchronization.result import SynchronizationResult

        results = [SynchronizationResult.from_dict(r) for r in self.sync_results]
        report = ClockCalibrationReport.from_results(
            results,
            device_id=device_id,
            experiment_id=self.experiment_id,
            metadata={"name": self.name, "duration_ms": self.summary().get("duration_ms")},
            estimator=ClockDriftEstimator(),
        )
        return report.to_dict()

    def _quality_by_device(self, *, target_samples: int = 100) -> dict[str, Any]:
        """Build SyncQuality summaries grouped by device_id."""
        from engine.synchronization.quality import SyncQuality

        by_device: dict[str, list[dict[str, Any]]] = {}
        for sample in self.sync_measurements:
            did = str(sample.get("device_id") or "")
            by_device.setdefault(did, []).append(sample)

        devices = []
        for device_id, samples in sorted(by_device.items()):
            rtts = [
                float(s["round_trip_time"])
                for s in samples
                if s.get("round_trip_time") is not None
            ]
            offsets = [
                float(s["estimated_offset"])
                for s in samples
                if s.get("estimated_offset") is not None
            ]
            devices.append(
                SyncQuality.from_samples(
                    device_id, rtts, offsets, target_samples=target_samples
                ).to_dict()
            )
        return {
            "device_count": len(devices),
            "total_samples": len(self.sync_measurements),
            "devices": devices,
        }

    def export(self, base_dir: PathLike = "data/experiments") -> Path:
        """Write events/metrics/sync JSONL plus summary/quality under EXP###/."""
        if self._active:
            raise RuntimeError("finish() the experiment before export()")

        root = Path(base_dir) / self.experiment_id
        root.mkdir(parents=True, exist_ok=True)

        events_path = root / "events.jsonl"
        metrics_path = root / "metrics.jsonl"
        sync_path = root / "sync_measurements.jsonl"
        samples_path = root / "sync_samples.jsonl"
        results_path = root / "sync_results.jsonl"
        time_series_path = root / "sync_time_series.jsonl"
        calibration_path = root / "calibration_report.json"
        summary_path = root / "summary.json"
        quality_path = root / "quality_summary.json"

        with events_path.open("w", encoding="utf-8") as fh:
            for record in self.events:
                fh.write(json.dumps(record, separators=(",", ":")))
                fh.write("\n")

        with metrics_path.open("w", encoding="utf-8") as fh:
            for record in self.metrics:
                fh.write(json.dumps(record, separators=(",", ":")))
                fh.write("\n")

        with sync_path.open("w", encoding="utf-8") as fh:
            for record in self.sync_measurements:
                fh.write(json.dumps(record, separators=(",", ":")))
                fh.write("\n")

        # Sprint 9 alias export for measurement-validation experiments.
        with samples_path.open("w", encoding="utf-8") as fh:
            for record in self.sync_measurements:
                fh.write(json.dumps(record, separators=(",", ":")))
                fh.write("\n")

        with results_path.open("w", encoding="utf-8") as fh:
            for record in self.sync_results:
                fh.write(json.dumps(record, separators=(",", ":")))
                fh.write("\n")

        with time_series_path.open("w", encoding="utf-8") as fh:
            for record in self.sync_time_series:
                fh.write(json.dumps(record, separators=(",", ":")))
                fh.write("\n")

        quality = self._quality_by_device()
        summary = self.summary()
        with summary_path.open("w", encoding="utf-8") as fh:
            json.dump(summary, fh, indent=2, sort_keys=True)
            fh.write("\n")

        with quality_path.open("w", encoding="utf-8") as fh:
            json.dump(quality, fh, indent=2, sort_keys=True)
            fh.write("\n")

        if self.sync_results:
            calibration = self.build_calibration_report()
            with calibration_path.open("w", encoding="utf-8") as fh:
                json.dump(calibration, fh, indent=2, sort_keys=True)
                fh.write("\n")

        logger.info("[EXPERIMENT] Exported %s → %s", self.experiment_id, root)
        return root
