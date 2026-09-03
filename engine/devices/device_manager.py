"""Unified Device Manager for physical, virtual, and simulator devices."""

from __future__ import annotations

import logging
from typing import Optional, Union

from .base.device import Device, DeviceMode, DeviceStatus
from .base.lifecycle import DeviceLifecycleEvent, publish_lifecycle
from .base.physical_device import PhysicalDevice
from .base.simulator_device import SimulatorDevice
from .registry import Device as RegistryDevice
from .registry import DeviceRegistry
from .virtual.base_device import VirtualDevice

logger = logging.getLogger("hhip.devices.manager")

ManagedDevice = Device


class UnknownVirtualDeviceError(Exception):
    """Raised when an operation references a virtual device_id that isn't registered."""


class UnknownDeviceError(Exception):
    """Raised when an operation references a device_id that isn't registered."""


class DeviceManager:
    """Manages PhysicalDevice, VirtualDevice, and SimulatorDevice via one interface.

    Also keeps the Phase 1.3 ``DeviceRegistry`` for wire HELLO/HEARTBEAT
    bookkeeping so existing protocol paths stay intact.
    """

    def __init__(self, physical_registry: Optional[DeviceRegistry] = None) -> None:
        self.physical = physical_registry if physical_registry is not None else DeviceRegistry()
        self._devices: dict[str, Device] = {}
        self._state_manager = None
        self._event_bus = None

    def bind_state_manager(self, state_manager: object) -> None:
        """Share a StateManager with subsequently registered virtual devices."""
        self._state_manager = state_manager

    def bind_event_bus(self, event_bus: object) -> None:
        """Attach an EventBus for device lifecycle events."""
        self._event_bus = event_bus

    # ---- unified registration -----------------------------------------

    def register_device(self, device: Device) -> Device:
        """Register any Device (virtual / physical / simulated), initialize, emit event."""
        if isinstance(device, VirtualDevice) and self._state_manager is not None:
            device.bind_state_manager(self._state_manager)  # type: ignore[arg-type]

        previous_health = device.health_check()
        device.initialize()
        self._devices[device.device_id] = device

        # Mirror physical devices into the legacy registry for HELLO paths.
        if device.device_mode == DeviceMode.PHYSICAL:
            self.physical.register(
                device_id=device.device_id,
                device_type=device.device_type,
                mode=device.device_mode.to_registry(),
            )

        logger.info(
            "[DEVICE] Registered %s | Type %s | Mode %s | Status %s",
            device.device_id,
            device.device_type,
            device.device_mode.value,
            device.status.value,
        )
        publish_lifecycle(
            self._event_bus,  # type: ignore[arg-type]
            DeviceLifecycleEvent.REGISTERED,
            device,
        )
        publish_lifecycle(
            self._event_bus,  # type: ignore[arg-type]
            DeviceLifecycleEvent.CONNECTED,
            device,
        )
        new_health = device.health_check()
        if previous_health.get("status") != new_health.get("status"):
            publish_lifecycle(
                self._event_bus,  # type: ignore[arg-type]
                DeviceLifecycleEvent.HEALTH_CHANGED,
                device,
                extra_payload={"previous_status": previous_health.get("status")},
            )
        return device

    def register_physical_from_hello(
        self,
        device_id: str,
        device_type: str,
        *,
        firmware_version: Optional[str] = None,
    ) -> PhysicalDevice:
        """Upsert a PhysicalDevice when a wire HELLO arrives."""
        existing = self._devices.get(device_id)
        if isinstance(existing, PhysicalDevice):
            existing.mark_connected()
            if firmware_version:
                existing.firmware_version = firmware_version
            self.physical.register(
                device_id=device_id,
                device_type=device_type,
                mode=DeviceMode.PHYSICAL.to_registry(),
            )
            publish_lifecycle(
                self._event_bus,  # type: ignore[arg-type]
                DeviceLifecycleEvent.CONNECTED,
                existing,
            )
            return existing

        device = PhysicalDevice(
            device_id=device_id,
            device_type=device_type,
            firmware_version=firmware_version,
        )
        return self.register_device(device)  # type: ignore[return-value]

    def remove_device(self, device_id: str) -> None:
        """Remove a managed device (and registry entry if physical)."""
        device = self._devices.get(device_id)
        if device is None:
            if device_id in self.physical:
                self.physical.remove(device_id)
                logger.info("[DEVICE] Removed physical registry entry %s", device_id)
                return
            raise UnknownDeviceError(f"Unknown device_id: {device_id!r}")

        device.shutdown()
        publish_lifecycle(
            self._event_bus,  # type: ignore[arg-type]
            DeviceLifecycleEvent.DISCONNECTED,
            device,
        )
        del self._devices[device_id]
        if device_id in self.physical:
            try:
                self.physical.remove(device_id)
            except Exception:  # noqa: BLE001
                pass
        logger.info("[DEVICE] Removed %s", device_id)

    def report_error(self, device_id: str, detail: str = "") -> None:
        """Mark a device ERROR and publish DEVICE_ERROR."""
        device = self._devices.get(device_id)
        if device is None:
            raise UnknownDeviceError(f"Unknown device_id: {device_id!r}")
        previous = device.set_status(DeviceStatus.ERROR)
        publish_lifecycle(
            self._event_bus,  # type: ignore[arg-type]
            DeviceLifecycleEvent.ERROR,
            device,
            extra_payload={"detail": detail, "previous_status": previous.value},
        )
        publish_lifecycle(
            self._event_bus,  # type: ignore[arg-type]
            DeviceLifecycleEvent.HEALTH_CHANGED,
            device,
            extra_payload={"previous_status": previous.value},
        )

    def get_device(self, device_id: str) -> Optional[Union[Device, RegistryDevice]]:
        """Look up a managed Device, falling back to the physical registry record."""
        managed = self._devices.get(device_id)
        if managed is not None:
            return managed
        return self.physical.get(device_id)

    def get_devices(self) -> list[Device]:
        """Return every managed Device abstraction."""
        return list(self._devices.values())

    def find_by_type(self, device_type: str) -> list[Device]:
        return [d for d in self._devices.values() if d.device_type == device_type]

    def find_by_mode(self, mode: Union[DeviceMode, str]) -> list[Device]:
        wanted = mode if isinstance(mode, DeviceMode) else DeviceMode(str(mode).upper())
        return [d for d in self._devices.values() if d.device_mode == wanted]

    def find_by_status(self, status: Union[DeviceStatus, str]) -> list[Device]:
        wanted = status.value if isinstance(status, DeviceStatus) else str(status)
        return [d for d in self._devices.values() if d.status.value == wanted]

    def find_by_capability(self, capability: str) -> list[Device]:
        """Return devices advertising ``capability`` (data-driven, no type branching)."""
        return [d for d in self._devices.values() if d.has_capability(capability)]

    # ---- Phase 1.4 virtual helpers (compat) ---------------------------

    def register_virtual(self, device: VirtualDevice) -> VirtualDevice:
        return self.register_device(device)  # type: ignore[return-value]

    def remove_virtual(self, device_id: str) -> None:
        if device_id not in self._devices or not isinstance(
            self._devices.get(device_id), VirtualDevice
        ):
            raise UnknownVirtualDeviceError(f"Unknown virtual device_id: {device_id!r}")
        self.remove_device(device_id)

    def get_virtual(self, device_id: str) -> Optional[VirtualDevice]:
        device = self._devices.get(device_id)
        if isinstance(device, VirtualDevice):
            return device
        return None

    def all_virtual(self) -> list[VirtualDevice]:
        return [d for d in self._devices.values() if isinstance(d, VirtualDevice)]

    def all_simulated(self) -> list[SimulatorDevice]:
        return [d for d in self._devices.values() if isinstance(d, SimulatorDevice)]

    def all_physical_devices(self) -> list[PhysicalDevice]:
        return [d for d in self._devices.values() if isinstance(d, PhysicalDevice)]

    # ---- unified lookup -----------------------------------------------

    def get(self, device_id: str) -> Optional[Union[Device, RegistryDevice]]:
        return self.get_device(device_id)

    def __contains__(self, device_id: str) -> bool:
        return device_id in self._devices or device_id in self.physical
