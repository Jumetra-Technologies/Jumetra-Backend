"""Virtual-to-physical pin mapping for hybrid experiments."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional


class PinMapper:
    """Create and validate virtual↔physical pin connections."""

    def __init__(self, *, storage_path: Optional[Path | str] = None) -> None:
        self._connections: dict[str, dict[str, Any]] = {}
        self._storage_path = Path(storage_path) if storage_path else None
        if self._storage_path and self._storage_path.exists():
            self._load()

    def list_connections(self) -> list[dict[str, Any]]:
        return list(self._connections.values())

    def get_connection(self, connection_id: str) -> Optional[dict[str, Any]]:
        return self._connections.get(connection_id)

    def create_connection(
        self,
        *,
        virtual_node_id: str,
        virtual_pin_id: str,
        physical_device_id: str,
        physical_pin_id: str,
        workspace_id: str = "",
    ) -> dict[str, Any]:
        issues = self.validate(
            virtual_pin_id=virtual_pin_id,
            physical_pin_id=physical_pin_id,
            virtual_interfaces=["digital", "gpio"],
            physical_interfaces=["gpio", "digital", "pwm"],
        )
        connection_id = f"HC{len(self._connections) + 1:04d}"
        record = {
            "connection_id": connection_id,
            "workspace_id": workspace_id,
            "virtual_node_id": virtual_node_id,
            "virtual_pin_id": virtual_pin_id,
            "physical_device_id": physical_device_id,
            "physical_pin_id": physical_pin_id,
            "valid": not issues,
            "issues": issues,
        }
        self._connections[connection_id] = record
        self._persist()
        return record

    def delete_connection(self, connection_id: str) -> bool:
        if connection_id not in self._connections:
            return False
        del self._connections[connection_id]
        self._persist()
        return True

    def connections_for_device(self, physical_device_id: str) -> list[dict[str, Any]]:
        return [
            c for c in self._connections.values() if c["physical_device_id"] == physical_device_id
        ]

    def connections_for_virtual(self, virtual_node_id: str) -> list[dict[str, Any]]:
        return [c for c in self._connections.values() if c["virtual_node_id"] == virtual_node_id]

    @staticmethod
    def validate(
        *,
        virtual_pin_id: str,
        physical_pin_id: str,
        virtual_interfaces: list[str],
        physical_interfaces: list[str],
    ) -> list[str]:
        issues: list[str] = []
        if not virtual_pin_id:
            issues.append("virtual pin is required")
        if not physical_pin_id:
            issues.append("physical pin is required")
        v_set = {i.lower() for i in virtual_interfaces}
        p_set = {i.lower() for i in physical_interfaces}
        if v_set and p_set and not (v_set & p_set):
            issues.append(
                f"incompatible interfaces: virtual={sorted(v_set)} physical={sorted(p_set)}"
            )
        return issues

    def _persist(self) -> None:
        if self._storage_path is None:
            return
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        with self._storage_path.open("w", encoding="utf-8") as fh:
            json.dump({"connections": list(self._connections.values())}, fh, indent=2)
            fh.write("\n")

    def _load(self) -> None:
        try:
            with self._storage_path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError):
            return
        for item in data.get("connections") or []:
            cid = str(item.get("connection_id") or "")
            if cid:
                self._connections[cid] = item
