import logging

from engine.devices.manager import DeviceManager
from engine.routing.router import Router
from engine.state.state_manager import StateManager
from engine.virtual.virtual_button import VirtualButton
from engine.virtual.virtual_led import VirtualLED


def make_router(send_callback=None):
    manager = DeviceManager()
    state_manager = StateManager()
    router = Router(device_manager=manager, state_manager=state_manager, send_callback=send_callback)
    return router, manager, state_manager


class TestRouteIncoming:
    def test_routes_state_update_to_registered_virtual_led(self):
        router, manager, state_manager = make_router()
        led = VirtualLED("virtual_led_01")
        manager.register_virtual(led)

        message = {
            "type": "STATE_UPDATE",
            "source": "esp32_01",
            "target": "virtual_led_01",
            "payload": {"state": "ON"},
        }
        router.route_incoming(message)

        assert led.get_state() == VirtualLED.ON

    def test_records_state_transition(self):
        router, manager, state_manager = make_router()
        led = VirtualLED("virtual_led_01")
        manager.register_virtual(led)

        message = {
            "type": "STATE_UPDATE",
            "source": "esp32_01",
            "target": "virtual_led_01",
            "payload": {"state": "ON"},
        }
        router.route_incoming(message)

        record = state_manager.get("virtual_led_01")
        assert record is not None
        assert record.previous_state == VirtualLED.OFF
        assert record.current_state == VirtualLED.ON
        assert record.source == "esp32_01"

    def test_unknown_target_is_logged_and_does_not_crash(self, caplog):
        router, manager, state_manager = make_router()
        message = {
            "type": "STATE_UPDATE",
            "source": "esp32_01",
            "target": "does_not_exist",
            "payload": {"state": "ON"},
        }
        with caplog.at_level(logging.WARNING):
            router.route_incoming(message)  # should not raise

        assert any("No virtual device registered" in r.message for r in caplog.records)
        assert state_manager.get("does_not_exist") is None

    def test_router_has_no_device_type_specific_branching(self):
        # Sanity check on the architectural constraint: Router should
        # not import VirtualLED/VirtualButton (docstrings may still
        # *mention* them in prose examples — that's fine; what matters
        # is the code has no import of, or branch on, a concrete type).
        import ast
        import inspect

        from engine.routing import router as router_module

        tree = ast.parse(inspect.getsource(router_module))
        imported_names = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        assert "VirtualLED" not in imported_names
        assert "VirtualButton" not in imported_names

        # And no isinstance/type check against a concrete virtual device type.
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "isinstance":
                for arg in node.args[1:]:
                    name = getattr(arg, "id", None)
                    assert name not in ("VirtualLED", "VirtualButton")


class TestRouteOutgoing:
    def test_calls_send_callback_with_target_and_payload(self):
        sent = []
        router, manager, state_manager = make_router(send_callback=lambda t, p: sent.append((t, p)))
        button = VirtualButton("virtual_button_01")
        button.press()

        router.route_outgoing(
            target="esp32_01",
            payload={"state": "ON"},
            source_device=button,
            previous_state=VirtualButton.RELEASED,
        )

        assert sent == [("esp32_01", {"state": "ON"})]

    def test_records_state_transition_with_hhip_as_source(self):
        router, manager, state_manager = make_router(send_callback=lambda t, p: None)
        button = VirtualButton("virtual_button_01")
        button.press()

        router.route_outgoing(
            target="esp32_01",
            payload={"state": "ON"},
            source_device=button,
            previous_state=VirtualButton.RELEASED,
        )

        record = state_manager.get("virtual_button_01")
        assert record is not None
        assert record.previous_state == VirtualButton.RELEASED
        assert record.current_state == VirtualButton.PRESSED
        assert record.source == "hhip"

    def test_missing_send_callback_is_logged_and_does_not_crash(self, caplog):
        router, manager, state_manager = make_router(send_callback=None)
        button = VirtualButton("virtual_button_01")
        button.press()

        with caplog.at_level(logging.WARNING):
            router.route_outgoing(
                target="esp32_01",
                payload={"state": "ON"},
                source_device=button,
                previous_state=VirtualButton.RELEASED,
            )

        assert any("No send_callback configured" in r.message for r in caplog.records)
        assert state_manager.get("virtual_button_01") is None
