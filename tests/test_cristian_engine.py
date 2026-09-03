"""Sprint 11 — Cristian synchronization engine (estimation only)."""

import json

import pytest

from engine.experiments import ExperimentSession
from engine.synchronization import (
    ClockAdjuster,
    ClockObservation,
    ClockOffsetEstimate,
    CristianOffsetEstimator,
    FilterMode,
    MinimumRTTSelector,
    NullClockAdjuster,
    OffsetFilter,
    SynchronizationEngine,
    SynchronizationResult,
)
from engine.time import SimulationClock, TimestampService, set_timestamp_service


def _obs(
    device_id: str = "esp32_01",
    local: int = 1000,
    remote: int = 1100,
    rtt: int = 10,
    *,
    request_id: str = "sync_1",
) -> ClockObservation:
    # Matches manager convention: offset = remote - (local + RTT/2)
    offset = float(remote) - (float(local) + rtt / 2.0)
    return ClockObservation(
        device_id=device_id,
        local_timestamp=local,
        server_timestamp=remote,
        round_trip_time=rtt,
        estimated_offset=offset,
        measurement_time=local + rtt,
        request_time=local,
        response_time=local + rtt,
        request_id=request_id,
    )


class TestCristianCalculation:
    def test_basic_formula(self):
        est = CristianOffsetEstimator()
        # host=1000, device=1100, RTT=10 → offset = 1100 - (1000 + 5) = 95
        result = est.estimate_from_fields(
            device_id="esp32_01",
            host_time=1000,
            device_time=1100,
            round_trip_time=10,
        )
        assert result.estimated_offset == 95.0
        assert result.algorithm == "cristian"

    def test_from_observation_matches_stored_offset(self):
        obs = _obs(local=2000, remote=2050, rtt=20)
        estimate = CristianOffsetEstimator().estimate(obs)
        assert estimate.estimated_offset == obs.estimated_offset
        assert estimate.estimated_offset == 2050 - (2000 + 10)

    def test_round_trip_serialize(self):
        estimate = ClockOffsetEstimate(
            device_id="d1",
            estimated_offset=12.5,
            host_time=1,
            device_time=2,
            round_trip_time=4,
        )
        assert ClockOffsetEstimate.from_dict(estimate.to_dict()).to_dict() == estimate.to_dict()


class TestMinimumRTTSelection:
    def test_selects_lowest_rtt(self):
        samples = [
            _obs(rtt=30, request_id="a"),
            _obs(rtt=5, request_id="b"),
            _obs(rtt=12, request_id="c"),
            _obs(rtt=8, request_id="d"),
        ]
        selector = MinimumRTTSelector(top_k=2)
        chosen = selector.select(samples)
        assert [s.round_trip_time for s in chosen] == [5, 8]
        assert selector.select_best(samples).request_id == "b"

    def test_window_and_reject_invalid(self):
        samples = [
            _obs(rtt=1, request_id="old"),
            _obs(rtt=50, request_id="w1"),
            _obs(rtt=40, request_id="w2"),
            _obs(rtt=-1, request_id="bad"),
        ]
        # Negative RTT rejected; window keeps last 3 valid candidates → w1,w2 (bad dropped)
        selector = MinimumRTTSelector(window_size=3, top_k=2, max_rtt=45)
        chosen = selector.select(samples)
        assert [s.request_id for s in chosen] == ["w2"]
        assert selector.is_valid(_obs(rtt=-3)) is False


class TestOffsetFiltering:
    def test_median(self):
        f = OffsetFilter(FilterMode.MEDIAN, window=5)
        assert f.filter([10.0, 100.0, 12.0]) == 12.0

    def test_moving_average(self):
        f = OffsetFilter(FilterMode.MOVING_AVERAGE, window=3)
        assert f.filter([10.0, 20.0, 30.0]) == 20.0
        assert f.push(10.0) == 10.0
        assert f.push(20.0) == 15.0

    def test_kalman_not_implemented(self):
        f = OffsetFilter(FilterMode.KALMAN, window=3)
        with pytest.raises(NotImplementedError):
            f.filter([1.0, 2.0])


class TestSynchronizationEngineAndResult:
    def setup_method(self):
        self.clock = SimulationClock(start_ms=50_000)
        set_timestamp_service(TimestampService(clock=self.clock))

    def teardown_method(self):
        set_timestamp_service(None)

    def test_engine_produces_result(self):
        samples = [
            _obs(local=1000, remote=1100, rtt=40, request_id="1"),
            _obs(local=1100, remote=1205, rtt=10, request_id="2"),
            _obs(local=1200, remote=1300, rtt=12, request_id="3"),
            _obs(local=1300, remote=1400, rtt=50, request_id="4"),
            _obs(local=1400, remote=1502, rtt=8, request_id="5"),
        ]
        engine = SynchronizationEngine(
            selector=MinimumRTTSelector(window_size=10, top_k=3),
            offset_filter=OffsetFilter(FilterMode.MEDIAN, window=3),
            timestamp_service=TimestampService(clock=self.clock),
        )
        result = engine.synchronize(samples, before_offset=samples[0].estimated_offset)
        assert isinstance(result, SynchronizationResult)
        assert result.device_id == "esp32_01"
        assert result.algorithm_used == "cristian"
        assert result.sample_count == 5
        assert result.selected_samples == 3
        assert result.min_rtt_selected == 8
        assert result.before_offset == samples[0].estimated_offset
        assert result.confidence >= 0.0
        # Lowest RTTs: 8, 10, 12 → offsets filtered by median
        assert result.estimated_offset == engine.offset_filter.filter(
            [
                CristianOffsetEstimator().estimate(s).estimated_offset
                for s in MinimumRTTSelector(top_k=3).select(samples)
            ]
        )

    def test_adjuster_interface_not_applied_by_default(self):
        assert issubclass(NullClockAdjuster, ClockAdjuster)
        adjuster = NullClockAdjuster()
        engine = SynchronizationEngine(
            adjuster=adjuster,
            apply_correction=False,
            timestamp_service=TimestampService(clock=self.clock),
        )
        engine.synchronize([_obs(rtt=5)], before_offset=0.0)
        assert adjuster.pending == []

        engine.apply_correction = True
        engine.synchronize([_obs(rtt=5)], before_offset=0.0)
        assert len(adjuster.pending) == 1
        assert adjuster.pending[0]["applied"] is False


class TestExperimentSyncResultExport:
    def setup_method(self):
        self.clock = SimulationClock(start_ms=70_000)
        set_timestamp_service(TimestampService(clock=self.clock))

    def teardown_method(self):
        set_timestamp_service(None)

    def test_records_and_exports_sync_results(self, tmp_path):
        session = ExperimentSession(name="cristian_v1", experiment_id="EXP11A")
        session.start(devices=["esp32_01"])

        samples = [
            _obs(rtt=20, request_id="a"),
            _obs(rtt=6, request_id="b"),
            _obs(rtt=9, request_id="c"),
        ]
        for s in samples:
            session.record_sync_measurement(s)

        engine = SynchronizationEngine(
            selector=MinimumRTTSelector(top_k=2),
            timestamp_service=TimestampService(clock=self.clock),
        )
        result = engine.synchronize(samples, before_offset=samples[0].estimated_offset)
        record = session.record_sync_result(result)

        assert "before_offset" in record
        assert "estimated_offset" in record
        assert record["algorithm_used"] == "cristian"
        assert record["sample_count"] == 3

        session.finish()
        root = session.export(base_dir=tmp_path / "experiments")

        lines = (root / "sync_results.jsonl").read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        exported = json.loads(lines[0])
        assert exported["algorithm_used"] == "cristian"
        assert exported["before_offset"] == samples[0].estimated_offset
        assert exported["estimated_offset"] == result.estimated_offset
        assert exported["sample_count"] == 3

        summary = json.loads((root / "summary.json").read_text(encoding="utf-8"))
        assert summary["sync_result_count"] == 1
        assert summary["sync_results"][0]["algorithm_used"] == "cristian"
