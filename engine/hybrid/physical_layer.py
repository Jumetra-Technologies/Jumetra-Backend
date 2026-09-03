"""Physical hybrid device layer — connect, manage, and route GPIO."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Optional

from engine.events.event_bus import EventBus

from .device_agent import DeviceAgent
from .events import HybridEventType, publish_hybrid_event
from .hardware import get_profile_registry
from .hybrid_router import HybridRouter
from .physical_device import PhysicalDevice
from .pin_mapper import PinMapper
from .registry import HybridRegistry, PhysicalDeviceRegistry
from .transports import create_transport


TransportFactory = Callable[[str], object]


class PhysicalHybridLayer:
    """Sprint 27/28 physical hybrid orchestrator (universal transports)."""

    def __init__(
        self,
        *,
        event_bus: Optional[EventBus] = None,
        data_dir: Path | str = "data",
        transport_factory: Optional[TransportFactory] = None,
        profiles_dir: Optional[Path | str] = None,
    ) -> None:
        base = Path(data_dir)
        hybrid_dir = base / "hybrid"
        profiles = profiles_dir or (base / "hardware_profiles")
        # Ensure profile registry sees project profiles
        get_profile_registry(profiles if Path(profiles).exists() else None)
        self.event_bus = event_bus or EventBus()
        self.registry: HybridRegistry = PhysicalDeviceRegistry()
        self.pin_mapper = PinMapper(storage_path=hybrid_dir / "pin_connections.json")
        self.router = HybridRouter(self.registry, self.pin_mapper, event_bus=self.event_bus)
        self.event_bus.register_subscriber(self.router)
        self._transport_factory = transport_factory
        self._profiles_dir = profiles if Path(profiles).exists() else None

    def list_devices(self) -> list[dict[str, Any]]:
        return self.registry.list_devices()

    def list_profiles(self) -> list[dict[str, Any]]:
        return self.registry.profiles()

    def get_device(self, device_id: str) -> Optional[dict[str, Any]]:
        device = self.registry.get_device(device_id)
        return device.to_dict() if device else None

    def get_pins(self, device_id: str) -> list[dict[str, Any]]:
        device = self.registry.get_device(device_id)
        if device is None:
            raise KeyError(f"device not found: {device_id}")
        return device.list_pins()

    def connect_device(
        self,
        *,
        port: str = "",
        endpoint: str = "",
        board_type: str = "esp32",
        device_id: str = "",
        label: str = "",
        baudrate: int = 115200,
        wait_discovery_s: float = 1.5,
        transport: str = "",
        username: str = "pi",
    ) -> dict[str, Any]:
        profile = get_profile_registry(self._profiles_dir).resolve_board_type(board_type)
        transport_kind = transport or profile.default_transport or "serial"
        ep = endpoint or port
        if not ep:
            raise ValueError("port or endpoint is required")

        kwargs: dict[str, Any] = {}
        if transport_kind in ("serial", "memory"):
            kwargs["baudrate"] = baudrate
            if self._transport_factory is not None:
                kwargs["adapter_factory"] = self._transport_factory
            if transport_kind == "memory":
                transport_kind = "serial"
        elif transport_kind == "ssh":
            kwargs["username"] = username

        hw_transport = create_transport(transport_kind, ep, **kwargs)

        def _on_drop() -> None:
            if agent.device:
                self.router.publish_disconnected(agent.device.device_id)
                self.registry.unregister(agent.device.device_id)

        hw_transport.set_disconnect_callback(_on_drop)
        agent = DeviceAgent(hw_transport, device_id=device_id)
        agent.connect()

        discovered = agent.wait_for_discovery(timeout_s=wait_discovery_s)
        if discovered is None:
            discovered = PhysicalDevice.from_discovery(
                device_id=device_id
                or f"{board_type}_{ep.replace('/', '_').replace(chr(92), '_')}",
                board_type=board_type,
                port=ep,
                label=label or profile.label,
                transport=transport_kind,
                vendor=profile.vendor,
                manufacturer=profile.vendor,
                profiles_dir=self._profiles_dir,
            )
            agent.device_id = discovered.device_id
            agent._device = discovered  # noqa: SLF001

        discovered.connected = True
        discovered.connection_state = "connected"
        discovered.transport = transport_kind
        if not discovered.vendor:
            discovered.vendor = profile.vendor
            discovered.manufacturer = profile.vendor
            discovered.model = profile.model
            discovered.category = profile.category
            discovered.interfaces = list(profile.interfaces)
            discovered.profile_id = profile.profile_id
        self.registry.register(discovered, agent, hw_transport)
        payload = discovered.to_dict()
        self.router.publish_connected(payload)
        return payload

    def connect_from_discovery(self, discovery_device: dict[str, Any]) -> dict[str, Any]:
        board_type = str(discovery_device.get("board_type") or "unknown")
        profile = get_profile_registry(self._profiles_dir).resolve_board_type(board_type)
        return self.connect_device(
            port=str(discovery_device.get("port") or discovery_device.get("endpoint") or ""),
            board_type=board_type,
            device_id=str(discovery_device.get("device_id") or ""),
            label=str(discovery_device.get("label") or ""),
            transport=str(discovery_device.get("transport") or profile.default_transport),
        )

    def disconnect_device(self, device_id: str) -> dict[str, Any]:
        removed = self.registry.disconnect(device_id)
        if removed is None:
            raise KeyError(f"device not found: {device_id}")
        self.router.publish_disconnected(device_id)
        return {"device_id": device_id, "disconnected": True}

    def create_connection(
        self,
        *,
        virtual_node_id: str,
        virtual_pin_id: str,
        physical_device_id: str,
        physical_pin_id: str,
        workspace_id: str = "",
    ) -> dict[str, Any]:
        device = self.registry.get_device(physical_device_id)
        if device is None:
            raise KeyError(f"physical device not found: {physical_device_id}")
        physical_pin = device.get_pin(physical_pin_id)
        physical_ifaces = physical_pin.interfaces if physical_pin else ["gpio"]
        record = self.pin_mapper.create_connection(
            virtual_node_id=virtual_node_id,
            virtual_pin_id=virtual_pin_id,
            physical_device_id=physical_device_id,
            physical_pin_id=physical_pin_id,
            workspace_id=workspace_id,
        )
        record["issues"] = PinMapper.validate(
            virtual_pin_id=virtual_pin_id,
            physical_pin_id=physical_pin_id,
            virtual_interfaces=["digital", "gpio"],
            physical_interfaces=physical_ifaces,
        )
        record["valid"] = not record["issues"]
        if self.event_bus:
            publish_hybrid_event(
                self.event_bus,
                HybridEventType.HYBRID_BINDING_CREATED,
                source=physical_device_id,
                payload=record,
            )
        return record

    def list_connections(self) -> list[dict[str, Any]]:
        return self.pin_mapper.list_connections()

    def poll(self) -> list[dict[str, Any]]:
        return self.router.poll_physical()

    def write_gpio(self, device_id: str, pin_id: str, value: int, **kwargs: Any) -> dict[str, Any]:
        return self.router.write_gpio(device_id, pin_id, value, **kwargs)
