"""Sprint 16 — physical correction bridge tests."""

from __future__ import annotations

import json

import pytest

from engine.devices.manager import DeviceManager
from engine.devices.virtual import VirtualLED
from engine.events import EventBus
from engine.protocol.correction import SyncCorrectionRequest, SyncCorrectionResponse
from engine.protocol.correction_wire import (
    build_wire_correction_request,
    build_wire_correction_response,
    event_payload_from_wire_correction_response,
)
from engine.protocol.messages import MessageType, validate_message
from engine.synchronization import SyncSession, SyncState, SynchronizationManager, SynchronizationStorage
from engine.synchronization.adjuster.physical_limits import PhysicalCorrectionLimits
from engine.synchronization.physical_bridge import PhysicalCorrectionBridge
from engine.synchronization.transactions import (
    CorrectionTransactionManager,
    InvalidTransactionTransition,
    TransactionState,
)
from engine.time import SimulationClock, TimestampService, set_timestamp_service


def _ready_session(device_id: str = "esp32_01") -> SyncSession:
    session = SyncSession(device_id=device_id)
    session.begin()
    session.transition_to(SyncState.CALIBRATED)
    session.enter_monitoring()
    session.transition_to(SyncState.CORRECTION_READY)
    return session


class FirmwareCorrectionSimulator:
    """In-process stand-in for ESP32 sync_agent correction handling."""

    def __init__(self, device_id: str = "esp32_01") -> None:
        self.device_id = device_id
        self.software_clock_offset = 0.0
        self.accumulated = 0.0

    def handle_wire_request(self, wire: dict) -> dict:
        payload = wire.get("payload") or {}
        step = float(payload.get("correction_step", 0.0))
        txn_id = str(payload.get("transaction_id") or wire.get("message_id"))
        self.software_clock_offset -= step
        self.accumulated += abs(step)
        response = SyncCorrectionResponse(
            transaction_id=txn_id,
            device_id=self.device_id,
            correction_step=step,
            timestamp=int(payload.get("timestamp", 0)),
            applied=True,
            accumulated_correction=self.accumulated,
            software_clock_offset=self.software_clock_offset,
        )
        return build_wire_correction_response(response)


class TestCorrectionProtocol:
    def test_request_round_trip(self):
        req = SyncCorrectionRequest.create("esp32_01", -5.0, 100_000)
        restored = SyncCorrectionRequest.from_json(req.to_json())
        assert restored.device_id == "esp32_01"
        assert restored.correction_step == -5.0
        assert restored.transaction_id == req.transaction_id

    def test_response_round_trip(self):
        resp = SyncCorrectionResponse(
            transaction_id="corr_abc",
            device_id="esp32_01",
            correction_step=-5.0,
            timestamp=100_001,
            accumulated_correction=5.0,
            software_clock_offset=-5.0,
        )
        restored = SyncCorrectionResponse.from_dict(json.loads(resp.to_json()))
        assert restored.applied is True
        assert restored.accumulated_correction == 5.0

    def test_wire_envelope_validates(self):
        req = SyncCorrectionRequest.create("esp32_01", 3.0, 50_000)
        wire = build_wire_correction_request(req)
        assert wire["type"] == MessageType.SYNC_CORRECTION_REQUEST
        assert validate_message(wire) == []
        payload = wire["payload"]
        assert payload["transaction_id"]
        assert payload["device_id"] == "esp32_01"
        assert payload["correction_step"] == 3.0
        assert payload["timestamp"] == 50_000

    def test_wire_response_normalization(self):
        resp = SyncCorrectionResponse(
            transaction_id="corr_x",
            device_id="esp32_01",
            correction_step=2.0,
            timestamp=99,
        )
        wire = build_wire_correction_response(resp)
        normalized = event_payload_from_wire_correction_response(wire)
        assert normalized["transaction_id"] == "corr_x"
        assert normalized["device_id"] == "esp32_01"


class TestCorrectionTransactionManager:
    def setup_method(self):
        self.clock = SimulationClock(start_ms=100_000)
        set_timestamp_service(TimestampService(clock=self.clock))
        self.limits = PhysicalCorrectionLimits(
            max_step_ms=10.0,
            max_accumulated_correction_ms=100.0,
            cooldown_period_ms=0,
        )
        self.manager = CorrectionTransactionManager(limits=self.limits)

    def teardown_method(self):
        set_timestamp_service(None)

    def test_lifecycle_happy_path(self):
        txn = self.manager.create("d1", 5.0, offset_before=20.0)
        assert txn.state == TransactionState.CREATED
        self.manager.mark_sent(txn.transaction_id)
        self.manager.mark_applied(
            txn.transaction_id,
            SyncCorrectionResponse(
                transaction_id=txn.transaction_id,
                device_id="d1",
                correction_step=5.0,
                timestamp=100_001,
                accumulated_correction=5.0,
            ),
        )
        self.manager.start_verification(txn.transaction_id)
        done = self.manager.complete_verification(
            txn.transaction_id, offset_after=15.0, improvement=5.0
        )
        assert done.state == TransactionState.COMPLETED
        assert done.verified is True

    def test_rejects_oversized_step(self):
        with pytest.raises(ValueError, match="max_step_ms"):
            self.manager.create("d1", 25.0)

    def test_rejects_cooldown(self):
        limits = PhysicalCorrectionLimits(cooldown_period_ms=5_000)
        mgr = CorrectionTransactionManager(limits=limits)
        mgr.create("d1", 2.0, timestamp=100_000)
        mgr._last_correction_time["d1"] = 100_000
        with pytest.raises(ValueError, match="cooldown"):
            mgr.create("d1", 2.0, timestamp=102_000)

    def test_invalid_transition(self):
        txn = self.manager.create("d1", 1.0)
        with pytest.raises(InvalidTransactionTransition):
            self.manager.complete_verification(txn.transaction_id, offset_after=0.0, improvement=0.0)

    def test_rollback_from_failed(self):
        txn = self.manager.create("d1", 4.0)
        self.manager.mark_sent(txn.transaction_id)
        self.manager.fail(txn.transaction_id, "timeout")
        rolled = self.manager.rollback(txn.transaction_id, reason="operator abort")
        assert rolled.state == TransactionState.ROLLED_BACK


class TestPhysicalVerification:
    def setup_method(self):
        self.clock = SimulationClock(start_ms=200_000)
        set_timestamp_service(TimestampService(clock=self.clock))
        self.bus = EventBus()
        self.dm = DeviceManager()
        self.device = VirtualLED("virt_corr")
        self.device.metadata["clock_offset"] = 50
        self.dm.register_device(self.device)
        self.sync_manager = SynchronizationManager(
            self.bus, device_manager=self.dm, echo_virtual=True
        )
        self.bus.register_subscriber(self.sync_manager)
        self.limits = PhysicalCorrectionLimits(stabilization_period_ms=0, cooldown_period_ms=0)
        self.txn_manager = CorrectionTransactionManager(limits=self.limits)

    def teardown_method(self):
        set_timestamp_service(None)

    def test_verification_detects_improvement(self):
        txn = self.txn_manager.create("virt_corr", 10.0, offset_before=50.0)
        self.txn_manager.mark_sent(txn.transaction_id)
        self.txn_manager.mark_applied(
            txn.transaction_id,
            SyncCorrectionResponse(
                transaction_id=txn.transaction_id,
                device_id="virt_corr",
                correction_step=10.0,
                timestamp=self.clock.now(),
            ),
        )
        self.device.metadata["clock_offset"] = 35
        from engine.synchronization.physical_verification import PhysicalVerificationLoop

        loop = PhysicalVerificationLoop(self.sync_manager, self.txn_manager, limits=self.limits)
        result = loop.verify_transaction(self.txn_manager.get(txn.transaction_id))
        assert result.verified is True
        assert result.improvement == pytest.approx(15.0, abs=1.0)
        assert self.txn_manager.get(txn.transaction_id).state == TransactionState.COMPLETED

    def test_verification_fails_without_improvement(self):
        txn = self.txn_manager.create("virt_corr", 5.0, offset_before=50.0)
        self.txn_manager.mark_sent(txn.transaction_id)
        self.txn_manager.mark_applied(
            txn.transaction_id,
            SyncCorrectionResponse(
                transaction_id=txn.transaction_id,
                device_id="virt_corr",
                correction_step=5.0,
                timestamp=self.clock.now(),
            ),
        )
        from engine.synchronization.physical_verification import PhysicalVerificationLoop

        loop = PhysicalVerificationLoop(self.sync_manager, self.txn_manager, limits=self.limits)
        result = loop.verify_transaction(self.txn_manager.get(txn.transaction_id))
        assert result.verified is False
        assert self.txn_manager.get(txn.transaction_id).state == TransactionState.FAILED


class TestPhysicalCorrectionBridge:
    def setup_method(self):
        self.clock = SimulationClock(start_ms=300_000)
        set_timestamp_service(TimestampService(clock=self.clock))
        self.bus = EventBus()
        self.dm = DeviceManager()
        self.device = VirtualLED("virt_bridge")
        self.device.metadata["clock_offset"] = 40
        self.dm.register_device(self.device)
        self.sync_manager = SynchronizationManager(
            self.bus, device_manager=self.dm, echo_virtual=True
        )
        self.bus.register_subscriber(self.sync_manager)

    def teardown_method(self):
        set_timestamp_service(None)

    def test_execute_correction_completes(self, tmp_path):
        storage = SynchronizationStorage(tmp_path / "sync")
        limits = PhysicalCorrectionLimits(
            max_step_ms=10.0, stabilization_period_ms=0, cooldown_period_ms=0
        )
        bridge = PhysicalCorrectionBridge(
            self.sync_manager, storage=storage, limits=limits
        )
        session = _ready_session("virt_bridge")

        def simulate(txn):
            self.device.metadata["clock_offset"] = 30
            return SyncCorrectionResponse(
                transaction_id=txn.transaction_id,
                device_id=txn.device_id,
                correction_step=txn.correction_step,
                timestamp=self.clock.now(),
                accumulated_correction=abs(txn.correction_step),
            )

        final = bridge.execute_correction(
            session, offset=40.0, confidence=0.9, simulate_response=simulate
        )
        assert final.state == TransactionState.COMPLETED
        events = [json.loads(l) for l in storage.decisions_path.read_text().strip().splitlines()]
        event_names = [e["event"] for e in events]
        assert "correction_attempt" in event_names
        assert "correction_applied" in event_names
        assert "correction_verified" in event_names

    def test_execute_correction_rollback_on_failed_verify(self, tmp_path):
        storage = SynchronizationStorage(tmp_path / "sync")
        limits = PhysicalCorrectionLimits(stabilization_period_ms=0, cooldown_period_ms=0)
        bridge = PhysicalCorrectionBridge(
            self.sync_manager, storage=storage, limits=limits
        )
        session = _ready_session("virt_bridge")

        def simulate(txn):
            return SyncCorrectionResponse(
                transaction_id=txn.transaction_id,
                device_id=txn.device_id,
                correction_step=txn.correction_step,
                timestamp=self.clock.now(),
            )

        final = bridge.execute_correction(
            session, offset=40.0, confidence=0.9, simulate_response=simulate
        )
        assert final.state == TransactionState.ROLLED_BACK


class TestFirmwareMessageSimulation:
    def test_simulator_applies_software_offset(self):
        sim = FirmwareCorrectionSimulator()
        req = SyncCorrectionRequest.create("esp32_01", 7.0, 1_000)
        wire = build_wire_correction_request(req)
        response_wire = sim.handle_wire_request(wire)
        assert response_wire["type"] == MessageType.SYNC_CORRECTION_RESPONSE
        payload = response_wire["payload"]
        assert payload["applied"] is True
        assert payload["software_clock_offset"] == pytest.approx(-7.0)
        assert payload["accumulated_correction"] == pytest.approx(7.0)

    def test_memory_adapter_correction_wire(self, tmp_path):
        sim = FirmwareCorrectionSimulator()
        req = SyncCorrectionRequest.create("esp32_01", 6.0, 5_000)
        wire = build_wire_correction_request(req)
        response_wire = sim.handle_wire_request(wire)
        assert validate_message(response_wire) == []
        assert response_wire["payload"]["transaction_id"] == req.transaction_id
