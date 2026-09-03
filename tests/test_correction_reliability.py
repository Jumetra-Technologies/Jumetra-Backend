"""Sprint 17 — correction reliability, recovery, and fault injection tests."""

from __future__ import annotations

import json

import pytest

from engine.devices.manager import DeviceManager
from engine.devices.virtual import VirtualLED
from engine.events import EventBus
from engine.protocol.correction import SyncCorrectionResponse
from engine.protocol.reliability import WireReliabilityConfig, WireReliabilityPolicy
from engine.synchronization import SyncSession, SyncState, SynchronizationManager, SynchronizationStorage
from engine.synchronization.adjuster.physical_limits import PhysicalCorrectionLimits
from engine.synchronization.health_monitor import CorrectionHealthMonitor
from engine.synchronization.physical_bridge import PhysicalCorrectionBridge
from engine.synchronization.transactions import (
    CorrectionTransactionStorage,
    RecoveryAction,
    TransactionState,
    UnknownCorrectionTransaction,
)
from engine.synchronization.transactions.manager import CorrectionTransactionManager
from engine.time import SimulationClock, TimestampService, set_timestamp_service


def _ready_session(device_id: str = "virt_rel") -> SyncSession:
    session = SyncSession(device_id=device_id)
    session.begin()
    session.transition_to(SyncState.CALIBRATED)
    session.enter_monitoring()
    session.transition_to(SyncState.CORRECTION_READY)
    return session


def _bridge_setup(tmp_path, clock: SimulationClock, *, reliability: WireReliabilityPolicy | None = None):
    bus = EventBus()
    dm = DeviceManager()
    device = VirtualLED("virt_rel")
    device.metadata["clock_offset"] = 50
    dm.register_device(device)
    sync_manager = SynchronizationManager(bus, device_manager=dm, echo_virtual=True)
    bus.register_subscriber(sync_manager)
    sync_storage = SynchronizationStorage(tmp_path / "sync")
    limits = PhysicalCorrectionLimits(stabilization_period_ms=0, cooldown_period_ms=0)
    bridge = PhysicalCorrectionBridge(
        sync_manager,
        storage=sync_storage,
        limits=limits,
        reliability=reliability,
        timestamp_service=TimestampService(clock=clock),
    )
    return bridge, device, sync_manager, sync_storage


class TestTransactionPersistence:
    def test_save_and_load_unfinished(self, tmp_path):
        storage = CorrectionTransactionStorage(tmp_path / "sync")
        manager = CorrectionTransactionManager(storage=storage)
        txn = manager.create("d1", 5.0, offset_before=20.0, timestamp=1000)
        manager.mark_sent(txn.transaction_id, sent_at=1001)

        loaded = storage.load_unfinished()
        assert len(loaded) == 1
        assert loaded[0].transaction_id == txn.transaction_id
        assert loaded[0].state == TransactionState.SENT

        raw = json.loads(storage.transactions_path.read_text())
        assert "accumulated_by_device" in raw
        assert txn.transaction_id in raw["transactions"]

    def test_terminal_not_unfinished(self, tmp_path):
        storage = CorrectionTransactionStorage(tmp_path / "sync")
        manager = CorrectionTransactionManager(storage=storage)
        txn = manager.create("d1", 2.0)
        manager.mark_sent(txn.transaction_id)
        manager.mark_applied(
            txn.transaction_id,
            SyncCorrectionResponse(
                transaction_id=txn.transaction_id,
                device_id="d1",
                correction_step=2.0,
                timestamp=100,
            ),
        )
        manager.start_verification(txn.transaction_id)
        manager.complete_verification(txn.transaction_id, offset_after=0.0, improvement=2.0)
        assert storage.load_unfinished() == []


class TestWireReliability:
    def test_backoff_increases(self):
        policy = WireReliabilityPolicy(
            WireReliabilityConfig(initial_backoff_ms=100, backoff_multiplier=2.0)
        )
        assert policy.backoff_delay_ms(1) == 100
        assert policy.backoff_delay_ms(2) == 200
        assert policy.backoff_delay_ms(3) == 400

    def test_timeout_and_retry(self):
        policy = WireReliabilityPolicy(WireReliabilityConfig(timeout_ms=1000, max_retries=2))
        assert policy.is_timed_out(1000, 1500) is False
        assert policy.is_timed_out(1000, 2001) is True
        assert policy.should_retry(0) is True
        assert policy.should_retry(1) is True
        assert policy.should_retry(2) is False


class TestCorrectionHealthMonitor:
    def test_reliability_score(self):
        monitor = CorrectionHealthMonitor()
        monitor.record_success(improvement=5.0)
        monitor.record_success(improvement=3.0)
        monitor.record_failure()
        monitor.record_rollback()
        report = monitor.report()
        assert report.successful_corrections == 2
        assert report.failed_corrections == 1
        assert report.rollback_count == 1
        assert report.average_improvement == pytest.approx(4.0)
        assert report.reliability_score == pytest.approx(2 / 3)


class TestFaultInjection:
    def setup_method(self):
        self.clock = SimulationClock(start_ms=500_000)
        set_timestamp_service(TimestampService(clock=self.clock))

    def teardown_method(self):
        set_timestamp_service(None)

    def test_lost_response_timeout_and_fail(self, tmp_path):
        reliability = WireReliabilityPolicy(
            WireReliabilityConfig(timeout_ms=500, max_retries=1)
        )
        bridge, _, _, _ = _bridge_setup(tmp_path, self.clock, reliability=reliability)
        sent = []

        def capture(wire):
            sent.append(wire)

        bridge.send = capture
        session = _ready_session()
        txn = bridge.txn_manager.create("virt_rel", 5.0, offset_before=50.0)
        bridge.txn_manager.mark_sent(txn.transaction_id, sent_at=self.clock.now())

        self.clock.advance(600)
        results = bridge.poll_pending_wire()
        assert results[0].action == RecoveryAction.RETRIED_SEND
        assert bridge.txn_manager.get(txn.transaction_id).metadata["retry_count"] == 1

        self.clock.advance(600)
        bridge.poll_pending_wire()
        assert bridge.txn_manager.get(txn.transaction_id).state == TransactionState.FAILED

    def test_duplicate_response_idempotent(self, tmp_path):
        bridge, _, _, _ = _bridge_setup(tmp_path, self.clock)
        txn = bridge.txn_manager.create("virt_rel", 4.0)
        bridge.txn_manager.mark_sent(txn.transaction_id)
        resp = SyncCorrectionResponse(
            transaction_id=txn.transaction_id,
            device_id="virt_rel",
            correction_step=4.0,
            timestamp=self.clock.now(),
        )
        bridge.handle_correction_response(resp)
        bridge.handle_correction_response(resp)
        assert bridge.txn_manager.get(txn.transaction_id).state == TransactionState.APPLIED

    def test_invalid_transaction_rejected(self, tmp_path):
        bridge, _, _, _ = _bridge_setup(tmp_path, self.clock)
        with pytest.raises(UnknownCorrectionTransaction):
            bridge.handle_correction_response(
                SyncCorrectionResponse(
                    transaction_id="corr_missing",
                    device_id="virt_rel",
                    correction_step=1.0,
                    timestamp=self.clock.now(),
                )
            )

    def test_recovery_applied_continues_verification(self, tmp_path):
        bridge, device, _, _ = _bridge_setup(tmp_path, self.clock)
        txn = bridge.txn_manager.create("virt_rel", 10.0, offset_before=50.0)
        bridge.txn_manager.mark_sent(txn.transaction_id)
        bridge.txn_manager.mark_applied(
            txn.transaction_id,
            SyncCorrectionResponse(
                transaction_id=txn.transaction_id,
                device_id="virt_rel",
                correction_step=10.0,
                timestamp=self.clock.now(),
            ),
        )
        device.metadata["clock_offset"] = 35

        bridge2, device2, _, _ = _bridge_setup(tmp_path, self.clock)
        device2.metadata["clock_offset"] = 35
        bridge2.load_persisted_transactions()
        results = bridge2.recover_on_startup()
        assert len(results) == 1
        assert results[0].action == RecoveryAction.CONTINUED_VERIFICATION
        assert results[0].final_state == TransactionState.COMPLETED

    def test_recovery_sent_retries(self, tmp_path):
        reliability = WireReliabilityPolicy(
            WireReliabilityConfig(timeout_ms=100, max_retries=2)
        )
        bridge, _, _, _ = _bridge_setup(tmp_path, self.clock, reliability=reliability)
        sent = []

        def capture(wire):
            sent.append(wire)

        txn = bridge.txn_manager.create("virt_rel", 3.0)
        bridge.txn_manager.mark_sent(txn.transaction_id, sent_at=self.clock.now())
        bridge.send = capture

        self.clock.advance(200)
        bridge2, _, _, _ = _bridge_setup(tmp_path, self.clock, reliability=reliability)
        bridge2.send = capture
        bridge2.load_persisted_transactions()
        results = bridge2.recover_on_startup()
        assert results[0].action == RecoveryAction.RETRIED_SEND
        assert len(sent) >= 1

    def test_recovery_verifying_resumes(self, tmp_path):
        bridge, device, _, _ = _bridge_setup(tmp_path, self.clock)
        txn = bridge.txn_manager.create("virt_rel", 8.0, offset_before=50.0)
        bridge.txn_manager.mark_sent(txn.transaction_id)
        bridge.txn_manager.mark_applied(
            txn.transaction_id,
            SyncCorrectionResponse(
                transaction_id=txn.transaction_id,
                device_id="virt_rel",
                correction_step=8.0,
                timestamp=self.clock.now(),
            ),
        )
        bridge.txn_manager.start_verification(txn.transaction_id)
        device.metadata["clock_offset"] = 38

        bridge2, device2, _, _ = _bridge_setup(tmp_path, self.clock)
        device2.metadata["clock_offset"] = 38
        bridge2.load_persisted_transactions()
        results = bridge2.recover_on_startup()
        assert results[0].action == RecoveryAction.RESUMED_VERIFICATION
        assert results[0].final_state == TransactionState.COMPLETED

    def test_rollback_recovery_after_failed_verify(self, tmp_path):
        bridge, _, _, _ = _bridge_setup(tmp_path, self.clock)
        session = _ready_session()

        def simulate(txn):
            return SyncCorrectionResponse(
                transaction_id=txn.transaction_id,
                device_id=txn.device_id,
                correction_step=txn.correction_step,
                timestamp=self.clock.now(),
            )

        final = bridge.execute_correction(
            session, offset=50.0, confidence=0.9, simulate_response=simulate
        )
        assert final.state == TransactionState.ROLLED_BACK
        report = bridge.health_report()
        assert report.rollback_count == 1
        assert report.failed_corrections >= 1

    def test_device_restart_recovery_from_sent(self, tmp_path):
        """Simulate crash after SENT with no response — restart and fail on timeout."""
        reliability = WireReliabilityPolicy(
            WireReliabilityConfig(timeout_ms=50, max_retries=0)
        )
        bridge, _, _, _ = _bridge_setup(tmp_path, self.clock, reliability=reliability)
        txn = bridge.txn_manager.create("virt_rel", 2.0, offset_before=30.0)
        bridge.txn_manager.mark_sent(txn.transaction_id, sent_at=self.clock.now())

        bridge2, _, _, _ = _bridge_setup(tmp_path, self.clock, reliability=reliability)
        bridge2.load_persisted_transactions()
        self.clock.advance(100)
        results = bridge2.recover_on_startup()
        assert results[0].action == RecoveryAction.FAILED_TIMEOUT
        assert bridge2.txn_manager.get(txn.transaction_id).state == TransactionState.FAILED

    def test_health_report_example(self, tmp_path):
        bridge, device, _, _ = _bridge_setup(tmp_path, self.clock)
        session = _ready_session()

        def simulate(txn):
            device.metadata["clock_offset"] = 30
            return SyncCorrectionResponse(
                transaction_id=txn.transaction_id,
                device_id=txn.device_id,
                correction_step=txn.correction_step,
                timestamp=self.clock.now(),
            )

        bridge.execute_correction(session, offset=50.0, confidence=0.9, simulate_response=simulate)
        report = bridge.health_report()
        example = report.to_dict()
        assert example["successful_corrections"] == 1
        assert example["reliability_score"] == 1.0
        assert example["average_improvement"] > 0
