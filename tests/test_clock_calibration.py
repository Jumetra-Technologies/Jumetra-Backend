"""Sprint 12 — clock calibration and drift measurement tests."""

import json

from engine.experiments import ExperimentSession
from engine.synchronization import (
    ClockCalibrationReport,
    ClockDriftEstimator,
    SynchronizationResult,
)
from engine.time import ClockModel, SimulationClock, TimestampService, set_timestamp_service


def _result(
    device_id: str,
    offset: float,
    ts: int,
    *,
    confidence: float = 0.8,
) -> SynchronizationResult:
    return SynchronizationResult(
        device_id=device_id,
        estimated_offset=offset,
        sample_count=10,
        selected_samples=3,
        confidence=confidence,
        timestamp=ts,
        algorithm_used="cristian",
    )


class TestClockModel:
    def test_predict_extrapolates_drift(self):
        model = ClockModel(clock_id="esp32_01")
        model.update_measurement(100.0, at_time_ms=1000, uncertainty=2.0)
        model.update_measurement(110.0, at_time_ms=2000, uncertainty=1.5)
        assert model.drift_rate == 0.01  # 10 ms offset / 1000 ms
        assert model.predict(3000) == 120.0
        assert model.initial_offset == 100.0
        assert model.current_offset == 110.0

    def test_reset_clears_state(self):
        model = ClockModel(clock_id="d1")
        model.update_measurement(5.0, at_time_ms=100)
        model.reset()
        assert model.current_offset == 0.0
        assert model.last_update == 0
        assert model.predict(500) == 0.0

    def test_round_trip(self):
        model = ClockModel(clock_id="d1")
        model.update_measurement(42.0, at_time_ms=5000)
        restored = ClockModel.from_dict(model.to_dict())
        assert restored.clock_id == "d1"
        assert restored.current_offset == 42.0


class TestClockDriftEstimator:
    def test_linear_drift(self):
        # offset grows 0.002 ms per ms host time
        results = [
            _result("esp32_01", 100.0, 10_000),
            _result("esp32_01", 120.0, 20_000),
            _result("esp32_01", 140.0, 30_000),
            _result("esp32_01", 160.0, 40_000),
        ]
        drift = ClockDriftEstimator().estimate(results)
        assert drift.device_id == "esp32_01"
        assert drift.sample_count == 4
        assert drift.initial_offset == 100.0
        assert drift.final_offset == 160.0
        assert drift.duration_ms == 30_000
        assert abs(drift.drift_rate - 0.002) < 1e-6

    def test_single_sample_zero_drift(self):
        drift = ClockDriftEstimator().estimate([_result("d1", 50.0, 1000)])
        assert drift.drift_rate == 0.0
        assert drift.initial_offset == 50.0


class TestClockCalibrationReport:
    def test_from_results_and_export(self, tmp_path):
        results = [
            _result("esp32_01", 80.0, 1000),
            _result("esp32_01", 90.0, 6000),
            _result("esp32_01", 100.0, 11_000),
        ]
        report = ClockCalibrationReport.from_results(
            results, experiment_id="EXP12A", metadata={"scenario": "drift_probe"}
        )
        assert report.device_id == "esp32_01"
        assert report.initial_offset == 80.0
        assert report.final_offset == 100.0
        assert report.sample_count == 3
        assert report.drift_rate > 0
        assert 0.0 <= report.confidence <= 1.0

        path = report.export_json(tmp_path / "calibration_report.json")
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["experiment_id"] == "EXP12A"
        assert data["drift_rate"] == report.drift_rate


class TestLongRunningExperiment:
    def setup_method(self):
        self.clock = SimulationClock(start_ms=50_000)
        set_timestamp_service(TimestampService(clock=self.clock))

    def teardown_method(self):
        set_timestamp_service(None)

    def test_duration_experiment_and_time_series_export(self, tmp_path):
        session = ExperimentSession(name="drift_calibration", experiment_id="EXP12B")
        session.start_duration(duration_ms=5000, sync_interval_ms=1000, devices=["esp32_01"])

        step = [0]

        def sync_fn() -> SynchronizationResult:
            offset = 100.0 + step[0] * 2.0
            ts = self.clock.now()
            step[0] += 1
            return _result("esp32_01", offset, ts)

        points = session.run_periodic_sync(
            sync_fn,
            interval_ms=1000,
            duration_ms=5000,
            advance_clock=self.clock.advance,
        )
        assert len(points) == 5
        assert len(session.sync_time_series) == 5
        assert session.sync_time_series[0]["sequence"] == 0
        assert session.is_duration_complete()

        session.finish()
        root = session.export(base_dir=tmp_path / "experiments")

        ts_lines = (root / "sync_time_series.jsonl").read_text(encoding="utf-8").strip().splitlines()
        assert len(ts_lines) == 5

        cal = json.loads((root / "calibration_report.json").read_text(encoding="utf-8"))
        assert cal["device_id"] == "esp32_01"
        assert cal["sample_count"] == 5
        assert cal["initial_offset"] == 100.0
        assert cal["final_offset"] == 108.0
        assert cal["drift_rate"] > 0

        summary = json.loads((root / "summary.json").read_text(encoding="utf-8"))
        assert summary["sync_time_series_count"] == 5
        assert summary["planned_duration_ms"] == 5000

    def test_clock_model_tracks_periodic_results(self):
        model = ClockModel(clock_id="esp32_01")
        session = ExperimentSession(name="model_track")
        session.start_duration(3000, devices=["esp32_01"])

        for i in range(3):
            self.clock.advance(1000)
            result = _result("esp32_01", 50.0 + i * 5.0, self.clock.now())
            session.record_sync_time_point(result)
            model.update_measurement(result.estimated_offset, result.timestamp)

        assert model.drift_rate == 0.005
        assert model.predict(self.clock.now() + 1000) == model.current_offset + 5.0
