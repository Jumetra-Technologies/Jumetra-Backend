"""A minimal in-process fake ESP32, for interactive testing without hardware.

Flagging per the project's "explain decisions that affect the future
architecture before implementing" rule: this is a testing/demo aid,
not the "Virtual Device Adapter" that later phases will build
properly. It deliberately mirrors firmware/esp32/hhip_device/hhip_device.ino's
behavior (HELLO on start, periodic HEARTBEAT, and — as of Phase 1.4 —
acknowledging STATE_UPDATE) rather than introducing protocol behavior
the firmware doesn't also have. It should be revisited (likely
replaced) once real virtual devices exist.

Decision flagged for Phase 1.4: the default device_id is now
"esp32_01", matching the real firmware's DEVICE_ID, rather than the
earlier "sim_esp32_01". That made the simulated device visually
distinct from a real one in Phase 1.3 logs, but Phase 1.4's routing
(HHIPEngine.physical_device_id, default "esp32_01") needs the two to
match for `--simulate --interactive` to actually deliver the virtual
button's STATE_UPDATE anywhere. Override device_id if you want both
a simulated device and different routing target side by side.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Optional

from ..communication.memory_adapter import InMemoryAdapter
from ..protocol.messages import MessageType, ProtocolError, create_message

logger = logging.getLogger("hhip.devices.simulated")


class SimulatedDevice:
    """Runs a background thread that behaves like the ESP32 firmware:
    sends HELLO once on start, then HEARTBEAT on a fixed interval, logs
    HELLO_ACK/ACK/ERROR replies as they arrive, and (Phase 1.4) acknowledges
    inbound STATE_UPDATE messages the way real firmware will once it has a
    physical LED to drive.
    """

    def __init__(
        self,
        adapter: InMemoryAdapter,
        device_id: str = "esp32_01",
        device_type: str = "esp32_simulated",
        heartbeat_interval: float = 5.0,
    ) -> None:
        self.adapter = adapter
        self.device_id = device_id
        self.device_type = device_type
        self.heartbeat_interval = heartbeat_interval
        self._sequence = 0
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def _next_sequence(self) -> int:
        self._sequence += 1
        return self._sequence

    def _send(self, type_: str, payload: Optional[dict] = None, target: str = "hhip") -> None:
        message = create_message(
            type_=type_,
            source=self.device_id,
            target=target,
            sequence=self._next_sequence(),
            payload=payload,
        )
        self.adapter.send(message)

    def _send_hello(self) -> None:
        self._send(
            MessageType.HELLO,
            {"device_type": self.device_type, "firmware_version": "0.1.0-sim"},
        )
        logger.info("[SIM] sent HELLO from %s", self.device_id)

    def _send_heartbeat(self) -> None:
        self._send(MessageType.HEARTBEAT, {})
        logger.info("[SIM] sent HEARTBEAT from %s", self.device_id)

    def _handle_state_update(self, message: dict) -> None:
        """Mirrors what real firmware will do: apply the requested state
        to its (simulated) physical LED and acknowledge receipt."""
        state = message.get("payload", {}).get("state")
        logger.info("[SIM] received STATE_UPDATE; simulated physical LED -> %s", state)
        self._send(MessageType.ACK, {"ack_type": MessageType.STATE_UPDATE})

    def _handle_incoming(self, message: dict) -> None:
        msg_type = message.get("type")
        if msg_type == MessageType.HELLO_ACK:
            logger.info("[SIM] received HELLO_ACK")
        elif msg_type == MessageType.ACK:
            logger.info("[SIM] received ACK")
        elif msg_type == MessageType.ERROR:
            logger.warning("[SIM] received ERROR: %s", message.get("payload"))
        elif msg_type == MessageType.STATE_UPDATE:
            self._handle_state_update(message)

    def send_button_press(self, target: str = "virtual_led_01") -> None:
        """Simulate a physical button press (Demonstration A) by sending a
        STATE_UPDATE as if a real button on this device had just been pressed."""
        self._send(MessageType.STATE_UPDATE, {"state": "ON"}, target=target)
        logger.info("[SIM] sent STATE_UPDATE (simulated button press) -> %s: ON", target)

    def _run(self) -> None:
        self.adapter.connect()
        self._send_hello()
        last_heartbeat = time.monotonic()

        while not self._stop_event.is_set():
            try:
                message = self.adapter.receive()
            except ProtocolError:
                message = None

            if message is not None:
                self._handle_incoming(message)

            now = time.monotonic()
            if now - last_heartbeat >= self.heartbeat_interval:
                self._send_heartbeat()
                last_heartbeat = now

        self.adapter.disconnect()

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True, name="simulated-device")
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self.adapter.connect()
        self._send_hello()
        last_heartbeat = time.monotonic()

        while not self._stop_event.is_set():
            try:
                message = self.adapter.receive()
            except ProtocolError:
                message = None

            if message is not None:
                self._handle_incoming(message)

            now = time.monotonic()
            if now - last_heartbeat >= self.heartbeat_interval:
                self._send_heartbeat()
                last_heartbeat = now

        self.adapter.disconnect()

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True, name="simulated-device")
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
