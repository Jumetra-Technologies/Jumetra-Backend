"""API façade for live hybrid workspace hardware nodes."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from engine.events.event_bus import EventBus
from engine.hardware_nodes import (
    BoardRenderer,
    DiscoveryListener,
    HardwareNodeFactory,
    WorkspaceSyncService,
)


class WorkspaceHardwareService:
    """Dependency-injected service for /workspace/hardware routes."""

    def __init__(
        self,
        data_dir: Path | str,
        *,
        event_bus: Optional[EventBus] = None,
        hybrid_service: Any = None,
    ) -> None:
        self.data_dir = Path(data_dir)
        self.event_bus = event_bus
        self.hybrid_service = hybrid_service
        self.factory = HardwareNodeFactory()
        self.sync = WorkspaceSyncService(
            data_dir=self.data_dir,
            factory=self.factory,
            event_bus=event_bus,
        )
        self.listener = DiscoveryListener(
            self.sync,
            event_bus=event_bus,
        )

    def list_hardware(self, workspace_id: str = "") -> dict[str, Any]:
        nodes = self.sync.list_nodes(workspace_id)
        return {"hardware": nodes, "count": len(nodes)}

    def get_hardware(self, device_id: str) -> dict[str, Any]:
        node = self.sync.get_node(device_id)
        if node is None:
            raise KeyError(f"hardware node not found: {device_id}")
        board_type = str(node.get("board_type") or "")
        return {
            **node,
            "render": BoardRenderer.render_spec(board_type),
            "inspector": self._inspector(node),
        }

    def reconnect(self, device_id: str = "", project_id: str = "") -> dict[str, Any]:
        hybrid = []
        if self.hybrid_service is not None:
            try:
                hybrid = self.hybrid_service.list_physical_devices()
            except Exception:  # noqa: BLE001
                hybrid = []
        if project_id:
            return self.sync.load_project(project_id, hybrid_devices=hybrid)
        return self.sync.reconnect(device_id, hybrid_devices=hybrid)

    def disconnect(self, device_id: str) -> dict[str, Any]:
        return self.sync.disconnect_node(device_id)

    def events(self, limit: int = 100) -> dict[str, Any]:
        ev = self.sync.events(limit=limit)
        return {"events": ev, "count": len(ev)}

    def update_layout(
        self,
        device_id: str,
        *,
        position: Optional[dict[str, float]] = None,
        rotation: Optional[float] = None,
        collapsed: Optional[bool] = None,
    ) -> dict[str, Any]:
        node = self.sync.update_layout(
            device_id,
            position=position,
            rotation=rotation,
            collapsed=collapsed,
        )
        if node is None:
            raise KeyError(f"hardware node not found: {device_id}")
        return node

    def _inspector(self, node: dict[str, Any]) -> dict[str, Any]:
        meta = node.get("metadata") or {}
        return {
            "manufacturer": node.get("manufacturer") or "",
            "chip": node.get("board_type") or "",
            "firmware": node.get("firmware_version") or "",
            "transport": node.get("transport") or "",
            "com_port": node.get("endpoint") or node.get("port") or "",
            "ip_address": meta.get("ip_address") or "",
            "capabilities": node.get("capabilities") or [],
            "memory": meta.get("memory") or "",
            "voltage": meta.get("voltage") or 3.3,
            "temperature": meta.get("temperature"),
            "heartbeat": node.get("heartbeat_ms") or node.get("heartbeat"),
            "serial_number": meta.get("serial_number") or "",
            "last_sync": node.get("last_sync_ms"),
            "health": node.get("health") or "unknown",
            "status": node.get("status"),
            "waiting_message": "Waiting for hardware" if node.get("status") == "waiting" else None,
        }
