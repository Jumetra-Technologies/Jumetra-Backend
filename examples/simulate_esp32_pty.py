"""Not part of the pytest suite. A one-off manual check that runs the
*real* engine.main.HHIPEngine against a simulated device over a Linux
pty pair, to prove the PoC-01 flow works end-to-end without needing
physical ESP32 hardware attached to this sandbox.

This does NOT replace hardware verification against real firmware —
see docs/poc-01.md for that. It only proves the Python-side engine
logic is wired correctly.
"""

import os
import pty
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.main import HHIPEngine  # noqa: E402
from engine.protocol.messages import (  # noqa: E402
    MessageType,
    create_message,
    decode_message,
    encode_message,
)

master_fd, slave_fd = pty.openpty()
device_port = os.ttyname(slave_fd)
print(f"[sim] virtual serial device: {device_port}")

engine = HHIPEngine(port=device_port, baudrate=115200)

engine_thread = threading.Thread(target=engine.run, daemon=True)
engine_thread.start()
time.sleep(0.3)


def device_send(msg: dict) -> None:
    line = (encode_message(msg) + "\n").encode("utf-8")
    os.write(master_fd, line)


def device_read_line(timeout: float = 2.0) -> dict:
    end = time.time() + timeout
    buf = b""
    while time.time() < end:
        try:
            chunk = os.read(master_fd, 4096)
        except OSError:
            chunk = b""
        buf += chunk
        if b"\n" in buf:
            line, _, _rest = buf.partition(b"\n")
            return decode_message(line.decode("utf-8"))
        time.sleep(0.05)
    raise TimeoutError("No message received from engine in time")


# 1. Device -> HELLO
hello = create_message(
    type_=MessageType.HELLO,
    source="esp32_01",
    target="hhip",
    sequence=1,
    payload={"device_type": "esp32", "firmware_version": "0.1.0"},
)
device_send(hello)
print("[sim] sent HELLO")

hello_ack = device_read_line()
assert hello_ack["type"] == MessageType.HELLO_ACK, hello_ack
print("[sim] received HELLO_ACK:", hello_ack)

# 2. Device -> HEARTBEAT
heartbeat = create_message(
    type_=MessageType.HEARTBEAT,
    source="esp32_01",
    target="hhip",
    sequence=2,
    payload={},
)
device_send(heartbeat)
print("[sim] sent HEARTBEAT")

ack = device_read_line()
assert ack["type"] == MessageType.ACK, ack
print("[sim] received ACK:", ack)

assert "esp32_01" in engine.registry
print("[sim] engine registry contains esp32_01:", engine.registry.get("esp32_01").to_dict())

print("\n[sim] PoC-01 flow verified end-to-end over a virtual pty pair.")

os.close(master_fd)
os.close(slave_fd)
