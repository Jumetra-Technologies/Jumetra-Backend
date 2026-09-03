import json

from engine.events import Event
from engine.storage import StorageManager


class TestStorageManager:
    def test_save_event_appends_jsonl(self, tmp_path):
        storage = StorageManager(base_dir=tmp_path)
        event_a = Event.create(
            event_type="STATE_UPDATE",
            source="esp32_01",
            target="virtual_led_01",
            payload={"state": "ON"},
        )
        event_b = Event.create(
            event_type="HEARTBEAT",
            source="esp32_01",
            target="hhip",
        )
        storage.save_event(event_a)
        storage.save_event(event_b)

        lines = storage.events_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0])["event_id"] == event_a.event_id
        assert json.loads(lines[1])["event_type"] == "HEARTBEAT"

    def test_save_metric_appends_jsonl(self, tmp_path):
        storage = StorageManager(base_dir=tmp_path)
        storage.save_metric({"events_received": 1, "processing_time_ms": 2.5})
        storage.save_metric({"events_received": 2, "processing_time_ms": 1.0})

        lines = storage.metrics_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0])["processing_time_ms"] == 2.5

    def test_save_and_load_snapshot(self, tmp_path):
        storage = StorageManager(base_dir=tmp_path)
        state = {"virtual_led_01": "ON", "virtual_button_01": "RELEASED"}
        storage.save_snapshot(state)

        loaded = storage.load_snapshot()
        assert loaded == state

        # Overwrite (snapshot is point-in-time, not append)
        storage.save_snapshot({"virtual_led_01": "OFF"})
        assert storage.load_snapshot() == {"virtual_led_01": "OFF"}

    def test_load_snapshot_missing_returns_none(self, tmp_path):
        storage = StorageManager(base_dir=tmp_path)
        assert storage.load_snapshot() is None
