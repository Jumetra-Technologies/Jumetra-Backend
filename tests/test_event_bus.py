"""Phase 1.4.1A — Event lifecycle, metadata, and Event Bus tests."""

from engine.events import (
    Event,
    EventBus,
    EventPriority,
    EventQueue,
    EventStatus,
    EventSubscriber,
    EventValidationError,
    reset_sequence_counter,
)


class RecordingSubscriber(EventSubscriber):
    def __init__(self) -> None:
        self.received: list[Event] = []

    def handle_event(self, event: Event) -> None:
        self.received.append(event)


class FailingSubscriber(EventSubscriber):
    def handle_event(self, event: Event) -> None:
        raise RuntimeError("subscriber boom")


class TestEventLifecycle:
    def test_created_on_construction(self):
        event = Event.create(event_type="HELLO", source="esp32_01")
        assert event.current_status == EventStatus.CREATED
        assert event.history == ["CREATED"]
        assert len(event.status_history) == 1
        assert event.status_history[0]["status"] == "CREATED"
        assert isinstance(event.status_history[0]["timestamp"], int)

    def test_status_transitions_record_history(self):
        event = Event.create(event_type="STATE_UPDATE", source="esp32_01")
        event.set_status(EventStatus.QUEUED)
        event.set_status(EventStatus.DISPATCHED)
        event.set_status(EventStatus.HANDLED)
        event.set_status(EventStatus.COMPLETED)
        event.set_status(EventStatus.ARCHIVED)

        assert event.history == [
            "CREATED",
            "QUEUED",
            "DISPATCHED",
            "HANDLED",
            "COMPLETED",
            "ARCHIVED",
        ]
        assert event.current_status == EventStatus.ARCHIVED
        assert event.processed_timestamp is not None
        assert event.completed_timestamp is not None

    def test_illegal_transition_raises(self):
        event = Event.create(event_type="HELLO", source="esp32_01")
        try:
            event.set_status(EventStatus.COMPLETED)
            assert False, "expected EventValidationError"
        except EventValidationError:
            pass

    def test_queue_marks_queued(self):
        event = Event.create(event_type="HELLO", source="esp32_01")
        q = EventQueue()
        q.add_event(event)
        assert event.current_status == EventStatus.QUEUED
        assert "QUEUED" in event.history


class TestEventMetadata:
    def setup_method(self):
        reset_sequence_counter(0)

    def test_sequence_numbers_increase_globally(self):
        first = Event.create(event_type="HELLO", source="a")
        second = Event.create(event_type="HELLO", source="b")
        third = Event.create(event_type="HELLO", source="c")
        assert first.sequence_number == 1
        assert second.sequence_number == 2
        assert third.sequence_number == 3

    def test_default_priority_is_normal(self):
        event = Event.create(event_type="HELLO", source="esp32_01")
        assert event.priority == EventPriority.NORMAL

    def test_priority_can_be_set(self):
        event = Event.create(
            event_type="STATE_UPDATE",
            source="esp32_01",
            priority=EventPriority.CRITICAL,
        )
        assert event.priority == EventPriority.CRITICAL

    def test_protocol_version_default(self):
        event = Event.create(event_type="HELLO", source="esp32_01")
        assert event.protocol_version == "1.0"

    def test_correlation_id_is_uuid_string(self):
        event = Event.create(event_type="HELLO", source="esp32_01")
        assert len(event.correlation_id) == 36
        assert event.correlation_id.count("-") == 4

    def test_correlation_id_can_be_inherited(self):
        parent = Event.create(event_type="STATE_UPDATE", source="esp32_01")
        child = Event.create(
            event_type="STATE_UPDATE",
            source="virtual_led_01",
            correlation_id=parent.correlation_id,
        )
        assert child.correlation_id == parent.correlation_id

    def test_created_timestamp_set(self):
        event = Event.create(event_type="HELLO", source="esp32_01")
        assert event.created_timestamp == event.timestamp
        assert event.processed_timestamp is None
        assert event.completed_timestamp is None

    def test_serialization_includes_lifecycle_metadata(self):
        event = Event.create(
            event_type="STATE_UPDATE",
            source="esp32_01",
            target="virtual_led_01",
            payload={"state": "ON"},
            priority=EventPriority.HIGH,
        )
        event.set_status(EventStatus.QUEUED)
        data = event.to_dict()
        assert data["priority"] == "HIGH"
        assert data["protocol_version"] == "1.0"
        assert data["sequence_number"] == event.sequence_number
        assert data["correlation_id"] == event.correlation_id
        assert data["current_status"] == "QUEUED"

        restored = Event.from_dict(data)
        assert restored.to_dict() == event.to_dict()


class TestEventBus:
    def test_register_and_subscriber_count(self):
        bus = EventBus()
        sub = RecordingSubscriber()
        assert bus.subscriber_count() == 0
        bus.register_subscriber(sub)
        assert bus.subscriber_count() == 1
        bus.register_subscriber(sub)  # duplicate ignored
        assert bus.subscriber_count() == 1

    def test_unregister(self):
        bus = EventBus()
        sub = RecordingSubscriber()
        bus.register_subscriber(sub)
        assert bus.unregister_subscriber(sub) is True
        assert bus.subscriber_count() == 0
        assert bus.unregister_subscriber(sub) is False

    def test_publish_invokes_subscribers(self):
        bus = EventBus()
        sub_a = RecordingSubscriber()
        sub_b = RecordingSubscriber()
        bus.register_subscriber(sub_a)
        bus.register_subscriber(sub_b)

        event = Event.create(event_type="STATE_UPDATE", source="esp32_01")
        event.set_status(EventStatus.QUEUED)
        bus.publish(event)

        assert sub_a.received == [event]
        assert sub_b.received == [event]
        assert event.history == [
            "CREATED",
            "QUEUED",
            "DISPATCHED",
            "HANDLED",
            "COMPLETED",
            "ARCHIVED",
        ]

    def test_broadcast_equivalent_to_publish(self):
        bus = EventBus()
        sub = RecordingSubscriber()
        bus.register_subscriber(sub)
        event = Event.create(event_type="HELLO", source="esp32_01")
        event.set_status(EventStatus.QUEUED)
        bus.broadcast(event)
        assert len(sub.received) == 1
        assert event.current_status == EventStatus.ARCHIVED

    def test_publish_continues_after_subscriber_error(self):
        bus = EventBus()
        good = RecordingSubscriber()
        bus.register_subscriber(FailingSubscriber())
        bus.register_subscriber(good)
        event = Event.create(event_type="HELLO", source="esp32_01")
        event.set_status(EventStatus.QUEUED)
        bus.publish(event)
        assert good.received == [event]
        assert event.current_status == EventStatus.ARCHIVED

    def test_register_rejects_non_subscriber(self):
        bus = EventBus()
        try:
            bus.register_subscriber(object())  # type: ignore[arg-type]
            assert False, "expected TypeError"
        except TypeError:
            pass
