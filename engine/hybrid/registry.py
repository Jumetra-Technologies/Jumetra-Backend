"""Registry of connected physical hybrid devices (universal hardware)."""

from __future__ import annotations

import threading
from typing import Any, Optional, Union

from .device_agent import DeviceAgent
from .hardware import HardwareDevice, get_profile_registry
from .physical_device import PhysicalDevice
from .transports.hardware_transport import HardwareTransport

# Supported board families for Sprint 28
SUPPORTED_BOARD_TYPES = frozenset(
    {
        "esp32",
        "esp8266",
        "arduino-uno",
        "arduino-mega",
        "arduino-nano",
        "arduino",
        "stm32",
        "raspberry-pi-4",
        "raspberry-pi-pico",
        "raspberry-pi",
        "pico",
        "teensy",
        "nrf52",
        "microbit",
        "particle-photon",
        "adafruit-feather",
    }
)


class HybridRegistry:
    """Track active physical devices across serial, MQTT, and SSH transports."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._devices: dict[str, PhysicalDevice] = {}
        self._agents: dict[str, DeviceAgent] = {}
        self._transports: dict[str, HardwareTransport] = {}

    @staticmethod
    def supported_board_types() -> list[str]:
        profiles = get_profile_registry().list_profiles()
        ids = sorted({p.board_type for p in profiles})
        return ids or sorted(SUPPORTED_BOARD_TYPES)

    def list_devices(self) -> list[dict[str, Any]]:
        with self._lock:
            return [d.to_dict() for d in self._devices.values()]

    def get_device(self, device_id: str) -> Optional[PhysicalDevice]:
        with self._lock:
            return self._devices.get(device_id)

    def get_agent(self, device_id: str) -> Optional[DeviceAgent]:
        with self._lock:
            return self._agents.get(device_id)

    def get_transport(self, device_id: str) -> Optional[HardwareTransport]:
        with self._lock:
            return self._transports.get(device_id)

    def register(
        self,
        device: Union[PhysicalDevice, HardwareDevice],
        agent: DeviceAgent,
        transport: HardwareTransport,
    ) -> None:
        if isinstance(device, HardwareDevice):
            device = PhysicalDevice.from_hardware(device)
        with self._lock:
            self._devices[device.device_id] = device
            self._agents[device.device_id] = agent
            self._transports[device.device_id] = transport

    def unregister(self, device_id: str) -> Optional[PhysicalDevice]:
        with self._lock:
            agent = self._agents.pop(device_id, None)
            transport = self._transports.pop(device_id, None)
            device = self._devices.pop(device_id, None)
            if agent:
                try:
                    agent.disconnect()
                except Exception:
                    pass
            elif transport:
                try:
                    transport.disconnect()
                except Exception:
                    pass
            return device

    def disconnect(self, device_id: str) -> bool:
        removed = self.unregister(device_id)
        return removed is not None

    def poll_all(self) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        with self._lock:
            agents = list(self._agents.values())
        for agent in agents:
            events.extend(agent.poll())
        return events

    def profiles(self) -> list[dict[str, Any]]:
        return [p.to_dict() for p in get_profile_registry().list_profiles()]


# Backward-compatible alias
PhysicalDeviceRegistry = HybridRegistry
