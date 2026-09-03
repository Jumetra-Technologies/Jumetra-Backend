"""Hybrid bridge API service."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Optional

from engine.components import default_registry
from engine.controllers import default_controller_registry
from engine.events.event_bus import EventBus
from engine.hybrid import HybridBridgeService, HybridStorage
from engine.hybrid.physical_layer import PhysicalHybridLayer


TransportFactory = Callable[[str], object]


class HybridService:
    """API wrapper for hybrid hardware experiments and physical device layer."""

    def __init__(
        self,
        bridge: Optional[HybridBridgeService] = None,
        data_dir: Path | str = "data",
        *,
        event_bus: Optional[EventBus] = None,
        transport_factory: Optional[TransportFactory] = None,
    ) -> None:
        storage = HybridStorage(data_dir)
        self._bridge = bridge or HybridBridgeService(
            default_registry(),
            default_controller_registry(),
            storage=storage,
        )
        self._physical = PhysicalHybridLayer(
            event_bus=event_bus,
            data_dir=data_dir,
            transport_factory=transport_factory,
        )

    @property
    def physical_layer(self) -> PhysicalHybridLayer:
        return self._physical

    # ---- Sprint 27 physical hybrid API ------------------------------------

    def list_physical_devices(self) -> list[dict[str, Any]]:
        return self._physical.list_devices()

    def connect_physical_device(
        self,
        *,
        port: str = "",
        endpoint: str = "",
        board_type: str = "esp32",
        device_id: str = "",
        label: str = "",
        transport: str = "",
        username: str = "pi",
    ) -> dict[str, Any]:
        return self._physical.connect_device(
            port=port,
            endpoint=endpoint,
            board_type=board_type,
            device_id=device_id,
            label=label,
            transport=transport,
            username=username,
        )

    def list_hardware_profiles(self) -> list[dict[str, Any]]:
        return self._physical.list_profiles()

    def get_physical_pins(self, device_id: str) -> list[dict[str, Any]]:
        return self._physical.get_pins(device_id)

    def create_pin_connection(
        self,
        *,
        virtual_node_id: str,
        virtual_pin_id: str,
        physical_device_id: str,
        physical_pin_id: str,
        workspace_id: str = "",
    ) -> dict[str, Any]:
        return self._physical.create_connection(
            virtual_node_id=virtual_node_id,
            virtual_pin_id=virtual_pin_id,
            physical_device_id=physical_device_id,
            physical_pin_id=physical_pin_id,
            workspace_id=workspace_id,
        )

    def list_pin_connections(self) -> list[dict[str, Any]]:
        return self._physical.list_connections()

    def poll_physical(self) -> list[dict[str, Any]]:
        return self._physical.poll()

    # ---- Sprint 25 experiment API -----------------------------------------

    def create(
        self,
        *,
        name: str,
        controller_id: str,
        component_ids: list[str],
        device_modes: Optional[dict[str, str]] = None,
        physical_device_id: str = "esp32_01",
        simulator_backend: str = "in-process",
    ) -> dict[str, Any]:
        return self._bridge.create_experiment(
            name=name,
            controller_id=controller_id,
            component_ids=component_ids,
            device_modes=device_modes,
            physical_device_id=physical_device_id,
            simulator_backend=simulator_backend,
        )

    def start(self, experiment_id: str) -> dict[str, Any]:
        return self._bridge.start(experiment_id)

    def advance(self, experiment_id: str, delta_ms: int = 100) -> dict[str, Any]:
        return self._bridge.advance(experiment_id, delta_ms)

    def stop(self, experiment_id: str) -> dict[str, Any]:
        return self._bridge.stop(experiment_id)

    def get(self, experiment_id: str) -> dict[str, Any]:
        return self._bridge.get_state(experiment_id)

    def list_experiments(self) -> list[dict[str, Any]]:
        return self._bridge.list_experiments()
