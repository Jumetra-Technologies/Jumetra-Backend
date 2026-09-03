"""Data models for hardware discovery."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class DiscoveryStatus(str, Enum):
    CONNECTING = "connecting"
    CONNECTED = "connected"
    BUSY = "busy"
    DISCONNECTED = "disconnected"
    ERROR = "error"


@dataclass
class DiscoveredDevice:
    """A USB serial device seen by the discovery scanner."""

    port: str
    status: DiscoveryStatus
    board_type: str
    label: str
    vid: Optional[int] = None
    pid: Optional[int] = None
    manufacturer: Optional[str] = None
    description: Optional[str] = None
    serial_number: Optional[str] = None
    device_id: Optional[str] = None
    firmware_version: Optional[str] = None
    capabilities: list[str] = field(default_factory=list)
    hhip_firmware: bool = False
    last_seen_ms: int = 0
    error: Optional[str] = None
    baudrate: int = 115200

    def to_dict(self) -> dict[str, Any]:
        return {
            "port": self.port,
            "status": self.status.value,
            "board_type": self.board_type,
            "label": self.label,
            "vid": self.vid,
            "pid": self.pid,
            "manufacturer": self.manufacturer,
            "description": self.description,
            "serial_number": self.serial_number,
            "device_id": self.device_id,
            "firmware_version": self.firmware_version,
            "capabilities": list(self.capabilities),
            "hhip_firmware": self.hhip_firmware,
            "last_seen_ms": self.last_seen_ms,
            "error": self.error,
            "baudrate": self.baudrate,
        }

    @classmethod
    def from_port_info(
        cls,
        port: str,
        *,
        vid: Optional[int],
        pid: Optional[int],
        manufacturer: Optional[str],
        description: Optional[str],
        serial_number: Optional[str],
        board_type: str,
        label: str,
        last_seen_ms: int,
    ) -> "DiscoveredDevice":
        return cls(
            port=port,
            status=DiscoveryStatus.CONNECTING,
            board_type=board_type,
            label=label,
            vid=vid,
            pid=pid,
            manufacturer=manufacturer,
            description=description,
            serial_number=serial_number,
            last_seen_ms=last_seen_ms,
        )
