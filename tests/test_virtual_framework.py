"""Phase 1.4.2 — Virtual Device Framework tests."""

from engine.devices.device_manager import DeviceManager, UnknownDeviceError
from engine.devices.virtual import DeviceStatus, VirtualButton, VirtualDevice, VirtualLED
from engine.events import Event, EventBus
from engine.routing.router_subscriber import RouterSubscriber
from engine.state.state_manager import StateManager


class TestVirtualDeviceBase:
    def test_initialize_sets_ready(self):
        led = VirtualLED("virtual_led_01")
        assert led.status == DeviceStatus.UNKNOWN
        led.initialize()
        assert led.status == DeviceStatus.READY
        assert led.health()["healthy"] is True

    def test_shutdown_sets_offline(self):
        led = VirtualLED("virtual_led_01")
        led.initialize()
        led.shutdown()
        assert led.status == DeviceStatus.OFFLINE

    def test_serialize_deserialize_round_trip(self):
        led = VirtualLED("virtual_led_01", brightness=40, color="#00FF00")
        led.initialize()
        led.turn_on()
        data = led.serialize()
        assert data["device_type"] == "LED"
        assert data["status"] == "READY"
        assert data["brightness"] == 40

        restored = VirtualLED("virtual_led_01")
        restored.deserialize(data)
        assert restored.get_state() == VirtualLED.ON
        assert restored.brightness == 40
        assert restored.color == "#00FF00"
        assert restored.status == DeviceStatus.READY


class TestVirtualLEDFramework:
    def test_brightness_clamped(self):
        led = VirtualLED("virtual_led_01", brightness=150)
        assert led.brightness == 100
        led.brightness = -5
        assert led.brightness == 0

    def test_handle_event_turns_on(self):
        led = VirtualLED("virtual_led_01")
        led.initialize()
        event = Event.create(
            event_type="STATE_UPDATE",
            source="esp32_01",
            target="virtual_led_01",
            payload={"state": "ON", "brightness": 80},
        )
        led.handle_event(event)
        assert led.get_state() == VirtualLED.ON
        assert led.brightness == 80


class TestVirtualButtonFramework:
    def test_toggle(self):
        button = VirtualButton("virtual_button_01")
        button.initialize()
        button.toggle()
        assert button.state == VirtualButton.PRESSED
        button.toggle()
        assert button.state == VirtualButton.RELEASED

    def test_press_publishes_state_update(self):
        published = []

        def publish(event_type, source, target, payload):
            published.append((event_type, source, target, payload))

        button = VirtualButton(
            "virtual_button_01",
            publish=publish,
            default_target="esp32_01",
        )
        button.initialize()
        button.press()
        assert len(published) == 1
        event_type, source, target, payload = published[0]
        assert event_type == "STATE_UPDATE"
        assert source == "virtual_button_01"
        assert target == "esp32_01"
        assert payload["state"] == "ON"
        assert payload["button_state"] == VirtualButton.PRESSED


class TestDeviceManagerFramework:
    def test_register_device_initializes_ready(self):
        manager = DeviceManager()
        led = VirtualLED("virtual_led_01")
        manager.register_device(led)
        assert led.status == DeviceStatus.READY
        assert manager.get_device("virtual_led_01") is led

    def test_find_by_type_and_status(self):
        manager = DeviceManager()
        manager.register_device(VirtualLED("virtual_led_01"))
        manager.register_device(VirtualButton("virtual_button_01"))
        assert {d.device_id for d in manager.find_by_type("LED")} == {"virtual_led_01"}
        assert {d.device_id for d in manager.find_by_status(DeviceStatus.READY)} == {
            "virtual_led_01",
            "virtual_button_01",
        }

    def test_get_devices_includes_physical(self):
        manager = DeviceManager()
        manager.register_physical_from_hello("esp32_01", "esp32")
        manager.register_device(VirtualLED("virtual_led_01"))
        ids = {d.device_id for d in manager.get_devices()}
        assert ids == {"esp32_01", "virtual_led_01"}

    def test_remove_unknown_raises(self):
        manager = DeviceManager()
        try:
            manager.remove_device("missing")
            assert False, "expected UnknownDeviceError"
        except UnknownDeviceError:
            pass

    def test_state_manager_sync_on_register(self):
        manager = DeviceManager()
        state = StateManager()
        manager.bind_state_manager(state)
        led = VirtualLED("virtual_led_01")
        manager.register_device(led)
        led.turn_on()
        assert state.get_state("virtual_led_01") == VirtualLED.ON


class TestRouterSubscriber:
    def test_delivers_state_update_to_virtual_led(self):
        manager = DeviceManager()
        state = StateManager()
        manager.bind_state_manager(state)
        led = VirtualLED("virtual_led_01")
        manager.register_device(led)

        bus = EventBus()
        subscriber = RouterSubscriber(manager, state)
        bus.register_subscriber(subscriber)

        event = Event.create(
            event_type="STATE_UPDATE",
            source="esp32_01",
            target="virtual_led_01",
            payload={"state": "ON"},
        )
        event.set_status("QUEUED")
        bus.publish(event)

        assert led.get_state() == VirtualLED.ON
        assert state.get_state("virtual_led_01") == VirtualLED.ON

    def test_delivers_to_physical_via_send_callback(self):
        manager = DeviceManager()
        state = StateManager()
        manager.physical.register(device_id="esp32_01", device_type="esp32")
        sent = []

        subscriber = RouterSubscriber(
            manager, state, send_callback=lambda t, p: sent.append((t, p))
        )
        event = Event.create(
            event_type="STATE_UPDATE",
            source="virtual_button_01",
            target="esp32_01",
            payload={"state": "ON"},
        )
        subscriber.handle_event(event)
        assert sent == [("esp32_01", {"state": "ON"})]

    def test_ignores_non_state_update(self):
        manager = DeviceManager()
        state = StateManager()
        led = VirtualLED("virtual_led_01")
        manager.register_device(led)
        subscriber = RouterSubscriber(manager, state)
        event = Event.create(event_type="HEARTBEAT", source="esp32_01", target="hhip")
        subscriber.handle_event(event)
        assert led.get_state() == VirtualLED.OFF
