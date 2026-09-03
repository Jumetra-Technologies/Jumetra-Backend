"""Unified Device abstract base for physical, virtual, and simulated devices."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Mapping, Optional, TYPE_CHECKING

from .capabilities import Capability, capabilities_for, capability_values

if TYPE_CHECKING:
    from ...events.event import Event


def _now_ms() -> int:
    return int(time.time() * 1000)


class DeviceMode(Enum):
    """How a device is realized in HHIP."""

    PHYSICAL = "PHYSICAL"
    VIRTUAL = "VIRTUAL"
    SIMULATED = "SIMULATED"

    def to_registry(self) -> str:
        """Map to Phase 1.3 registry string values (lowercase)."""
        return self.value.lower()

    @classmethod
    def from_registry(cls, value: str) -> "DeviceMode":
        return cls(str(value).upper())


class DeviceStatus(Enum):
    """Lifecycle status shared by all Device implementations."""

    UNKNOWN = "UNKNOWN"
    INITIALIZING = "INITIALIZING"
    READY = "READY"
    BUSY = "BUSY"
    ERROR = "ERROR"
    OFFLINE = "OFFLINE"


class Device(ABC):
    """Abstract device — the commercial-scale common interface.

    Properties:
        device_id, device_name, device_type, device_mode, manufacturer,
        model, firmware_version, capabilities, status, metadata
    """

    def __init__(
        self,
        device_id: str,
        device_type: str,
        device_mode: DeviceMode,
        *,
        device_name: Optional[str] = None,
        manufacturer: Optional[str] = None,
        model: Optional[str] = None,
        firmware_version: Optional[str] = None,
        capabilities: Optional[set[Capability] | frozenset[Capability]] = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> None:
        self.device_id = device_id
        self.device_type = device_type
        self.device_mode = device_mode
        self.device_name = device_name or device_id
        self.manufacturer = manufacturer
        self.model = model
        self.firmware_version = firmware_version
        self._capabilities: frozenset[Capability] = (
            frozenset(capabilities)
            if capabilities is not None
            else capabilities_for(device_type)
        )
        self._status = DeviceStatus.UNKNOWN
        self.metadata: dict[str, Any] = dict(metadata) if metadata else {}
        self._init_clock_metadata()
        self.created_at: int = _now_ms()
        self.updated_at: int = self.created_at
        self._initialized = False

    def _init_clock_metadata(self) -> None:
        """Ensure clock measurement fields exist (observations only — no correction)."""
        clock_type = {
            DeviceMode.PHYSICAL: "device",
            DeviceMode.VIRTUAL: "system",
            DeviceMode.SIMULATED: "simulation",
        }.get(self.device_mode, "system")
        self.metadata.setdefault("clock_id", f"clock_{self.device_id}")
        self.metadata.setdefault("clock_type", clock_type)
        # Sprint 7 aliases
        self.metadata.setdefault("clock_offset", 0)
        self.metadata.setdefault("clock_drift", 0.0)
        self.metadata.setdefault("last_sync_time", None)
        # Sprint 8 observation fields
        self.metadata.setdefault("clock_offset_estimate", 0.0)
        self.metadata.setdefault("clock_drift_estimate", 0.0)
        self.metadata.setdefault("last_sync_measurement", None)

    # --- properties ----------------------------------------------------

    @property
    def status(self) -> DeviceStatus:
        return self._status

    @property
    def capabilities(self) -> frozenset[Capability]:
        return self._capabilities

    def get_capabilities(self) -> list[str]:
        """Return capability names as a sorted list of strings."""
        return capability_values(self._capabilities)

    def has_capability(self, capability: Capability | str) -> bool:
        """Return True if this device advertises ``capability``."""
        if isinstance(capability, str):
            try:
                capability = Capability(capability)
            except ValueError:
                return False
        return capability in self._capabilities

    def get_metadata(self) -> dict[str, Any]:
        """Return a copy of device metadata."""
        return dict(self.metadata)

    # --- lifecycle -----------------------------------------------------

    def initialize(self) -> None:
        """Bring the device to READY."""
        self._status = DeviceStatus.INITIALIZING
        self.updated_at = _now_ms()
        self._on_initialize()
        self._status = DeviceStatus.READY
        self._initialized = True
        self.updated_at = _now_ms()

    def shutdown(self) -> None:
        """Move the device to OFFLINE."""
        self._on_shutdown()
        self._status = DeviceStatus.OFFLINE
        self._initialized = False
        self.updated_at = _now_ms()

    def _on_initialize(self) -> None:
        """Subclass hook."""

    def _on_shutdown(self) -> None:
        """Subclass hook."""

    def set_status(self, status: DeviceStatus) -> DeviceStatus:
        """Update lifecycle status; returns previous status."""
        previous = self._status
        self._status = status
        self.updated_at = _now_ms()
        return previous

    def handle_event(self, event: "Event") -> None:
        """Handle an Event addressed to this device (default: ignore)."""
        if event.target and event.target != self.device_id:
            return

    def health_check(self) -> dict[str, Any]:
        """Return a health snapshot (alias-friendly name for commercial API)."""
        return self.health()

    def health(self) -> dict[str, Any]:
        """Return a lightweight health snapshot."""
        return {
            "device_id": self.device_id,
            "device_type": self.device_type,
            "device_mode": self.device_mode.value,
            "status": self._status.value,
            "healthy": self._status in (DeviceStatus.READY, DeviceStatus.BUSY),
            "initialized": self._initialized,
            "capabilities": self.get_capabilities(),
            "updated_at": self.updated_at,
        }

    def serialize(self) -> dict[str, Any]:
        """Serialize identity and status to a JSON-compatible dict."""
        return {
            "device_id": self.device_id,
            "device_name": self.device_name,
            "device_type": self.device_type,
            "device_mode": self.device_mode.value,
            "manufacturer": self.manufacturer,
            "model": self.model,
            "firmware_version": self.firmware_version,
            "capabilities": self.get_capabilities(),
            "status": self._status.value,
            "metadata": self.get_metadata(),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def deserialize(self, data: Mapping[str, Any]) -> None:
        """Restore mutable fields from a serialized dict."""
        if "device_name" in data and data["device_name"] is not None:
            self.device_name = str(data["device_name"])
        if "manufacturer" in data:
            self.manufacturer = data["manufacturer"]
        if "model" in data:
            self.model = data["model"]
        if "firmware_version" in data:
            self.firmware_version = data["firmware_version"]
        if "metadata" in data and isinstance(data["metadata"], Mapping):
            self.metadata = dict(data["metadata"])
        if "status" in data and data["status"] is not None:
            self._status = DeviceStatus(str(data["status"]))
        if "updated_at" in data and data["updated_at"] is not None:
            self.updated_at = int(data["updated_at"])
        if "created_at" in data and data["created_at"] is not None:
            self.created_at = int(data["created_at"])
        if "capabilities" in data and data["capabilities"] is not None:
            caps: set[Capability] = set()
            for item in data["capabilities"]:
                try:
                    caps.add(Capability(str(item)))
                except ValueError:
                    continue
            self._capabilities = frozenset(caps)
