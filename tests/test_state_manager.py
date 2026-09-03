from engine.state.state_manager import StateManager


class TestStateManager:
    def test_record_stores_and_returns_a_record(self):
        manager = StateManager()
        record = manager.record(
            device_id="virtual_led_01", previous_state="OFF", current_state="ON", source="esp32_01"
        )
        assert record.device_id == "virtual_led_01"
        assert record.previous_state == "OFF"
        assert record.current_state == "ON"
        assert record.source == "esp32_01"
        assert isinstance(record.timestamp, int)

    def test_get_returns_latest_record_for_device(self):
        manager = StateManager()
        manager.record(device_id="virtual_led_01", previous_state="OFF", current_state="ON", source="esp32_01")
        record = manager.get("virtual_led_01")
        assert record is not None
        assert record.current_state == "ON"

    def test_get_returns_none_for_unknown_device(self):
        manager = StateManager()
        assert manager.get("does_not_exist") is None

    def test_record_overwrites_previous_record_for_same_device(self):
        manager = StateManager()
        manager.record(device_id="virtual_led_01", previous_state="OFF", current_state="ON", source="esp32_01")
        manager.record(device_id="virtual_led_01", previous_state="ON", current_state="OFF", source="esp32_01")
        record = manager.get("virtual_led_01")
        assert record.previous_state == "ON"
        assert record.current_state == "OFF"

    def test_all_states_returns_one_record_per_device(self):
        manager = StateManager()
        manager.record(device_id="virtual_led_01", previous_state="OFF", current_state="ON", source="esp32_01")
        manager.record(device_id="virtual_button_01", previous_state="RELEASED", current_state="PRESSED", source="hhip")
        device_ids = {r.device_id for r in manager.all_states()}
        assert device_ids == {"virtual_led_01", "virtual_button_01"}

    def test_to_dict_shape(self):
        manager = StateManager()
        record = manager.record(device_id="virtual_led_01", previous_state="OFF", current_state="ON", source="esp32_01")
        d = record.to_dict()
        assert set(d.keys()) == {"device_id", "previous_state", "current_state", "source", "timestamp"}

    def test_update_state_returns_transition_dict(self):
        manager = StateManager()
        result = manager.update_state(
            "virtual_led_01", "ON", source="esp32_01", previous_state="OFF"
        )
        assert result["device"] == "virtual_led_01"
        assert result["previous"] == "OFF"
        assert result["current"] == "ON"
        assert "timestamp" in result

    def test_get_state_and_get_all_states(self):
        manager = StateManager()
        manager.update_state("virtual_led_01", "ON", source="esp32_01", previous_state="OFF")
        manager.update_state(
            "virtual_button_01", "PRESSED", source="hhip", previous_state="RELEASED"
        )
        assert manager.get_state("virtual_led_01") == "ON"
        assert manager.get_state("missing") is None
        assert manager.get_all_states() == {
            "virtual_led_01": "ON",
            "virtual_button_01": "PRESSED",
        }

    def test_update_state_infers_previous_from_stored(self):
        manager = StateManager()
        manager.update_state("virtual_led_01", "ON", source="esp32_01")
        result = manager.update_state("virtual_led_01", "OFF", source="esp32_01")
        assert result["previous"] == "ON"
        assert result["current"] == "OFF"
