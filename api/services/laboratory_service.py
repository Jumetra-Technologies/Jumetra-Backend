"""Virtual laboratory API service."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from engine.components import default_registry
from engine.controllers import default_controller_registry
from engine.simulation import LaboratoryStorage, VirtualLaboratoryService


class LaboratoryService:
    """API wrapper for virtual laboratory and simulation operations."""

    def __init__(
        self,
        lab_service: Optional[VirtualLaboratoryService] = None,
        data_dir: Path | str = "data",
    ) -> None:
        storage = LaboratoryStorage(data_dir)
        self._service = lab_service or VirtualLaboratoryService(
            default_registry(),
            default_controller_registry(),
            storage=storage,
        )
        self._storage = storage

    def create(
        self,
        *,
        name: str,
        controller_id: str,
        component_ids: list[str],
        description: str = "",
        metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        return self._service.create(
            name=name,
            controller_id=controller_id,
            component_ids=component_ids,
            description=description,
            metadata=metadata,
        )

    def start(self, laboratory_id: str) -> dict[str, Any]:
        return self._service.start(laboratory_id)

    def get(self, laboratory_id: str) -> dict[str, Any]:
        return self._service.labs.get(laboratory_id).to_dict()

    def get_simulation(self, laboratory_id: str) -> dict[str, Any]:
        return self._service.get_simulation_state(laboratory_id)

    def pause_simulation(self, laboratory_id: str) -> dict[str, Any]:
        return self._service.pause_simulation(laboratory_id)

    def stop_simulation(self, laboratory_id: str) -> dict[str, Any]:
        return self._service.stop_simulation(laboratory_id)

    def advance_simulation(self, laboratory_id: str, delta_ms: int = 100) -> dict[str, Any]:
        return self._service.advance_simulation(laboratory_id, delta_ms)

    def send_command(
        self, laboratory_id: str, instance_id: str, action: str, value: Any = None
    ) -> dict[str, Any]:
        return self._service.send_command(laboratory_id, instance_id, action, value)
