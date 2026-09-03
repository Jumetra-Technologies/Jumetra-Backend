from engine.events import Event, EventQueue, EventValidationError


class TestEventCreation:
    def test_create_assigns_id_and_timestamp(self):
        event = Event.create(
            event_type="STATE_UPDATE",
            source="esp32_01",
            target="virtual_led_01",
            payload={"state": "ON"},
        )
        assert event.event_id.startswith("evt_")
        assert event.event_type == "STATE_UPDATE"
        assert event.source == "esp32_01"
        assert event.target == "virtual_led_01"
        assert event.payload == {"state": "ON"}
        assert event.metadata == {}
        assert isinstance(event.timestamp, int)

    def test_create_rejects_empty_source(self):
        try:
            Event.create(event_type="HELLO", source="")
            assert False, "expected EventValidationError"
        except EventValidationError as exc:
            assert "source" in str(exc)

    def test_from_message_maps_protocol_fields(self):
        message = {
            "version": 1,
            "message_id": "msg_1",
            "type": "STATE_UPDATE",
            "source": "esp32_01",
            "target": "virtual_led_01",
            "sequence": 3,
            "timestamp": 1723456789000,
            "payload": {"state": "ON"},
        }
        event = Event.from_message(message)
        assert event.event_type == "STATE_UPDATE"
        assert event.source == "esp32_01"
        assert event.target == "virtual_led_01"
        assert event.payload == {"state": "ON"}
        assert event.timestamp == 1723456789000
        assert event.metadata["message_id"] == "msg_1"
        assert event.metadata["sequence"] == 3
        assert event.metadata["origin"] == "protocol"


class TestEventSerialization:
    def test_to_dict_and_from_dict_round_trip(self):
        original = Event.create(
            event_type="STATE_UPDATE",
            source="esp32_01",
            target="virtual_led_01",
            payload={"state": "ON"},
            metadata={"origin": "test"},
        )
        restored = Event.from_dict(original.to_dict())
        assert restored.to_dict() == original.to_dict()

    def test_to_json_and_from_json_round_trip(self):
        original = Event.create(
            event_type="HEARTBEAT",
            source="esp32_01",
            target="hhip",
            payload={},
        )
        restored = Event.from_json(original.to_json())
        assert restored.event_id == original.event_id
        assert restored.event_type == original.event_type
        assert restored.source == original.source

    def test_from_dict_validates(self):
        try:
            Event.from_dict({"event_id": "", "event_type": "X", "source": "y"})
            assert False, "expected EventValidationError"
        except EventValidationError:
            pass


class TestEventQueueOrdering:
    def test_fifo_ordering(self):
        q = EventQueue()
        first = Event.create(event_type="HELLO", source="esp32_01", target="hhip")
        second = Event.create(event_type="HEARTBEAT", source="esp32_01", target="hhip")
        third = Event.create(
            event_type="STATE_UPDATE",
            source="esp32_01",
            target="virtual_led_01",
            payload={"state": "ON"},
        )
        q.add_event(first)
        q.add_event(second)
        q.add_event(third)

        assert q.size() == 3
        assert q.get_event(block=False) is first
        assert q.get_event(block=False) is second
        assert q.get_event(block=False) is third
        assert q.size() == 0
        assert q.get_event(block=False) is None

    def test_clear_empties_queue(self):
        q = EventQueue()
        q.add_event(Event.create(event_type="HELLO", source="esp32_01"))
        q.add_event(Event.create(event_type="HELLO", source="esp32_02"))
        q.clear()
        assert q.size() == 0
        assert q.get_event(block=False) is None

    def test_add_event_rejects_non_event(self):
        q = EventQueue()
        try:
            q.add_event({"event_type": "HELLO"})  # type: ignore[arg-type]
            assert False, "expected TypeError"
        except TypeError:
            pass
