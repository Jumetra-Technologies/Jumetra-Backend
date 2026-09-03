"""Sprint 18 — adaptive synchronization intelligence tests."""

from __future__ import annotations

import json

import pytest

from engine.events import EventBus
from engine.synchronization import (
    AdaptiveIntervalStrategy,
    AdaptiveStrategy,
    DeviceSyncProfile,
    DeviceSyncProfileStore,
    FixedIntervalStrategy,
    SyncStrategyComparison,
    SynchronizationCoordinator,
    SynchronizationDecisionEngine,
    SynchronizationManager,
    SynchronizationStorage,
)
from engine.synchronization.intelligence.correction_policy import AdaptiveCorrectionPolicy
from engine.synchronization.intelligence.interval_strategy import AdaptiveIntervalConfig
from engine.synchronization.policy import CorrectionAction
from engine.synchronization.quality import SyncQuality
from engine.time import SimulationClock, TimestampService, set_timestamp_service


def _measurements(count: int = 5) -> list[dict]:
    rows = []
    for i in range(count):
        rows.append(
            {
                "offset": 40.0 - i * 5,
                "drift": 0.002 + i * 0.0001,
                "confidence": 0.9 - i * 0.05,
                "timestamp": 1000 + i * 5000,
                "quality": {
                    "jitter": 2.0 + i,
                    "average_rtt": 20.0,
                    "confidence_score": 0.9 - i * 0.05,
                },
            }
        )
    return rows


class TestAdaptiveIntervalStrategy:
    def test_high_drift_shortens_interval(self):
        strategy = AdaptiveIntervalStrategy()
        stable = strategy.recommend(
            "d1", drift_rate=0.0001, confidence=0.9, rtt_stability=0.95, device_health=0.95
        )
        unstable = strategy.recommend(
            "d1", drift_rate=0.01, confidence=0.9, rtt_stability=0.95, device_health=0.95
        )
        assert unstable.interval_ms < stable.interval_ms

    def test_low_confidence_shortens_interval(self):
        strategy = AdaptiveIntervalStrategy()
        high = strategy.recommend("d1", confidence=0.95, rtt_stability=0.9, device_health=0.9)
        low = strategy.recommend("d1", confidence=0.4, rtt_stability=0.9, device_health=0.9)
        assert low.interval_ms < high.interval_ms

    def test_adaptive_strategy_wrapper(self):
        strategy = AdaptiveStrategy()
        interval = strategy.calculate_next_interval(
            "d1",
            last_interval_ms=5000,
            drift=0.005,
            confidence=0.6,
            quality={"jitter": 5.0, "average_rtt": 20.0, "confidence_score": 0.6},
        )
        assert 1000 <= interval <= 30000

    def test_respects_bounds(self):
        cfg = AdaptiveIntervalConfig(min_interval_ms=2000, max_interval_ms=8000)
        strategy = AdaptiveIntervalStrategy(cfg)
        rec = strategy.recommend("d1", drift_rate=1.0, confidence=0.1, failure_rate=0.9)
        assert rec.interval_ms >= 2000
        rec2 = strategy.recommend("d1", drift_rate=0.0, confidence=1.0, device_health=1.0)
        assert rec2.interval_ms <= 8000


class TestAdaptiveCorrectionPolicy:
    def test_step_scales_with_confidence(self):
        policy = AdaptiveCorrectionPolicy()
        high = policy.recommend_step("d1", 50.0, confidence=0.95, health_score=0.95)
        low = policy.recommend_step("d1", 50.0, confidence=0.4, health_score=0.95)
        assert abs(high.step_ms) > abs(low.step_ms)

    def test_previous_corrections_reduce_step(self):
        policy = AdaptiveCorrectionPolicy()
        first = policy.recommend_step("d1", 50.0, confidence=0.9, previous_corrections=0)
        third = policy.recommend_step("d1", 50.0, confidence=0.9, previous_corrections=3)
        assert abs(third.step_ms) < abs(first.step_ms)

    def test_rejects_unsafe_offset(self):
        policy = AdaptiveCorrectionPolicy()
        rec = policy.recommend_step("d1", 50_000.0, confidence=0.99)
        assert rec.allowed is False
        assert rec.step_ms == 0.0


class TestDeviceSyncProfile:
    def test_record_sync_updates_stability(self):
        profile = DeviceSyncProfile(device_id="esp32_01")
        profile.record_sync(drift=0.001, confidence=0.8, rtt_stability=0.7, timestamp=1000)
        assert profile.sync_event_count == 1
        assert 0.0 < profile.stability_score <= 1.0
        assert profile.average_drift > 0

    def test_failure_rate(self):
        profile = DeviceSyncProfile(device_id="d1")
        profile.record_correction(success=True, timestamp=100)
        profile.record_correction(success=False, timestamp=200)
        assert profile.failure_rate == pytest.approx(0.5)

    def test_store_round_trip(self):
        store = DeviceSyncProfileStore()
        p = store.get("d1")
        p.recommended_interval = 3500
        p.success_rate = 0.8
        raw = store.to_dict()
        store2 = DeviceSyncProfileStore()
        store2.load(raw)
        assert store2.get("d1").recommended_interval == 3500


class TestSynchronizationDecisionEngine:
    def setup_method(self):
        self.clock = SimulationClock(start_ms=100_000)
        set_timestamp_service(TimestampService(clock=self.clock))

    def teardown_method(self):
        set_timestamp_service(None)

    def test_produces_plan(self):
        engine = SynchronizationDecisionEngine()
        quality = SyncQuality.from_samples("d1", [20, 22, 21], [45, 44, 43])
        plan = engine.decide(
            "d1",
            offset=45.0,
            drift=0.001,
            confidence=0.85,
            quality=quality.to_dict(),
            health_score=0.9,
            timestamp=self.clock.now(),
        )
        assert plan.recommended_interval_ms >= 1000
        assert plan.correction_action == CorrectionAction.READY
        assert plan.recommended_correction_step != 0.0
        assert plan.correction_action in CorrectionAction
        assert plan.profile is not None
        assert plan.reason

    def test_sample_adaptive_decision_dict(self):
        engine = SynchronizationDecisionEngine()
        plan = engine.decide(
            "esp32_01",
            offset=32.0,
            drift=0.003,
            confidence=0.72,
            quality={"jitter": 4.0, "average_rtt": 18.0, "confidence_score": 0.72},
            health_score=0.85,
            timestamp=100_000,
        )
        sample = plan.to_dict()
        assert sample["device_id"] == "esp32_01"
        assert "recommended_interval_ms" in sample
        assert "recommended_correction_step" in sample


class TestSyncStrategyComparison:
    def test_compare_fixed_vs_adaptive(self):
        comparison = SyncStrategyComparison(fixed_interval_ms=5000)
        report = comparison.compare("d1", _measurements(6))
        data = report.to_dict()
        assert "fixed" in data and "adaptive" in data
        assert report.fixed.strategy_name == "fixed"
        assert report.adaptive.strategy_name == "adaptive"
        assert report.fixed.sync_event_count == report.adaptive.sync_event_count == 6

    def test_adaptive_communication_cost_can_differ(self):
        comparison = SyncStrategyComparison(fixed_interval_ms=5000)
        stable = [
            {
                "offset": 8.0,
                "drift": 0.0001,
                "confidence": 0.95,
                "timestamp": 1000 + i * 5000,
                "quality": {"jitter": 1.0, "average_rtt": 20.0},
            }
            for i in range(10)
        ]
        report = comparison.compare("d1", stable, health_score=0.95)
        assert report.adaptive.average_interval_ms >= 1000


class TestCoordinatorAdaptiveIntegration:
    def setup_method(self):
        self.clock = SimulationClock(start_ms=200_000)
        set_timestamp_service(TimestampService(clock=self.clock))

    def teardown_method(self):
        set_timestamp_service(None)

    def test_adaptive_schedule_uses_decision_engine(self, tmp_path):
        bus = EventBus()
        manager = SynchronizationManager(
            bus, timestamp_service=TimestampService(clock=self.clock), echo_virtual=False
        )
        bus.register_subscriber(manager)
        storage = SynchronizationStorage(tmp_path / "sync")
        coord = SynchronizationCoordinator(
            manager,
            storage,
            strategy=AdaptiveStrategy(),
            default_interval_ms=5000,
            timestamp_service=TimestampService(clock=self.clock),
        )
        coord.schedule_device("virt_01", interval_ms=5000, adaptive=True)
        coord.startup()
        coord.shutdown()

        profiles = storage.load_sync_profiles()
        assert isinstance(profiles, dict)

    def test_profile_persistence(self, tmp_path):
        storage = SynchronizationStorage(tmp_path / "sync")
        store = DeviceSyncProfileStore()
        p = store.get("dev1")
        p.stability_score = 0.77
        p.recommended_interval = 4200
        storage.save_sync_profiles(store.to_dict())
        loaded = storage.load_sync_profiles()
        assert loaded["dev1"]["stability_score"] == pytest.approx(0.77)
