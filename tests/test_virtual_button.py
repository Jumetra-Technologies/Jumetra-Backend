from engine.virtual.virtual_button import VirtualButton


class TestVirtualButton:
    def test_starts_released(self):
        button = VirtualButton("virtual_button_01")
        assert button.state == VirtualButton.RELEASED

    def test_press_changes_state(self):
        button = VirtualButton("virtual_button_01")
        button.press()
        assert button.state == VirtualButton.PRESSED

    def test_release_changes_state(self):
        button = VirtualButton("virtual_button_01")
        button.press()
        button.release()
        assert button.state == VirtualButton.RELEASED

    def test_press_triggers_on_change_callback(self):
        calls = []
        button = VirtualButton(
            "virtual_button_01",
            on_change=lambda btn, prev, new: calls.append((btn.device_id, prev, new)),
        )
        button.press()
        assert calls == [("virtual_button_01", VirtualButton.RELEASED, VirtualButton.PRESSED)]

    def test_release_triggers_on_change_callback(self):
        calls = []
        button = VirtualButton(
            "virtual_button_01",
            on_change=lambda btn, prev, new: calls.append((prev, new)),
        )
        button.press()
        button.release()
        assert calls[-1] == (VirtualButton.PRESSED, VirtualButton.RELEASED)

    def test_repeated_press_does_not_retrigger_callback(self):
        calls = []
        button = VirtualButton(
            "virtual_button_01",
            on_change=lambda btn, prev, new: calls.append((prev, new)),
        )
        button.press()
        button.press()  # already pressed; should be a no-op event-wise
        assert len(calls) == 1

    def test_no_callback_configured_does_not_crash(self):
        button = VirtualButton("virtual_button_01")  # on_change=None
        button.press()  # should not raise
        assert button.state == VirtualButton.PRESSED

    def test_receive_event_does_not_crash_or_change_state(self):
        button = VirtualButton("virtual_button_01")
        button.receive_event({"state": "ON"})  # buttons ignore inbound events
        assert button.state == VirtualButton.RELEASED
