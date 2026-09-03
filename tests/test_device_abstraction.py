"""Sprint 6 — Device abstraction, capabilities, modes, lifecycle."""

from engine.devices.base import (
    Capability,
    DeviceLifecycleEvent,
    DeviceMode,
    DeviceStatus,
    PhysicalDevice,
    SimulatorDevice,
    capabilities_for,
)
from engine.devices.device_manager import DeviceManager
from engine.devices.virtual import VirtualButton, VirtualLED
from engine.events import EventBus, EventSubscriber


class _LifecycleRecorder(EventSubscriber):
    def __init__(self) -> None:
        self.types: list[str] = []

    def handle_event(self, event) -> None:
        self.types.append(event.event_type)


class TestCapabilities:
    def test_led_profile_is_data_driven(self):
        caps = capabilities_for("LED")
        assert Capability.ON in caps
        assert Capability.OFF in caps
        assert Capability.BRIGHTNESS in caps
        assert Capability.ROTATE not in caps

    def test_servo_and_sensor_profiles(self):
        assert {c.value for c in capabilities_for("SERVO")} == {"ROTATE", "POSITION"}
        assert {c.value for c in capabilities_for("SENSOR")} == {"READ", "CALIBRATE"}

    def test_unknown_type_has_empty_capabilities(self):
        assert capabilities_for("NOT_A_REAL_TYPE") == frozenset()

    def test_virtual_led_exposes_capabilities_without_type_branching(self):
        led = VirtualLED("virtual_led_01")
        assert led.has_capability(Capability.ON)
        assert led.has_capability("BRIGHTNESS")
        assert "ON" in led.get_capabilities()
        assert "ROTATE" not in led.get_capabilities()


class TestDeviceModes:
    def test_virtual_mode(self):
        led = VirtualLED("virtual_led_01")
        assert led.device_mode == DeviceMode.VIRTUAL

    def test_physical_mode(self):
        device = PhysicalDevice("esp32_01", device_type="ESP32")
        assert device.device_mode == DeviceMode.PHYSICAL
        assert device.device_mode.to_registry() == "physical"

    def test_simulated_mode(self):
        sim = SimulatorDevice("wokwi_01", simulator_backend="wokwi")
        assert sim.device_mode == DeviceMode.SIMULATED
        assert sim.simulator_backend == "wokwi"


class TestSimulatorDevice:
    def test_initialize_and_health_check(self):
        sim = SimulatorDevice("sim_01", simulator_backend="proteus")
        sim.initialize()
        health = sim.health_check()
        assert health["healthy"] is True
        assert health["device_mode"] == "SIMULATED"
        assert health["status"] == "READY"
        assert "CONNECT" in health["capabilities"]

    def test_connect_disconnect_backend(self):
        sim = SimulatorDevice("sim_01")
        sim.connect_backend()
        assert sim.status == DeviceStatus.READY
        sim.disconnect_backend()
        assert sim.status == DeviceStatus.OFFLINE


class TestPhysicalDevice:
    def test_mark_connected_and_touch(self):
        device = PhysicalDevice("esp32_01")
        device.mark_connected()
        assert device.status == DeviceStatus.READY
        before = device.last_seen
        device.touch()
        assert device.last_seen >= before


class TestDeviceManagerAbstraction:
    def test_manages_all_modes(self):
        manager = DeviceManager()
        manager.register_device(VirtualLED("virtual_led_01"))
        manager.register_device(VirtualButton("virtual_button_01"))
        manager.register_device(PhysicalDevice("esp32_01"))
        manager.register_device(SimulatorDevice("sim_01"))

        assert len(manager.get_devices()) == 4
        assert len(manager.find_by_mode(DeviceMode.VIRTUAL)) == 2
        assert len(manager.find_by_mode(DeviceMode.PHYSICAL)) == 1
        assert len(manager.find_by_mode(DeviceMode.SIMULATED)) == 1

    def test_find_by_capability(self):
        manager = DeviceManager()
        manager.register_device(VirtualLED("virtual_led_01"))
        manager.register_device(VirtualButton("virtual_button_01"))
        manager.register_device(SimulatorDevice("sim_01"))

        with_on = {d.device_id for d in manager.find_by_capability("ON")}
        assert with_on == {"virtual_led_01"}
        with_press = {d.device_id for d in manager.find_by_capability("PRESS")}
        assert with_press == {"virtual_button_01"}

    def test_lifecycle_events_on_register_and_remove(self):
        bus = EventBus()
        recorder = _LifecycleRecorder()
        bus.register_subscriber(recorder)

        manager = DeviceManager()
        manager.bind_event_bus(bus)
        led = VirtualLED("virtual_led_01")
        manager.register_device(led)

        assert DeviceLifecycleEvent.REGISTERED in recorder.types
        assert DeviceLifecycleEvent.CONNECTED in recorder.types
        assert DeviceLifecycleEvent.HEALTH_CHANGED in recorder.types

        manager.remove_device("virtual_led_01")
        assert DeviceLifecycleEvent.DISCONNECTED in recorder.types

    def test_report_error_emits_lifecycle(self):
        bus = EventBus()
        recorder = _LifecycleRecorder()
        bus.register_subscriber(recorder)
        manager = DeviceManager()
        manager.bind_event_bus(bus)
        manager.register_device(VirtualLED("virtual_led_01"))
        recorder.types.clear()

        manager.report_error("virtual_led_01", detail="overheat")
        assert DeviceLifecycleEvent.ERROR in recorder.types
        assert DeviceLifecycleEvent.HEALTH_CHANGED in recorder.types
        assert manager.get_device("virtual_led_01").status == DeviceStatus.ERROR
