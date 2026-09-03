"""API façade for interactive hybrid wiring (Sprint 30)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from engine.events.event_bus import EventBus
from engine.hybrid.wiring import AutoMapper, WireManager


class WorkspaceWiringService:
    """Dependency-injected wiring service for /workspace/connections."""

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
        pin_mapper = None
        router = None
        if hybrid_service is not None and hasattr(hybrid_service, "physical_layer"):
            layer = hybrid_service.physical_layer
            pin_mapper = getattr(layer, "pin_mapper", None)
            router = getattr(layer, "router", None)
        self.manager = WireManager(
            data_dir=self.data_dir,
            event_bus=event_bus,
            pin_mapper=pin_mapper,
            hybrid_router=router,
        )
        self.auto_mapper = AutoMapper(self.manager)

    def list_connections(self, workspace_id: str = "") -> dict[str, Any]:
        items = self.manager.list_connections(workspace_id)
        return {"connections": items, "count": len(items)}

    def get_connection(self, connection_id: str) -> dict[str, Any]:
        conn = self.manager.get_connection(connection_id)
        if conn is None:
            raise KeyError(f"connection not found: {connection_id}")
        return conn

    def create_connection(self, body: dict[str, Any]) -> dict[str, Any]:
        # Prefer auto-map path when flag set or source/dest meta present
        if body.get("auto") or body.get("drag"):
            result = self.auto_mapper.map_drag(
                source_device=str(body.get("source_device") or body.get("source") or ""),
                source_pin=str(body.get("source_pin") or body.get("source_handle") or ""),
                destination_device=str(
                    body.get("destination_device") or body.get("target") or ""
                ),
                destination_pin=str(
                    body.get("destination_pin") or body.get("target_handle") or ""
                ),
                source_meta=body.get("source_meta") or {
                    "device_kind": body.get("source_kind"),
                    "pin_type": body.get("source_pin_type") or body.get("source_type"),
                    "voltage": body.get("source_voltage", 3.3),
                    "supports_input": body.get("source_supports_input", True),
                    "supports_output": body.get("source_supports_output", True),
                    "available": body.get("source_available", True),
                },
                destination_meta=body.get("destination_meta") or {
                    "device_kind": body.get("destination_kind"),
                    "pin_type": body.get("destination_pin_type") or body.get("destination_type"),
                    "voltage": body.get("destination_voltage", 3.3),
                    "supports_input": body.get("destination_supports_input", True),
                    "supports_output": body.get("destination_supports_output", True),
                    "available": body.get("destination_available", True),
                },
                workspace_id=str(body.get("workspace_id") or ""),
                wire_type=str(body.get("wire_type") or body.get("protocol") or ""),
                transport=str(body.get("transport") or ""),
            )
            if not result.get("ok"):
                raise ValueError(
                    "; ".join((result.get("validation") or {}).get("errors") or ["invalid"])
                )
            return result["connection"]
        conn = self.manager.connect_from_dict(body)
        return conn.to_dict()

    def delete_connection(self, connection_id: str) -> dict[str, Any]:
        conn = self.manager.disconnect(connection_id)
        if conn is None:
            raise KeyError(f"connection not found: {connection_id}")
        return {"ok": True, "connection_id": connection_id, "connection": conn.to_dict()}

    def patch_connection(self, connection_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        return self.manager.update_connection(connection_id, patch).to_dict()

    def preview(self, body: dict[str, Any]) -> dict[str, Any]:
        return self.auto_mapper.preview(
            source_device=str(body.get("source_device") or body.get("source") or ""),
            source_pin=str(body.get("source_pin") or body.get("source_handle") or ""),
            destination_device=str(body.get("destination_device") or body.get("target") or ""),
            destination_pin=str(body.get("destination_pin") or body.get("target_handle") or ""),
            source_meta=body.get("source_meta"),
            destination_meta=body.get("destination_meta"),
            wire_type=str(body.get("wire_type") or ""),
        )

    def write_pin(self, body: dict[str, Any]) -> dict[str, Any]:
        return self.manager.write_pin(
            str(body.get("device_id") or ""),
            str(body.get("pin") or body.get("pin_id") or ""),
            body.get("value", 0),
            mode=str(body.get("mode") or ""),
            virtual_node_id=str(body.get("virtual_node_id") or ""),
        )

    def set_pin_mode(self, body: dict[str, Any]) -> dict[str, Any]:
        return self.manager.set_pin_mode(
            str(body.get("device_id") or ""),
            str(body.get("pin") or body.get("pin_id") or ""),
            str(body.get("mode") or "INPUT"),
        )

    def inspect_pin(self, device_id: str, pin: str) -> dict[str, Any]:
        return self.manager.get_pin_state(device_id, pin)

    def highlight(
        self,
        start_device: str,
        start_pin: str,
        end_device: str,
        end_pin: str,
    ) -> dict[str, Any]:
        return self.manager.highlight_path(start_device, start_pin, end_device, end_pin)

    def load_workspace(self, workspace_id: str) -> dict[str, Any]:
        return self.manager.load_workspace(workspace_id)

    def graph_stats(self) -> dict[str, Any]:
        return {
            "components": self.manager.find_connected_components(),
            "connection_count": len(self.manager.list_connections()),
        }
