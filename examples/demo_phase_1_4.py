"""Executable, no-hardware proof of both Phase 1.4 demonstrations,
run against the real HHIPEngine (not a mock). Uses InMemoryAdapter
(cross-platform — unlike the Phase 1.3 pty demo, this also runs on
Windows) to stand in for a physical ESP32.

Demonstration A: Physical Button -> ESP32 -> HHIP -> Virtual LED
Demonstration B: Virtual Button  -> HHIP -> ESP32 -> Physical LED

Run: python examples/demo_phase_1_4.py
"""

import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.communication.memory_adapter import make_adapter_pair  # noqa: E402
from engine.main import HHIPEngine  # noqa: E402
from engine.protocol.messages import (  # noqa: E402
    MessageType,
    create_message,
    decode_message,
    encode_message,
)
from engine.virtual.virtual_led import VirtualLED  # noqa: E402


def banner(text: str) -> None:
    print(f"\n{'=' * 70}\n{text}\n{'=' * 70}")


engine_adapter, device_adapter = make_adapter_pair()
engine = HHIPEngine(adapter=engine_adapter, physical_device_id="esp32_01")

engine_thread = threading.Thread(target=engine.run, daemon=True)
engine_thread.start()
time.sleep(0.2)

# --- Register the (fake) physical device first, same as PoC-01 -----------
banner("Setup: fake ESP32 sends HELLO (needed before either demonstration)")
device_adapter.connect()
hello = create_message(
    type_=MessageType.HELLO,
    source="esp32_01",
    target="hhip",
    sequence=1,
    payload={"device_type": "esp32", "firmware_version": "0.2.0"},
)
device_adapter.send(hello)
hello_ack = device_adapter.receive()
assert hello_ack["type"] == MessageType.HELLO_ACK, hello_ack
print("Fake ESP32 registered. HELLO_ACK received.")

# --- Demonstration A: Physical Button -> ESP32 -> HHIP -> Virtual LED ----
banner("Demonstration A: Physical Button -> ESP32 -> HHIP -> Virtual LED")
assert engine.virtual_led.get_state() == VirtualLED.OFF
print(f"Before: virtual_led_01 state = {engine.virtual_led.get_state()}")

button_press_update = create_message(
    type_=MessageType.STATE_UPDATE,
    source="esp32_01",
    target="virtual_led_01",
    sequence=2,
    payload={"state": "ON"},
)
device_adapter.send(button_press_update)
print("Fake ESP32 sent STATE_UPDATE (simulating physical button press) -> virtual_led_01: ON")

ack = device_adapter.receive()
assert ack["type"] == MessageType.ACK and ack["payload"]["ack_type"] == MessageType.STATE_UPDATE, ack
print("HHIP acknowledged the STATE_UPDATE.")

time.sleep(0.1)
after = engine.virtual_led.get_state()
print(f"After:  virtual_led_01 state = {after}")
assert after == VirtualLED.ON, "Demonstration A FAILED: virtual LED did not turn on"
print("Demonstration A: PASSED — physical button press turned the virtual LED ON.")

record = engine.state_manager.get("virtual_led_01")
print(f"StateManager record: {record.to_dict()}")

# --- Demonstration B: Virtual Button -> HHIP -> ESP32 -> Physical LED ----
banner("Demonstration B: Virtual Button -> HHIP -> ESP32 -> Physical LED")
print(f"Before: virtual_button_01 state = {engine.virtual_button.state}")

engine.press_virtual_button()
print("Called engine.press_virtual_button() (simulating a virtual button activation)")

outgoing = device_adapter.receive()
assert outgoing is not None, "Demonstration B FAILED: no STATE_UPDATE arrived at the fake ESP32"
assert outgoing["type"] == MessageType.STATE_UPDATE, outgoing
assert outgoing["target"] == "esp32_01", outgoing
assert outgoing["payload"]["state"] == "ON", outgoing
print(f"Fake ESP32 received STATE_UPDATE targeting it: {outgoing['payload']}")
print("Demonstration B: PASSED — virtual button press produced an outgoing STATE_UPDATE "
      "to the physical device, requesting LED = ON.")

record = engine.state_manager.get("virtual_button_01")
print(f"StateManager record: {record.to_dict()}")

banner("Both demonstrations verified end-to-end against the real HHIPEngine.")

device_adapter.disconnect()
