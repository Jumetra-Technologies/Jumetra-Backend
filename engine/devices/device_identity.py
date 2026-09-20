"""Unvalidated self-description a device claims on the wire.

Sprint 36 service-layer only — not a store.

Why this file exists despite ``PhysicalDevice`` already having
``device_id`` / ``board_type`` / ``firmware_version`` / ``capabilities`` /
``connection_state``:

- ``engine.hybrid.physical_device.PhysicalDevice`` is a *registered*
  hybrid device. ``from_discovery()`` pulls board profiles and requires
  a ``port``. That is post-trust / post-registration.
- ``engine.devices.base.physical_device.PhysicalDevice`` uses
  ``device_type`` (not ``board_type``) and is the DeviceManager
  abstraction, also after registration.

This type is the raw HELLO / DEVICE_DISCOVERY claim extracted *before*
``DeviceManager.register_physical_from_hello`` or a HardwareNode upsert.
It has zero dependency on the hybrid package and holds no
device_id → identity dict. Callers that need a device object still use
``PhysicalDevice`` / ``DeviceManager``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence

from engine.protocol.messages import MessageType


def _as_str_tuple(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return tuple(part.strip() for part in value.split(",") if part.strip())
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return tuple(str(item) for item in value)
    return ()


@dataclass(frozen=True)
class DeviceIdentityClaim:
    """Wire claim only. Do not persist or index instances of this class."""

    device_id: str
    board_type: str
    firmware_version: str = ""
    capabilities: tuple[str, ...] = ()
    connection_state: str = "connecting"

    def to_discovery_payload(self, *, endpoint: str = "") -> dict[str, Any]:
        """Shape ``DiscoveryListener`` / ``WorkspaceSyncService.upsert_from_device`` accept."""
        payload: dict[str, Any] = {
            "device_id": self.device_id,
            "board_type": self.board_type,
            "firmware_version": self.firmware_version,
            "capabilities": list(self.capabilities),
            "connection_state": self.connection_state,
            "connected": True,
            "transport": "serial",
        }
        if endpoint:
            payload["port"] = endpoint
            payload["endpoint"] = endpoint
        return payload

    @classmethod
    def from_message(cls, message: Mapping[str, Any]) -> Optional["DeviceIdentityClaim"]:
        """Parse a HELLO or EVENT/DEVICE_DISCOVERY envelope. None if not a claim."""
        if not isinstance(message, Mapping):
            return None
        payload = message.get("payload") or {}
        if not isinstance(payload, dict):
            payload = {}
        msg_type = str(message.get("type") or "")
        event_name = str(payload.get("event") or "")

        is_hello = msg_type == MessageType.HELLO
        is_discovery = msg_type == MessageType.EVENT and event_name == "DEVICE_DISCOVERY"
        if not is_hello and not is_discovery:
            return None

        device_id = str(
            payload.get("device_id") or message.get("source") or ""
        ).strip()
        board_type = str(
            payload.get("board_type") or payload.get("device_type") or ""
        ).strip()
        if not device_id or not board_type:
            return None

        return cls(
            device_id=device_id,
            board_type=board_type,
            firmware_version=str(payload.get("firmware_version") or ""),
            capabilities=_as_str_tuple(payload.get("capabilities")),
            connection_state="connecting",
        )
