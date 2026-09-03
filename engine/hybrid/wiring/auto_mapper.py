"""Auto-map drag-drop pin pairs into live PinConnections."""

from __future__ import annotations

from typing import Any, Optional

from .pin_connection import PinConnection, PinEndpoint
from .pin_validator import PinValidator
from .wire_manager import WireManager


class AutoMapper:
    """
    When user drags ESP32 GPIO2 → Virtual LED IN:
    create mapping + publish PIN_CONNECTED — no manual API calls from UI beyond drop.
    """

    def __init__(
        self,
        manager: WireManager,
        *,
        validator: Optional[PinValidator] = None,
    ) -> None:
        self.manager = manager
        self.validator = validator or PinValidator()

    def map_drag(
        self,
        *,
        source_device: str,
        source_pin: str,
        destination_device: str,
        destination_pin: str,
        source_meta: Optional[dict[str, Any]] = None,
        destination_meta: Optional[dict[str, Any]] = None,
        workspace_id: str = "",
        wire_type: str = "",
        transport: str = "",
    ) -> dict[str, Any]:
        src = self._endpoint(source_device, source_pin, source_meta or {})
        dst = self._endpoint(destination_device, destination_pin, destination_meta or {})
        preview = self.validator.validate(src, dst, requested_wire_type=wire_type)
        if not preview.ok:
            return {
                "ok": False,
                "connected": False,
                "validation": preview.to_dict(),
                "connection": None,
            }
        conn = self.manager.connect(
            source=src,
            destination=dst,
            wire_type=preview.wire_type,
            workspace_id=workspace_id,
            transport=transport,
            auto=True,
        )
        return {
            "ok": conn.valid,
            "connected": True,
            "validation": preview.to_dict(),
            "connection": conn.to_dict(),
        }

    def preview(
        self,
        *,
        source_device: str,
        source_pin: str,
        destination_device: str,
        destination_pin: str,
        source_meta: Optional[dict[str, Any]] = None,
        destination_meta: Optional[dict[str, Any]] = None,
        wire_type: str = "",
    ) -> dict[str, Any]:
        src = self._endpoint(source_device, source_pin, source_meta or {})
        dst = self._endpoint(destination_device, destination_pin, destination_meta or {})
        return self.validator.validate(src, dst, requested_wire_type=wire_type).to_dict()

    @staticmethod
    def _endpoint(device_id: str, pin: str, meta: dict[str, Any]) -> PinEndpoint:
        return PinEndpoint(
            device_id=device_id,
            pin=pin,
            device_kind=str(meta.get("device_kind") or meta.get("kind") or "unknown"),
            pin_type=str(meta.get("pin_type") or meta.get("type") or "GPIO").upper(),
            mode=str(meta.get("mode") or "UNKNOWN"),
            voltage=float(meta.get("voltage") or 3.3),
            supports_input=bool(meta.get("supports_input", True)),
            supports_output=bool(meta.get("supports_output", True)),
            available=bool(meta.get("available", True)),
        )
