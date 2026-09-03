from engine.virtual.virtual_led import VirtualLED


class TestVirtualLED:
    def test_starts_off(self):
        led = VirtualLED("virtual_led_01")
        assert led.get_state() == VirtualLED.OFF

    def test_turn_on(self):
        led = VirtualLED("virtual_led_01")
        led.turn_on()
        assert led.get_state() == VirtualLED.ON

    def test_turn_off(self):
        led = VirtualLED("virtual_led_01")
        led.turn_on()
        led.turn_off()
        assert led.get_state() == VirtualLED.OFF

    def test_toggle(self):
        led = VirtualLED("virtual_led_01")
        led.toggle()
        assert led.get_state() == VirtualLED.ON
        led.toggle()
        assert led.get_state() == VirtualLED.OFF

    def test_last_updated_changes_on_state_change(self):
        led = VirtualLED("virtual_led_01")
        before = led.last_updated
        led.turn_on()
        assert led.last_updated >= before

    def test_report_state_shape(self):
        led = VirtualLED("virtual_led_01")
        report = led.report_state()
        assert report["device_id"] == "virtual_led_01"
        assert report["device_type"] == "LED"
        assert report["state"] == VirtualLED.OFF
        assert "last_updated" in report

    def test_receive_event_turns_on(self):
        led = VirtualLED("virtual_led_01")
        led.receive_event({"state": "ON"})
        assert led.get_state() == VirtualLED.ON

    def test_receive_event_turns_off(self):
        led = VirtualLED("virtual_led_01")
        led.turn_on()
        led.receive_event({"state": "OFF"})
        assert led.get_state() == VirtualLED.OFF

    def test_receive_event_ignores_unrecognized_state(self):
        led = VirtualLED("virtual_led_01")
        led.receive_event({"state": "BLINK"})
        assert led.get_state() == VirtualLED.OFF  # unchanged

    def test_receive_event_missing_state_key(self):
        led = VirtualLED("virtual_led_01")
        led.receive_event({})
        assert led.get_state() == VirtualLED.OFF  # unchanged, no crash
