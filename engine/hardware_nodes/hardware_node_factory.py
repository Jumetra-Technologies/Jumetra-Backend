"""Factory: HybridHardwareDevice / PhysicalDevice → HardwareNode."""

from __future__ import annotations

import time
from typing import Any, Mapping, Optional, Union

from .board_renderer import get_pin_layout
from .hardware_node import HardwareNode, HardwareNodeStatus
from .pin_layout import HardwarePinDef


class HardwareNodeFactory:
    """Convert hybrid / discovery device payloads into workspace HardwareNodes."""

    def __init__(self, *, default_workspace_id: str = "") -> None:
        self.default_workspace_id = default_workspace_id
        self._next_slot = 0

    def from_hybrid_device(
        self,
        device: Union[Mapping[str, Any], Any],
        *,
        workspace_id: str = "",
        position: Optional[dict[str, float]] = None,
    ) -> HardwareNode:
        data = device if isinstance(device, Mapping) else _to_mapping(device)
        board_type = str(data.get("board_type") or "unknown")
        device_id = str(data.get("device_id") or data.get("port") or f"device_{int(time.time())}")

        layout_pins = {p.name: p for p in get_pin_layout(board_type)}
        # Overlay discovery-reported pins when present
        for raw in data.get("pins") or []:
            if not isinstance(raw, dict):
                continue
            name = str(raw.get("pin_id") or raw.get("name") or "")
            if not name:
                continue
            if name in layout_pins:
                # keep layout geometry; refresh type hints from discovery if richer
                continue
            layout_pins[name] = HardwarePinDef.from_dict(
                {
                    **raw,
                    "name": name,
                    "type": str(raw.get("type") or (raw.get("interfaces") or ["GPIO"])[0]).upper(),
                    "x": 0.5,
                    "y": 0.5,
                    "side": "right",
                }
            )

        caps = data.get("capabilities") or []
        if caps and isinstance(caps[0], dict):
            caps = [c.get("name", c) for c in caps]

        pos = position or self._auto_position()
        node = HardwareNode(
            device_id=device_id,
            board_type=board_type,
            manufacturer=str(data.get("manufacturer") or data.get("vendor") or ""),
            transport=str(data.get("transport") or data.get("communication_method") or "serial"),
            firmware_version=str(data.get("firmware_version") or ""),
            pins=layout_pins,
            capabilities=[str(c) for c in caps],
            status=HardwareNodeStatus.ONLINE if data.get("connected", True) else HardwareNodeStatus.WAITING,
            heartbeat_ms=int(time.time() * 1000),
            position=pos,
            workspace_id=workspace_id or self.default_workspace_id,
            label=str(data.get("label") or data.get("model") or board_type),
            model=str(data.get("model") or data.get("label") or board_type),
            category=str(data.get("category") or "microcontroller"),
            endpoint=str(data.get("endpoint") or data.get("port") or ""),
            available=bool(data.get("connected", True)),
            health="ok" if data.get("connected", True) else "waiting",
            metadata={
                "profile_id": data.get("profile_id"),
                "serial_number": (data.get("metadata") or {}).get("serial_number")
                if isinstance(data.get("metadata"), dict)
                else None,
            },
        )
        return node

    def from_waiting(
        self,
        *,
        device_id: str,
        board_type: str,
        workspace_id: str = "",
        endpoint: str = "",
        transport: str = "serial",
        manufacturer: str = "",
        position: Optional[dict[str, float]] = None,
    ) -> HardwareNode:
        pins = {p.name: p for p in get_pin_layout(board_type)}
        return HardwareNode(
            device_id=device_id,
            board_type=board_type,
            manufacturer=manufacturer,
            transport=transport,
            pins=pins,
            status=HardwareNodeStatus.WAITING,
            position=position or self._auto_position(),
            workspace_id=workspace_id or self.default_workspace_id,
            endpoint=endpoint,
            available=False,
            health="waiting",
            label=f"{board_type} (waiting)",
        )

    def _auto_position(self) -> dict[str, float]:
        slot = self._next_slot
        self._next_slot += 1
        col = slot % 4
        row = slot // 4
        return {"x": 80.0 + col * 320.0, "y": 80.0 + row * 220.0}


def _to_mapping(device: Any) -> dict[str, Any]:
    if hasattr(device, "to_dict"):
        return dict(device.to_dict())
    return {
        "device_id": getattr(device, "device_id", ""),
        "board_type": getattr(device, "board_type", "unknown"),
        "manufacturer": getattr(device, "manufacturer", "") or getattr(device, "vendor", ""),
        "transport": getattr(device, "transport", "serial"),
        "firmware_version": getattr(device, "firmware_version", ""),
        "capabilities": getattr(device, "capabilities", []),
        "pins": [],
        "connected": getattr(device, "connected", True),
        "port": getattr(device, "port", "") or getattr(device, "endpoint", ""),
        "endpoint": getattr(device, "endpoint", "") or getattr(device, "port", ""),
        "label": getattr(device, "label", ""),
        "model": getattr(device, "model", ""),
        "category": getattr(device, "category", "microcontroller"),
    }
