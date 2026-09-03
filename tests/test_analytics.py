"""Sprint 20 — research analytics tests."""

from __future__ import annotations

import json

import pytest

from engine.analytics import (
    AnalyticsEngine,
    DeviceReliabilityScore,
    ExperimentAnalytics,
    ExperimentComparison,
    export_csv_string,
    export_full,
    export_json,
    research_summary,
)


def _sample_experiment(strategy: str = "fixed") -> dict:
    return {
        "experiment_id": f"EXP_{strategy}",
        "name": f"{strategy}_run",
        "strategy": strategy,
        "sync_measurements": [
            {"device_id": "d1", "estimated_offset": 40.0, "round_trip_time": 20},
            {"device_id": "d1", "estimated_offset": 35.0, "round_trip_time": 22},
            {"device_id": "d1", "estimated_offset": 30.0, "round_trip_time": 21},
            {"device_id": "d2", "estimated_offset": 15.0, "round_trip_time": 18},
            {"device_id": "d2", "estimated_offset": 12.0, "round_trip_time": 19},
        ],
        "sync_results": [
            {"device_id": "d1", "offset": 35.0, "drift_rate": 0.002},
            {"device_id": "d2", "offset": 13.0, "drift_rate": 0.001},
        ],
        "events": [
            {
                "device_id": "d1",
                "latencies": {"total_latency": 5.0},
            },
            {
                "device_id": "d2",
                "latencies": {"total_latency": 8.0},
            },
        ],
        "transactions": [
            {"device_id": "d1", "state": "COMPLETED", "improvement": 5.0},
            {"device_id": "d1", "state": "ROLLED_BACK", "improvement": 0.0},
        ],
        "health_reports": [
            {
                "device_id": "d1",
                "successful_corrections": 1,
                "failed_corrections": 1,
                "rollback_count": 1,
                "total_attempts": 2,
                "average_improvement": 2.5,
            }
        ],
        "communication_cost": 10,
    }


class TestAnalyticsEngine:
    def test_load_and_calculate_metrics(self):
        engine = AnalyticsEngine()
        analytics = engine.load_from_dict(_sample_experiment("adaptive"))
        assert isinstance(analytics, ExperimentAnalytics)
        assert len(analytics.devices) == 2
        d1 = analytics.device("d1")
        assert d1 is not None
        assert d1.synchronization.sync_event_count >= 3
        assert d1.synchronization.average_sync_error > 0
        assert d1.correction.correction_attempts >= 1

    def test_generate_research_report(self):
        engine = AnalyticsEngine()
        engine.load_from_dict(_sample_experiment())
        report = engine.generate_report()
        assert report.device_count == 2
        assert report.average_sync_error > 0
        assert report.correction_success_rate >= 0
        assert "p50" in report.latency_distribution
        assert len(report.device_rankings) == 2

    def test_load_from_path(self, tmp_path):
        path = tmp_path / "experiment.json"
        path.write_text(json.dumps(_sample_experiment()), encoding="utf-8")
        engine = AnalyticsEngine()
        analytics = engine.load_from_path(path)
        assert analytics.experiment_id == "EXP_fixed"

    def test_autonomous_metrics_load(self):
        engine = AnalyticsEngine()
        analytics = engine.load_from_autonomous_metrics(
            {
                "strategy_name": "adaptive",
                "sync_operations": 5,
                "communication_cost": 8,
                "correction_attempts": 3,
                "correction_successes": 2,
                "correction_failures": 1,
                "correction_accuracy": 0.667,
                "rollbacks": 1,
                "recovery_events": 0,
            },
            device_id="esp32_01",
        )
        assert analytics.strategy == "adaptive"
        assert len(analytics.devices) == 1
        assert analytics.devices[0].correction.correction_attempts == 3


class TestExperimentComparison:
    def test_compare_fixed_vs_adaptive(self):
        engine = AnalyticsEngine()
        fixed = engine.load_from_dict(_sample_experiment("fixed"))
        engine2 = AnalyticsEngine()
        adaptive_data = _sample_experiment("adaptive")
        adaptive_data["sync_measurements"][-1]["estimated_offset"] = 8.0
        adaptive_data["communication_cost"] = 7
        adaptive_data["transactions"] = [
            {"device_id": "d1", "state": "COMPLETED", "improvement": 8.0},
            {"device_id": "d1", "state": "COMPLETED", "improvement": 6.0},
        ]
        adaptive = engine2.load_from_dict(adaptive_data)

        result = ExperimentComparison.compare(fixed, adaptive)
        assert result.fixed_experiment_id == "EXP_fixed"
        assert result.adaptive_experiment_id == "EXP_adaptive"
        assert isinstance(result.communication_savings, int)
        assert isinstance(result.accuracy_difference, float)

    def test_from_autonomous_reports(self):
        report = {
            "fixed": {
                "strategy_name": "fixed",
                "sync_operations": 5,
                "communication_cost": 10,
                "correction_attempts": 2,
                "correction_successes": 1,
                "correction_accuracy": 0.5,
                "correction_failures": 1,
                "rollbacks": 0,
            },
            "adaptive": {
                "strategy_name": "adaptive",
                "sync_operations": 5,
                "communication_cost": 7,
                "correction_attempts": 2,
                "correction_successes": 2,
                "correction_accuracy": 1.0,
                "correction_failures": 0,
                "rollbacks": 0,
            },
        }
        result = ExperimentComparison.from_autonomous_reports(report)
        assert result.communication_savings == 3
        assert result.accuracy_difference > 0


class TestDeviceReliabilityScore:
    def test_compute_score(self):
        score = DeviceReliabilityScore.compute(
            "d1",
            success_rate=0.9,
            failure_count=1,
            correction_attempts=10,
            rollback_count=1,
            drift_stability=0.8,
            offset_stability=0.85,
        )
        assert 0.0 <= score.score <= 1.0
        assert score.success_rate == 0.9
        assert score.rollback_count == 1

    def test_rank_devices(self):
        scores = [
            DeviceReliabilityScore.compute("a", success_rate=0.5),
            DeviceReliabilityScore.compute("b", success_rate=0.95),
            DeviceReliabilityScore.compute("c", success_rate=0.7),
        ]
        ranked = DeviceReliabilityScore.rank_devices(scores)
        assert ranked[0].device_id == "b"
        assert ranked[-1].device_id == "a"


class TestExport:
    def test_json_export(self, tmp_path):
        engine = AnalyticsEngine()
        engine.load_from_dict(_sample_experiment())
        report = engine.generate_report()
        path = export_json(report.to_dict(), tmp_path / "report.json")
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["experiment_id"] == "EXP_fixed"

    def test_csv_export(self, tmp_path):
        engine = AnalyticsEngine()
        analytics = engine.load_from_dict(_sample_experiment())
        csv_text = export_csv_string(analytics)
        assert "device_id" in csv_text
        assert "d1" in csv_text

    def test_research_summary_text(self):
        engine = AnalyticsEngine()
        engine.load_from_dict(_sample_experiment())
        report = engine.generate_report()
        text = research_summary(report)
        assert "HHIP Research Summary" in text
        assert "Average sync error" in text
        assert "Device reliability ranking" in text

    def test_export_full(self, tmp_path):
        engine = AnalyticsEngine()
        engine.load_from_dict(_sample_experiment())
        paths = export_full(engine, tmp_path / "out", basename="test_run")
        assert paths["json"].exists()
        assert paths["csv"].exists()
        assert paths["summary"].exists()
