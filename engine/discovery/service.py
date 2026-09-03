"""Background hardware discovery with hot-plug detection."""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Optional

from engine.communication.serial_adapter import SerialAdapter, SerialAdapterError
from engine.devices.base.lifecycle import DeviceLifecycleEvent
from engine.devices.device_manager import DeviceManager
from engine.events.event import Event
from engine.events.event_bus import EventBus
from engine.events.dashboard_publisher import DashboardEventPublisher

from .handshake import perform_handshake
from .identify import identify_board
from .models import DiscoveredDevice, DiscoveryStatus
from .scanner import PortInfo, default_port_lister

logger = logging.getLogger("hhip.discovery")

TransportFactory = Callable[[str], object]
ChangeCallback = Callable[[list[DiscoveredDevice]], None]


class HardwareDiscoveryService:
    """Scan USB serial ports, identify boards, and perform HHIP handshake."""

    def __init__(
        self,
        *,
        event_bus: Optional[EventBus] = None,
        device_manager: Optional[DeviceManager] = None,
        dashboard_publisher: Optional[DashboardEventPublisher] = None,
        scan_interval_s: float = 2.0,
        port_lister: Optional[Callable[[], list[PortInfo]]] = None,
        transport_factory: Optional[TransportFactory] = None,
        on_change: Optional[ChangeCallback] = None,
    ) -> None:
        self._event_bus = event_bus or EventBus()
        self._device_manager = device_manager or DeviceManager()
        self._device_manager.bind_event_bus(self._event_bus)
        self._dashboard = dashboard_publisher
        self._scan_interval_s = scan_interval_s
        self._port_lister = port_lister or default_port_lister
        self._transport_factory = transport_factory or (
            lambda port: SerialAdapter(port, timeout=0.3)
        )
        self._on_change = on_change
        self._lock = threading.RLock()
        self._devices: dict[str, DiscoveredDevice] = {}
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._running = False

    @property
    def event_bus(self) -> EventBus:
        return self._event_bus

    @property
    def device_manager(self) -> DeviceManager:
        return self._device_manager

    def start(self) -> None:
        if self._running:
            return
        self._stop.clear()
        self._running = True
        self._thread = threading.Thread(target=self._scan_loop, name="hhip-discovery", daemon=True)
        self._thread.start()
        logger.info("[DISCOVERY] Started (interval=%ss)", self._scan_interval_s)

    def stop(self) -> None:
        self._running = False
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=self._scan_interval_s + 2)
        self._thread = None
        logger.info("[DISCOVERY] Stopped")

    def scan_once(self) -> list[DiscoveredDevice]:
        """Run a single discovery pass (thread-safe)."""
        with self._lock:
            return self._scan_locked()

    def list_devices(self) -> list[DiscoveredDevice]:
        with self._lock:
            return list(self._devices.values())

    def get_device(self, port: str) -> Optional[DiscoveredDevice]:
        with self._lock:
            return self._devices.get(port)

    def _scan_loop(self) -> None:
        while self._running and not self._stop.is_set():
            try:
                self.scan_once()
            except Exception:
                logger.exception("[DISCOVERY] Scan pass failed")
            self._stop.wait(self._scan_interval_s)

    def _scan_locked(self) -> list[DiscoveredDevice]:
        now_ms = int(time.time() * 1000)
        try:
            ports = self._port_lister()
        except Exception as exc:  # noqa: BLE001
            logger.exception("[DISCOVERY] Port list failed: %s", exc)
            ports = []
        seen: set[str] = set()

        for info in ports:
            seen.add(info.device)
            board_type, label = identify_board(
                vid=info.vid,
                pid=info.pid,
                description=info.description,
                manufacturer=info.manufacturer,
            )
            existing = self._devices.get(info.device)
            if existing is None:
                device = DiscoveredDevice.from_port_info(
                    info.device,
                    vid=info.vid,
                    pid=info.pid,
                    manufacturer=info.manufacturer,
                    description=info.description,
                    serial_number=info.serial_number,
                    board_type=board_type,
                    label=label,
                    last_seen_ms=now_ms,
                )
                self._devices[info.device] = device
                self._probe_device(device, is_new=True)
            else:
                prev_status = existing.status
                existing.last_seen_ms = now_ms
                existing.vid = info.vid
                existing.pid = info.pid
                existing.manufacturer = info.manufacturer
                existing.description = info.description
                existing.serial_number = info.serial_number
                if prev_status == DiscoveryStatus.DISCONNECTED:
                    existing.board_type = board_type
                    existing.label = label
                    existing.status = DiscoveryStatus.CONNECTING
                    existing.error = None
                    self._probe_device(existing, is_new=True)
                elif existing.board_type == "unknown-serial" and board_type != "unknown-serial":
                    existing.board_type = board_type
                    existing.label = label

        # Hot-unplug
        for port, device in list(self._devices.items()):
            if port not in seen:
                if device.status != DiscoveryStatus.DISCONNECTED:
                    self._mark_disconnected(device, reason="Port removed")

        devices = list(self._devices.values())
        self._notify_change(devices)
        return devices

    def _probe_device(self, device: DiscoveredDevice, *, is_new: bool = False) -> None:
        device.status = DiscoveryStatus.CONNECTING
        device.error = None
        transport = self._transport_factory(device.port)
        try:
            transport.connect()  # type: ignore[attr-defined]
        except (SerialAdapterError, OSError, Exception) as exc:  # noqa: BLE001
            msg = str(exc).lower()
            if "access" in msg or "busy" in msg or "permission" in msg:
                device.status = DiscoveryStatus.BUSY
            else:
                device.status = DiscoveryStatus.ERROR
            device.error = str(exc)
            return

        try:
            result = perform_handshake(transport)  # type: ignore[arg-type]
        finally:
            try:
                transport.disconnect()  # type: ignore[attr-defined]
            except Exception:
                pass

        if result.success and result.hhip_firmware:
            device.status = DiscoveryStatus.CONNECTED
            device.hhip_firmware = True
            device.device_id = result.device_id
            device.firmware_version = result.firmware_version
            device.capabilities = list(result.capabilities)
            if result.device_type and result.device_type != "unknown":
                device.board_type = _normalize_board_type(result.device_type)
                device.label = _label_for_board(device.board_type)
            device.error = None
            self._register_physical(device)
            if is_new:
                self._publish_connected(device)
        elif device.board_type != "unknown-serial":
            device.status = DiscoveryStatus.CONNECTED
            device.hhip_firmware = False
            device.error = result.error or "HHIP firmware not detected"
            if is_new:
                self._publish_connected(device, partial=True)
        else:
            device.status = DiscoveryStatus.CONNECTED
            device.hhip_firmware = False
            device.label = "Unknown Serial Device"
            device.error = result.error or "Install or upload HHIP firmware"
            if is_new:
                self._publish_connected(device, partial=True)

    def _mark_disconnected(self, device: DiscoveredDevice, *, reason: str = "") -> None:
        previous_id = device.device_id
        device.status = DiscoveryStatus.DISCONNECTED
        device.error = reason or None
        device.hhip_firmware = False
        if previous_id and self._device_manager.get_device(previous_id):
            try:
                self._device_manager.remove_device(previous_id)
            except Exception:
                pass
        device.device_id = None
        self._publish_disconnected(device, previous_id=previous_id)

    def _register_physical(self, device: DiscoveredDevice) -> None:
        if not device.device_id:
            device.device_id = f"{device.board_type}_{device.port.replace('/', '_').replace(chr(92), '_')}"
        try:
            self._device_manager.register_physical_from_hello(
                device.device_id,
                device.board_type,
                firmware_version=device.firmware_version,
            )
        except Exception:
            logger.exception("[DISCOVERY] Failed to register %s", device.device_id)

    def _publish_connected(self, device: DiscoveredDevice, *, partial: bool = False) -> None:
        payload = device.to_dict()
        payload["partial"] = partial
        self._publish_bus(DeviceLifecycleEvent.CONNECTED, device)
        if self._dashboard:
            self._dashboard.publish_device_connected(
                device.device_id or device.port,
                **payload,
            )

    def _publish_disconnected(self, device: DiscoveredDevice, *, previous_id: Optional[str]) -> None:
        payload = device.to_dict()
        payload["previous_device_id"] = previous_id
        self._publish_bus(DeviceLifecycleEvent.DISCONNECTED, device)
        if self._dashboard:
            self._dashboard.publish_device_disconnected(
                previous_id or device.port,
                **payload,
            )

    def _publish_bus(self, event_type: str, device: DiscoveredDevice) -> None:
        event = Event.create(
            event_type=event_type,
            source=device.device_id or device.port,
            target="hhip",
            payload=device.to_dict(),
            metadata={"origin": "hardware_discovery"},
        )
        self._event_bus.publish(event)

    def _notify_change(self, devices: list[DiscoveredDevice]) -> None:
        if self._on_change:
            try:
                self._on_change(devices)
            except Exception:
                logger.exception("[DISCOVERY] on_change callback failed")


def _normalize_board_type(device_type: str) -> str:
    dt = device_type.lower().replace(" ", "-")
    mapping = {
        "esp32": "esp32",
        "esp8266": "esp8266",
        "arduino-uno": "arduino-uno",
        "arduino_uno": "arduino-uno",
        "uno": "arduino-uno",
        "mega": "arduino-mega",
        "arduino-mega": "arduino-mega",
        "nano": "arduino-nano",
        "stm32": "stm32",
        "pico": "raspberry-pi-pico",
        "raspberry-pi-pico": "raspberry-pi-pico",
    }
    return mapping.get(dt, dt)


def _label_for_board(board_type: str) -> str:
    labels = {
        "esp32": "ESP32 DevKit V1",
        "esp8266": "ESP8266",
        "arduino-uno": "Arduino Uno R3",
        "arduino-mega": "Arduino Mega 2560",
        "arduino-nano": "Arduino Nano",
        "stm32": "STM32 Blue Pill",
        "raspberry-pi-pico": "Raspberry Pi Pico",
    }
    return labels.get(board_type, board_type)
