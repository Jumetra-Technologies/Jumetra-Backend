"""Integration: protocol message → Event → Queue → handlers (no hardware)."""

from engine.communication.memory_adapter import make_adapter_pair
from engine.main import HHIPEngine
from engine.protocol.messages import MessageType, create_message


def _engine(tmp_path):
    engine_adapter, _device_adapter = make_adapter_pair()
    engine_adapter.connect()
    return HHIPEngine(
        adapter=engine_adapter,
        storage_dir=str(tmp_path / "data"),
        persist_events=True,
    )


class TestEventBackboneIntegration:
    def test_hello_creates_event_and_keeps_ack(self, tmp_path):
        engine = _engine(tmp_path)
        message = create_message(
            type_=MessageType.HELLO,
            source="esp32_01",
            target="hhip",
            sequence=1,
            payload={"device_type": "esp32"},
        )
        engine.handle_message(message)

        assert "esp32_01" in engine.registry
        assert engine.events.size() == 0  # drained after dispatch
        metrics = engine.metrics.get_metrics()
        # Startup DEVICE_* lifecycle events are counted; HELLO adds one more.
        assert metrics["events_received"] >= 1
        assert metrics["events_processed"] >= 1
        assert metrics["processing_time_count"] >= 1

        lines = engine.storage.events_path.read_text(encoding="utf-8").strip().splitlines()
        assert any("HELLO" in line for line in lines)

    def test_state_update_flows_through_event_queue(self, tmp_path):
        engine = _engine(tmp_path)
        # Register physical device first (as HELLO would).
        engine.handle_message(
            create_message(
                type_=MessageType.HELLO,
                source="esp32_01",
                target="hhip",
                sequence=1,
                payload={"device_type": "esp32"},
            )
        )
        engine.handle_message(
            create_message(
                type_=MessageType.STATE_UPDATE,
                source="esp32_01",
                target="virtual_led_01",
                sequence=2,
                payload={"state": "ON"},
            )
        )

        assert engine.virtual_led.get_state() == "ON"
        assert engine.state_manager.get_state("virtual_led_01") == "ON"
        snapshot = engine.storage.load_snapshot()
        assert snapshot is not None
        assert snapshot["virtual_led_01"] == "ON"
        assert engine.metrics.get_metrics()["events_received"] >= 2
        assert engine.event_bus.subscriber_count() >= 4

    def test_event_reaches_archived_lifecycle(self, tmp_path):
        engine = _engine(tmp_path)
        engine.handle_message(
            create_message(
                type_=MessageType.HELLO,
                source="esp32_01",
                target="hhip",
                sequence=1,
                payload={"device_type": "esp32"},
            )
        )
        # Last published event is drained; reconstruct by checking storage line
        # and that HELLO still registered the device through the bus.
        assert "esp32_01" in engine.registry
        from engine.events import EventStatus
        from engine.events.event import Event

        # Fresh event through the same pipeline pieces:
        event = Event.from_message(
            create_message(
                type_=MessageType.HEARTBEAT,
                source="esp32_01",
                target="hhip",
                sequence=2,
            )
        )
        engine.events.add_event(event)
        queued = engine.events.get_event(block=False)
        engine.event_bus.publish(queued)
        assert queued.current_status == EventStatus.ARCHIVED
        assert queued.history[0] == "CREATED"
        assert "DISPATCHED" in queued.history
        assert "COMPLETED" in queued.history
