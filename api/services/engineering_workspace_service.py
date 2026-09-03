"""API wrapper for engineering laboratory workspace."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from engine.lab_workspace import LabWorkspaceService, LabWorkspaceStorage


class EngineeringWorkspaceService:
    def __init__(
        self,
        service: Optional[LabWorkspaceService] = None,
        data_dir: Path | str = "data",
    ) -> None:
        self._service = service or LabWorkspaceService(storage=LabWorkspaceStorage(data_dir))

    def catalog(
        self,
        q: str = "",
        category: str | None = None,
        *,
        interface: str | None = None,
        interfaces: list[str] | None = None,
        voltage: float | None = None,
        voltages: list[float] | None = None,
        controller_id: str | None = None,
    ) -> dict[str, Any]:
        return self._service.catalog(
            q=q,
            category=category,
            interface=interface,
            interfaces=interfaces,
            voltage=voltage,
            voltages=voltages,
            controller_id=controller_id,
        )

    def create(self, *, name: str, project_id: str = "") -> dict[str, Any]:
        return self._service.create(name=name, project_id=project_id)

    def list_workspaces(self) -> list[dict[str, Any]]:
        return self._service.list_workspaces()

    def get(self, workspace_id: str) -> dict[str, Any]:
        return self._service.get(workspace_id)

    def get_state(self, workspace_id: str) -> dict[str, Any]:
        return self._service.get_state(workspace_id)

    def connect(self, workspace_id: str) -> dict[str, Any]:
        return self._service.connect(workspace_id)

    def disconnect(self, workspace_id: str) -> dict[str, Any]:
        return self._service.disconnect(workspace_id)

    def run(self, workspace_id: str, speed: str = "1x") -> dict[str, Any]:
        return self._service.run(workspace_id, speed=speed)

    def pause(self, workspace_id: str) -> dict[str, Any]:
        return self._service.pause(workspace_id)

    def reset(self, workspace_id: str) -> dict[str, Any]:
        return self._service.reset(workspace_id)

    def step(self, workspace_id: str, delta_ms: int = 100) -> dict[str, Any]:
        return self._service.step(workspace_id, delta_ms)

    def add_node(self, workspace_id: str, **kwargs: Any) -> dict[str, Any]:
        return self._service.add_node(workspace_id, **kwargs)

    def update_node(self, workspace_id: str, node_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        return self._service.update_node(workspace_id, node_id, patch)

    def delete_nodes(self, workspace_id: str, node_ids: list[str]) -> dict[str, Any]:
        return self._service.delete_nodes(workspace_id, node_ids)

    def duplicate_nodes(self, workspace_id: str, node_ids: list[str]) -> list[dict[str, Any]]:
        return self._service.duplicate_nodes(workspace_id, node_ids)

    def add_wire(self, workspace_id: str, **kwargs: Any) -> dict[str, Any]:
        return self._service.add_wire(workspace_id, **kwargs)

    def delete_wires(self, workspace_id: str, wire_ids: list[str]) -> dict[str, Any]:
        return self._service.delete_wires(workspace_id, wire_ids)

    def undo(self, workspace_id: str) -> dict[str, Any]:
        return self._service.undo(workspace_id)

    def redo(self, workspace_id: str) -> dict[str, Any]:
        return self._service.redo(workspace_id)

    def send_serial(self, workspace_id: str, line: str) -> dict[str, Any]:
        return self._service.send_serial(workspace_id, line)
