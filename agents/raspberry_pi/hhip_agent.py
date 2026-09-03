#!/usr/bin/env python3
"""HHIP agent for Raspberry Pi — discovery, GPIO, heartbeat, commands.

Run on the Pi (or locally in simulation mode)::

    python hhip_agent.py --simulate
    python hhip_agent.py --device-id rpi4_lab --gpio-backend gpiozero

Protocol: newline-delimited HHIP JSON (EVENT DEVICE_DISCOVERY / GPIO_STATE /
GPIO_WRITE, HEARTBEAT) matching ``engine.hybrid.device_agent``.
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
import threading
import time
import uuid
from typing import Any, Callable, Optional


PROTOCOL_VERSION = 1
BOARD_TYPE = "raspberry-pi-4"
FIRMWARE_VERSION = "1.0.0-hhip-pi-agent"
HEARTBEAT_INTERVAL_S = 5.0

DEFAULT_PINS = [
    {"pin_id": "GPIO17", "name": "GPIO17", "number": 17, "interfaces": ["gpio"], "state": 0},
    {"pin_id": "GPIO18", "name": "GPIO18", "number": 18, "interfaces": ["gpio", "pwm"], "state": 0},
    {"pin_id": "GPIO22", "name": "GPIO22", "number": 22, "interfaces": ["gpio"], "state": 0},
    {"pin_id": "GPIO23", "name": "GPIO23", "number": 23, "interfaces": ["gpio"], "state": 0},
    {"pin_id": "GPIO24", "name": "GPIO24", "number": 24, "interfaces": ["gpio"], "state": 0},
    {"pin_id": "GPIO27", "name": "GPIO27", "number": 27, "interfaces": ["gpio"], "state": 0},
]


class RaspberryPiAgent:
    """Raspberry Pi HHIP agent — discovery, GPIO reporting, heartbeat, commands."""

    def __init__(
        self,
        *,
        device_id: str = "",
        simulate: bool = True,
        writer: Optional[Callable[[str], None]] = None,
        gpio_backend: Optional[Any] = None,
    ) -> None:
        self.device_id = device_id or f"rpi4_{uuid.uuid4().hex[:6]}"
        self.simulate = simulate
        self._writer = writer or (lambda line: print(line, flush=True))
        self._sequence = 0
        self._pins = {p["pin_id"]: dict(p) for p in DEFAULT_PINS}
        self._gpio = gpio_backend
        self._running = False
        self._lock = threading.RLock()

    def start(self) -> None:
        self._running = True
        self.send_device_discovery()
        threading.Thread(target=self._heartbeat_loop, daemon=True).start()

    def stop(self) -> None:
        self._running = False

    def send_device_discovery(self) -> dict[str, Any]:
        payload = {
            "event": "DEVICE_DISCOVERY",
            "device_id": self.device_id,
            "board_type": BOARD_TYPE,
            "device_type": BOARD_TYPE,
            "vendor": "Raspberry Pi Foundation",
            "manufacturer": "Raspberry Pi Foundation",
            "firmware_version": FIRMWARE_VERSION,
            "label": "Raspberry Pi 4 HHIP Agent",
            "capabilities": ["gpio", "pwm", "i2c", "spi", "uart", "ssh", "camera"],
            "pins": list(self._pins.values()),
        }
        return self._send("EVENT", payload)

    def send_heartbeat(self) -> dict[str, Any]:
        return self._send("HEARTBEAT", {})

    def send_gpio_state(self, pin_id: str, value: int) -> dict[str, Any]:
        return self._send(
            "EVENT",
            {"event": "GPIO_STATE", "pin": pin_id, "value": int(value)},
        )

    def handle_line(self, line: str) -> Optional[dict[str, Any]]:
        line = line.strip()
        if not line:
            return None
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            return None
        return self.handle_message(message)

    def handle_message(self, message: dict[str, Any]) -> Optional[dict[str, Any]]:
        msg_type = message.get("type")
        payload = message.get("payload") or {}
        if msg_type in ("HELLO", "HELLO_ACK"):
            return self.send_device_discovery()
        if msg_type == "EVENT" and payload.get("event") == "GPIO_WRITE":
            pin = str(payload.get("pin") or "")
            value = int(payload.get("value", 0))
            return self.apply_gpio_write(pin, value)
        if msg_type == "WRITE":
            pin = str(payload.get("pin") or "")
            value = int(payload.get("value", 0))
            return self.apply_gpio_write(pin, value)
        if msg_type == "EVENT" and payload.get("event") == "EXECUTE":
            return self.execute_command(str(payload.get("command") or ""))
        return None

    def apply_gpio_write(self, pin_id: str, value: int) -> dict[str, Any]:
        with self._lock:
            if pin_id not in self._pins:
                return self._send(
                    "ERROR",
                    {"code": "UNKNOWN_PIN", "pin": pin_id},
                )
            self._pins[pin_id]["state"] = 1 if value else 0
            if self._gpio is not None and hasattr(self._gpio, "write"):
                try:
                    self._gpio.write(self._pins[pin_id]["number"], value)
                except Exception as exc:  # noqa: BLE001
                    return self._send("ERROR", {"code": "GPIO_ERROR", "detail": str(exc)})
        return self.send_gpio_state(pin_id, 1 if value else 0)

    def execute_command(self, command: str) -> dict[str, Any]:
        """Execute a safe allowlisted command (simulate-friendly)."""
        allowed = {"hostname", "uname -a", "uptime", "cat /proc/device-tree/model"}
        if command not in allowed:
            return self._send(
                "EVENT",
                {"event": "COMMAND_RESULT", "ok": False, "error": "command not allowlisted"},
            )
        if self.simulate:
            result = {
                "hostname": socket.gethostname(),
                "uname -a": "Linux simulated-pi",
                "uptime": "up 0 minutes",
                "cat /proc/device-tree/model": "Raspberry Pi 4 Model B (simulated)",
            }.get(command, "")
            return self._send(
                "EVENT",
                {"event": "COMMAND_RESULT", "ok": True, "command": command, "stdout": result},
            )
        import subprocess

        completed = subprocess.run(  # noqa: S603
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return self._send(
            "EVENT",
            {
                "event": "COMMAND_RESULT",
                "ok": completed.returncode == 0,
                "command": command,
                "stdout": completed.stdout.strip(),
                "stderr": completed.stderr.strip(),
            },
        )

    def report_gpio(self) -> list[dict[str, Any]]:
        """Emit GPIO_STATE for all pins (discovery / polling)."""
        return [self.send_gpio_state(pid, int(p["state"])) for pid, p in self._pins.items()]

    def _heartbeat_loop(self) -> None:
        while self._running:
            time.sleep(HEARTBEAT_INTERVAL_S)
            if self._running:
                self.send_heartbeat()

    def _send(self, type_: str, payload: dict[str, Any]) -> dict[str, Any]:
        self._sequence += 1
        message = {
            "version": PROTOCOL_VERSION,
            "message_id": f"{self.device_id}-{self._sequence}",
            "type": type_,
            "source": self.device_id,
            "target": "hhip",
            "sequence": self._sequence,
            "timestamp": int(time.time() * 1000),
            "payload": payload,
        }
        self._writer(json.dumps(message, separators=(",", ":")))
        return message


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="HHIP Raspberry Pi agent")
    parser.add_argument("--device-id", default="")
    parser.add_argument("--simulate", action="store_true", default=True)
    parser.add_argument("--real-gpio", action="store_true", help="Disable simulation mode")
    args = parser.parse_args(argv)
    simulate = not args.real_gpio
    agent = RaspberryPiAgent(device_id=args.device_id, simulate=simulate)
    agent.start()
    try:
        for line in sys.stdin:
            agent.handle_line(line)
    except KeyboardInterrupt:
        pass
    finally:
        agent.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
