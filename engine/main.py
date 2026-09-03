"""HHIP Engine entry point.

Phase 1.3 (PoC-01): connect to a single device and exchange
HELLO / HELLO_ACK / HEARTBEAT / ACK.

Phase 1.4: adds STATE_UPDATE routing between physical and virtual
devices via the Router (engine.routing.router), so a physical button
press can drive a VirtualLED, and a VirtualButton press can drive a
physical LED. Nothing from Phase 1.3 was redesigned to add this.

Phase 1.4.1: event backbone — every decoded protocol message becomes an
Event, is enqueued, then dispatched to subscribers (handlers, metrics,
storage). HELLO / HEARTBEAT / STATE_UPDATE behaviour is unchanged.

Phase 1.4.1A: Event Bus + lifecycle + future-ready metadata. Flow is
Communication → Event → Queue → EventBus → Subscribers.

Usage:
    python main.py COM8
    python main.py /dev/ttyUSB0 --baudrate 115200

    # No hardware available: talk to an in-process fake ESP32 instead.
    python main.py --simulate
    python main.py --simulate --heartbeat-interval 2

    # Phase 1.4: enable terminal commands to drive the demo virtual button
    # (press / release / status / quit) without a GUI.
    python main.py --simulate --interactive
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path
from typing import Optional

# Allow `python main.py PORT` to work when run directly (i.e. not via
# `python -m engine.main`), by making the project root importable so
# `engine.*` absolute imports resolve regardless of invocation style.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from engine.communication.serial_adapter import (  # noqa: E402
    DEFAULT_BAUDRATE,
    SerialAdapter,
    SerialAdapterError,
)
from engine.communication.memory_adapter import make_adapter_pair  # noqa: E402
from engine.devices.manager import DeviceManager  # noqa: E402
from engine.devices.registry import DeviceRegistry  # noqa: E402
from engine.devices.simulated_device import SimulatedDevice  # noqa: E402
from engine.devices.virtual import VirtualButton, VirtualLED  # noqa: E402
from engine.devices.base import PhysicalDevice  # noqa: E402
from engine.events import Event, EventBus, EventQueue  # noqa: E402
from engine.events.adapters import (  # noqa: E402
    LoggerSubscriber,
    MetricsSubscriber,
    ProtocolSubscriber,
    StorageSubscriber,
)
from engine.events.sync_bridge import SyncTransportSubscriber  # noqa: E402
from engine.events.correction_bridge import CorrectionTransportSubscriber  # noqa: E402
from engine.metrics import MetricsCollector  # noqa: E402
from engine.protocol.sync_wire import event_payload_from_wire_sync_response  # noqa: E402
from engine.protocol.correction_wire import event_payload_from_wire_correction_response  # noqa: E402
from engine.synchronization.physical_bridge import PhysicalCorrectionBridge  # noqa: E402
from engine.routing.router import Router  # noqa: E402
from engine.routing.router_subscriber import RouterSubscriber  # noqa: E402
from engine.state.state_manager import StateManager  # noqa: E402
from engine.storage import StorageManager  # noqa: E402
from engine.synchronization import SynchronizationManager  # noqa: E402
from engine.synchronization.coordinator import SynchronizationCoordinator  # noqa: E402
from engine.synchronization.storage import SynchronizationStorage  # noqa: E402
from engine.synchronization.strategy import FixedIntervalStrategy  # noqa: E402
from engine.protocol.messages import (  # noqa: E402
    ErrorCode,
    MessageType,
    ProtocolError,
    create_message,
    validate_message,
)

HHIP_ENGINE_ID = "hhip"
ENGINE_VERSION = "0.1.0"

# Phase 1.4 demo device ids. The default virtual devices HHIPEngine
# registers on startup, and the physical device id assumed to own the
# real button/LED pair (matches DEVICE_ID in hhip_device.ino). This is
# a PoC-01.4 simplification — one ESP32, one button, one LED — not a
# general multi-device addressing scheme.
DEFAULT_VIRTUAL_LED_ID = "virtual_led_01"
DEFAULT_VIRTUAL_BUTTON_ID = "virtual_button_01"
DEFAULT_PHYSICAL_DEVICE_ID = "esp32_01"

logger = logging.getLogger("hhip.engine")


def configure_logging(verbose: bool = False) -> None:
    """Simple readable logging for PoC-01.

    Deliberately not a full logging subsystem yet — just enough to
    produce the [RX]/[TX]/[HHIP] transcript this phase needs.
    """
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(message)s", stream=sys.stdout)


class HHIPEngine:
    """Coordinates a single connected device, plus (since Phase 1.4) any
    virtual devices registered with it.

    Accepts either a serial port (the normal, hardware path) or a
    pre-built adapter (used for --simulate, and by tests). Any object
    implementing connect()/disconnect()/send()/receive() works —
    HHIPEngine never imports or checks for SerialAdapter specifically.
    """

    def __init__(
        self,
        port: Optional[str] = None,
        baudrate: int = DEFAULT_BAUDRATE,
        adapter: Optional[object] = None,
        physical_device_id: str = DEFAULT_PHYSICAL_DEVICE_ID,
        storage_dir: str = "data",
        persist_events: bool = True,
        sync_enabled: bool = True,
        sync_interval_ms: int = 5_000,
    ) -> None:
        if adapter is not None:
            self.adapter = adapter
        else:
            if not port:
                raise ValueError("HHIPEngine requires either 'port' or 'adapter'")
            self.adapter = SerialAdapter(port=port, baudrate=baudrate)

        # Physical device registry — unchanged from Phase 1.3.
        self.registry = DeviceRegistry()
        self.events = EventQueue()
        self.event_bus = EventBus()
        self.metrics = MetricsCollector()
        self.storage = StorageManager(base_dir=storage_dir)
        self.persist_events = persist_events
        self.sync_enabled = sync_enabled
        self.sync_interval_ms = sync_interval_ms
        self._sequence = 0  # HHIP's own outgoing sequence counter
        self._last_seen_sequence: dict[str, int] = {}  # per-device inbound tracking

        # Phase 1.4: virtual devices, state history, and routing.
        # physical_device_id is where outgoing STATE_UPDATEs triggered by a
        # virtual device (e.g. VirtualButton) get sent — see the module-level
        # docstring note on the current one-ESP32/one-button/one-LED assumption.
        self.physical_device_id = physical_device_id
        self.device_manager = DeviceManager(physical_registry=self.registry)
        self.state_manager = StateManager()
        self.device_manager.bind_state_manager(self.state_manager)
        self.device_manager.bind_event_bus(self.event_bus)
        self.router = Router(
            device_manager=self.device_manager,
            state_manager=self.state_manager,
            send_callback=self._send_state_update,
        )

        # Phase 1.4.1A / 1.4.2: Event Bus subscribers (order = notification order).
        # Registered before devices so DEVICE_* lifecycle events are observed.
        self._metrics_subscriber = MetricsSubscriber(self.metrics)
        self._storage_subscriber = StorageSubscriber(self.storage, enabled=persist_events)
        self._logger_subscriber = LoggerSubscriber()
        self._router_subscriber = RouterSubscriber(
            device_manager=self.device_manager,
            state_manager=self.state_manager,
            send_callback=self._send_state_update,
        )
        self._protocol_subscriber = ProtocolSubscriber(self._on_bus_protocol_event)
        self.event_bus.register_subscriber(self._logger_subscriber)
        self.event_bus.register_subscriber(self._metrics_subscriber)
        self.event_bus.register_subscriber(self._storage_subscriber)
        self.event_bus.register_subscriber(self._router_subscriber)
        self.event_bus.register_subscriber(self._protocol_subscriber)

        # Sprint 8: sync measurement protocol (no clock correction).
        self.sync_manager = SynchronizationManager(
            self.event_bus,
            device_manager=self.device_manager,
            echo_virtual=True,
        )
        self.event_bus.register_subscriber(self.sync_manager)

        # Sprint 10: physical SYNC_REQUEST → transport (sync stays serial-free).
        self._sync_transport = SyncTransportSubscriber(
            device_manager=self.device_manager,
            send_callback=self._send_wire_message,
        )
        self.event_bus.register_subscriber(self._sync_transport)

        # Sprint 14: sync control coordinator (schedule, persist, audit).
        self.sync_storage = SynchronizationStorage(
            base_dir=str(Path(storage_dir) / "synchronization")
        )

        # Sprint 16: physical correction bridge (software clock model on device).
        self.physical_correction_bridge = PhysicalCorrectionBridge(
            self.sync_manager,
            send_callback=self._send_wire_message,
            storage=self.sync_storage,
        )
        self._correction_transport = CorrectionTransportSubscriber(
            device_manager=self.device_manager,
            send_callback=self._send_wire_message,
        )
        self.event_bus.register_subscriber(self._correction_transport)

        self.sync_coordinator = SynchronizationCoordinator(
            self.sync_manager,
            self.sync_storage,
            strategy=FixedIntervalStrategy(sync_interval_ms),
            default_interval_ms=sync_interval_ms,
        )

        self.virtual_led = VirtualLED(DEFAULT_VIRTUAL_LED_ID)
        self.device_manager.register_device(self.virtual_led)

        self.virtual_button = VirtualButton(
            DEFAULT_VIRTUAL_BUTTON_ID,
            publish=self._publish_device_event,
            default_target=self.physical_device_id,
        )
        self.device_manager.register_device(self.virtual_button)

    def _next_sequence(self) -> int:
        self._sequence += 1
        return self._sequence

    def _send(self, type_: str, target: str, payload: Optional[dict] = None) -> None:
        message = create_message(
            type_=type_,
            source=HHIP_ENGINE_ID,
            target=target,
            sequence=self._next_sequence(),
            payload=payload,
        )
        self.adapter.send(message)
        logger.info("[TX] %s", type_)

    def _send_wire_message(self, message: dict) -> None:
        """Transmit a fully-formed wire envelope (used by SyncTransportSubscriber)."""
        self.adapter.send(message)
        logger.info("[TX] %s", message.get("type", "?"))

    def _check_sequence(self, device_id: str, sequence: int) -> None:
        """Basic out-of-order / duplicate detection.

        PoC-01 only logs a warning; rejecting or requesting
        retransmission is future work once reliability semantics are
        defined.
        """
        last = self._last_seen_sequence.get(device_id)
        if last is not None:
            if sequence == last:
                logger.warning("[HHIP] Duplicate sequence %d from %s", sequence, device_id)
            elif sequence < last:
                logger.warning(
                    "[HHIP] Out-of-order message from %s (got %d, last %d)",
                    device_id,
                    sequence,
                    last,
                )
        self._last_seen_sequence[device_id] = sequence

    def _handle_hello(self, message: dict) -> None:
        device_id = message["source"]
        payload = message.get("payload", {})
        device_type = payload.get("device_type", "unknown")

        self.device_manager.register_physical_from_hello(
            device_id=device_id,
            device_type=device_type,
            firmware_version=payload.get("firmware_version"),
        )
        logger.info("[HHIP] Device registered: %s", device_id)

        self._send(
            MessageType.HELLO_ACK,
            target=device_id,
            payload={"engine_version": ENGINE_VERSION},
        )

    def _handle_heartbeat(self, message: dict) -> None:
        device_id = message["source"]

        if device_id not in self.registry:
            logger.warning("[HHIP] HEARTBEAT from unregistered device: %s", device_id)
            self.metrics.record_error()
            self._send(
                MessageType.ERROR,
                target=device_id,
                payload={
                    "code": ErrorCode.UNKNOWN_DEVICE,
                    "detail": f"Unknown device: {device_id}",
                },
            )
            return

        self.registry.touch(device_id)
        physical = self.device_manager.get_device(device_id)
        if isinstance(physical, PhysicalDevice):
            physical.touch()
        self._send(MessageType.ACK, target=device_id, payload={"ack_type": MessageType.HEARTBEAT})

    def _handle_state_update(self, message: dict) -> None:
        """Acknowledge an inbound wire STATE_UPDATE after RouterSubscriber delivery.

        Routing itself is owned by :class:`RouterSubscriber`. This handler
        only ACKs transport receipt for protocol-originated events.
        """
        if self.persist_events:
            self.storage.save_snapshot(self.state_manager.get_all_states())
        self._send(
            MessageType.ACK, target=message["source"], payload={"ack_type": MessageType.STATE_UPDATE}
        )

    def _publish_device_event(
        self, event_type: str, source: str, target: str, payload: dict
    ) -> None:
        """Publish a device-originated Event onto the queue / Event Bus."""
        event = Event.create(
            event_type=event_type,
            source=source,
            target=target,
            payload=payload,
            metadata={"origin": "virtual_device"},
        )
        self.events.add_event(event)
        queued = self.events.get_event(block=False)
        if queued is not None:
            self._publish_queued_event(queued)

    def _log_event_created(self, event: Event) -> None:
        logger.info(
            "[EVENT CREATED] %s | id=%s | corr=%s | seq=%s | priority=%s | status=%s",
            event.event_type,
            event.event_id,
            event.correlation_id,
            event.sequence_number,
            event.priority.value,
            event.current_status.value,
        )

    def _on_bus_protocol_event(self, event: Event, message: dict) -> None:
        """ProtocolSubscriber callback: HELLO / HEARTBEAT / inbound ACK."""
        msg_type = event.event_type
        if msg_type.startswith("DEVICE_") or msg_type.startswith("SYNC_") or msg_type in (
            "CLOCK_SAMPLE",
            "SYNC_MEASUREMENT",
            "SYNC_REQUEST",
            "SYNC_RESPONSE",
        ):
            return  # lifecycle / sync protocol — not wire HELLO/HEARTBEAT handlers
        if msg_type == MessageType.HELLO:
            self._handle_hello(message)
        elif msg_type == MessageType.HEARTBEAT:
            self._handle_heartbeat(message)
        elif msg_type == MessageType.STATE_UPDATE:
            # Delivery is handled by RouterSubscriber; ACK only wire-originated.
            if event.metadata.get("origin") == "protocol":
                self._handle_state_update(message)
        else:
            logger.info(
                "[HHIP] No handler for message type %s in this phase; ignoring", msg_type
            )

    def _publish_queued_event(self, event: Event) -> None:
        """Publish a dequeued event through the Event Bus and record metrics."""
        started = time.perf_counter()
        error = False
        try:
            self.event_bus.publish(event)
            self.metrics.mark_processed()
        except Exception:
            error = True
            self.metrics.record_error()
            logger.exception("[HHIP] Error while publishing event %s", event.event_id)
        finally:
            duration_ms = (time.perf_counter() - started) * 1000.0
            self.metrics.record_processing_time(duration_ms)
            latencies = self.metrics.record_event_latencies(event)
            if self.persist_events:
                self.storage.save_metric(
                    {
                        "event_id": event.event_id,
                        "event_type": event.event_type,
                        "correlation_id": event.correlation_id,
                        "sequence_number": event.sequence_number,
                        "processing_time_ms": duration_ms,
                        "timestamp": event.timestamp,
                        "timing": dict(event.timing),
                        "latencies": latencies,
                        "error": error,
                    }
                )

    def _send_state_update(self, target: str, payload: dict) -> None:
        """Router / RouterSubscriber send_callback: encode+transmit STATE_UPDATE."""
        self._send(MessageType.STATE_UPDATE, target=target, payload=payload)

    def _on_virtual_button_change(
        self, button: VirtualButton, previous_state: str, new_state: str
    ) -> None:
        """Legacy Demo B callback — kept for compatibility; prefer Event Bus publish."""
        if self.physical_device_id not in self.registry:
            logger.warning(
                "[HHIP] Virtual button pressed but physical device %r is not connected; "
                "cannot deliver STATE_UPDATE",
                self.physical_device_id,
            )
            return

        payload = {"state": "ON" if new_state == VirtualButton.PRESSED else "OFF"}
        self.router.route_outgoing(
            target=self.physical_device_id,
            payload=payload,
            source_device=button,
            previous_state=previous_state,
        )

    def press_virtual_button(self, device_id: str = DEFAULT_VIRTUAL_BUTTON_ID) -> None:
        """Convenience entry point for triggering Demonstration B — used by
        --interactive terminal commands, and directly by tests/examples."""
        device = self.device_manager.get_virtual(device_id)
        if not isinstance(device, VirtualButton):
            logger.warning("[HHIP] %r is not a VirtualButton; cannot press", device_id)
            return
        device.press()

    def release_virtual_button(self, device_id: str = DEFAULT_VIRTUAL_BUTTON_ID) -> None:
        device = self.device_manager.get_virtual(device_id)
        if not isinstance(device, VirtualButton):
            logger.warning("[HHIP] %r is not a VirtualButton; cannot release", device_id)
            return
        device.release()

    def print_status(self) -> None:
        """Terminal-friendly snapshot of every known device. No GUI —
        just readable log lines, per the Phase 1.4 constraint."""
        logger.info("[HHIP] --- Status ---")
        for device in self.device_manager.all_virtual():
            logger.info("[HHIP] virtual  %-20s %s", device.device_id, device.state)
        for device in self.registry.all_devices():
            logger.info("[HHIP] physical %-20s %s", device.device_id, device.status)
        if self.sync_enabled:
            logger.info(
                "[HHIP] sync sessions=%d scheduled=%d",
                len(self.sync_coordinator.sessions),
                len(self.sync_coordinator.scheduler.all_schedules()),
            )

    def sync_startup(self) -> None:
        """Load persisted sync state and schedule known devices."""
        if not self.sync_enabled:
            return
        self.sync_coordinator.startup()
        for device in self.registry.all_devices():
            self.sync_coordinator.schedule_device(
                device.device_id, interval_ms=self.sync_interval_ms
            )
        for device in self.device_manager.all_virtual():
            self.sync_coordinator.schedule_device(
                device.device_id, interval_ms=self.sync_interval_ms
            )
        recovered = self.physical_correction_bridge.recover_on_startup()
        if recovered:
            logger.info("[HHIP] Recovered %d correction transaction(s)", len(recovered))

    def sync_poll(self) -> list[str]:
        """Poll synchronization scheduler (runtime hook)."""
        if not self.sync_enabled:
            return []
        self.physical_correction_bridge.poll_pending_wire()
        return self.sync_coordinator.poll()

    def sync_shutdown(self) -> None:
        """Persist synchronization state on engine shutdown."""
        if not self.sync_enabled:
            return
        self.sync_coordinator.shutdown()

    def handle_message(self, message: dict) -> None:
        """Adapt one decoded, validated message into the event backbone.

        Flow (Phase 1.4.1A)::

            Protocol message → Event → EventQueue → EventBus → Subscribers
                (logger, metrics, storage, protocol handlers)

        HELLO, HEARTBEAT, and STATE_UPDATE behaviour is unchanged from
        Phases 1.3 / 1.4; only the surrounding event pipeline is new.
        """
        msg_type = message["type"]
        device_id = message["source"]
        logger.info("[RX] %s from %s", msg_type, device_id)

        self._check_sequence(device_id, message["sequence"])

        event = Event.from_message(message)
        # Sprint 10: normalize physical SYNC_RESPONSE payload keys for the manager.
        if msg_type == MessageType.SYNC_RESPONSE and isinstance(event.payload, dict):
            event.payload.clear()
            event.payload.update(event_payload_from_wire_sync_response(message))
            corr = event.payload.get("correlation_id")
            if corr:
                event.correlation_id = str(corr)

        if msg_type == MessageType.SYNC_CORRECTION_RESPONSE and isinstance(
            event.payload, dict
        ):
            event.payload.clear()
            event.payload.update(event_payload_from_wire_correction_response(message))
            if self.sync_enabled:
                self.physical_correction_bridge.handle_correction_response(event.payload)

        self._log_event_created(event)
        self.events.add_event(event)
        logger.info(
            "[QUEUED] id=%s corr=%s seq=%s priority=%s status=%s",
            event.event_id,
            event.correlation_id,
            event.sequence_number,
            event.priority.value,
            event.current_status.value,
        )

        # Drain FIFO: preserve ordering for future multi-producer use while
        # processing synchronously on the communication thread for now.
        queued = self.events.get_event(block=False)
        if queued is not None:
            self._publish_queued_event(queued)

    def run(self) -> None:
        logger.info("[HHIP] Connecting to %s...", self.adapter.port)
        self.adapter.connect()  # SerialAdapterError propagates to caller
        logger.info("[HHIP] Connected.")
        logger.info("")
        self.sync_startup()

        try:
            while True:
                try:
                    message = self.adapter.receive()
                except ProtocolError as exc:
                    logger.warning("[HHIP] Dropped unparseable message: %s", exc)
                    continue

                if message is None:
                    self.sync_poll()
                    continue  # read timeout; keep listening

                errors = validate_message(message)
                if errors:
                    logger.warning("[HHIP] Invalid message: %s", "; ".join(errors))
                    continue

                self.handle_message(message)
                self.sync_poll()
        except KeyboardInterrupt:
            logger.info("")
            logger.info("[HHIP] Interrupted, shutting down.")
        finally:
            self.sync_shutdown()
            self.adapter.disconnect()
            logger.info("[HHIP] Disconnected.")


def parse_args(argv: Optional[list] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="hhip-engine",
        description="HHIP Engine PoC-01: HELLO/HELLO_ACK/HEARTBEAT/ACK over serial "
        "(or --simulate, no hardware required).",
    )
    parser.add_argument(
        "port",
        nargs="?",
        default=None,
        help="Serial port to connect to, e.g. COM8 or /dev/ttyUSB0. "
        "Omit when using --simulate.",
    )
    parser.add_argument(
        "--baudrate",
        type=int,
        default=DEFAULT_BAUDRATE,
        help=f"Baud rate (default: {DEFAULT_BAUDRATE})",
    )
    parser.add_argument(
        "--simulate",
        action="store_true",
        help="Run against an in-process simulated ESP32 instead of a real serial "
        "port. No hardware, port, or baudrate required.",
    )
    parser.add_argument(
        "--heartbeat-interval",
        type=float,
        default=5.0,
        help="Simulated device's heartbeat interval in seconds. "
        "Only used with --simulate (default: 5.0).",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Enable terminal commands (press / release / status / quit) to "
        "drive the demo virtual button without a GUI (Phase 1.4 Demonstration B).",
    )
    parser.add_argument(
        "--physical-device-id",
        default=DEFAULT_PHYSICAL_DEVICE_ID,
        help=f"Device id that owns the physical button/LED, for routing outgoing "
        f"STATE_UPDATEs triggered by the virtual button (default: {DEFAULT_PHYSICAL_DEVICE_ID!r}).",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")

    args = parser.parse_args(argv)
    if not args.simulate and not args.port:
        parser.error("port is required unless --simulate is given")
    return args


def _run_interactive_stdin(engine: "HHIPEngine") -> None:
    """Background thread: reads simple text commands from stdin so
    Demonstration B (virtual button -> physical LED) can be triggered
    without a GUI. Intentionally minimal: press / release / status / quit.

    Runs on its own thread since engine.run() blocks its thread reading
    from the transport. Concurrent send() (from here) and receive()
    (from engine.run()) on the same adapter is expected to be safe for
    serial/in-memory transports in this phase, but hasn't been stress
    tested — noted as a limitation in docs/phase-1.4.md.
    """
    print("[HHIP] Interactive mode: type 'press', 'release', 'status', or 'quit'.")
    for line in sys.stdin:
        command = line.strip().lower()
        if not command:
            continue
        if command in ("quit", "exit"):
            break
        elif command == "press":
            engine.press_virtual_button()
        elif command == "release":
            engine.release_virtual_button()
        elif command == "status":
            engine.print_status()
        else:
            print(f"[HHIP] Unknown command: {command!r} (try: press, release, status, quit)")


def main(argv: Optional[list] = None) -> int:
    args = parse_args(argv)
    configure_logging(verbose=args.verbose)

    simulated_device: Optional[SimulatedDevice] = None

    if args.simulate:
        logger.info("[HHIP] --simulate: running against an in-process fake ESP32.")
        logger.info("[HHIP] No hardware, serial port, or baudrate needed.")
        logger.info("")
        engine_adapter, device_adapter = make_adapter_pair()
        simulated_device = SimulatedDevice(
            adapter=device_adapter, heartbeat_interval=args.heartbeat_interval
        )
        simulated_device.start()
        engine = HHIPEngine(adapter=engine_adapter, physical_device_id=args.physical_device_id)
    else:
        engine = HHIPEngine(
            port=args.port, baudrate=args.baudrate, physical_device_id=args.physical_device_id
        )

    if args.interactive:
        import threading

        threading.Thread(
            target=_run_interactive_stdin, args=(engine,), daemon=True, name="interactive-stdin"
        ).start()

    try:
        engine.run()
    except SerialAdapterError as exc:
        logger.error("[HHIP] Connection failed: %s", exc)
        return 1
    finally:
        if simulated_device is not None:
            simulated_device.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
