"""Hybrid hardware bridge — unified device abstraction."""

from __future__ import annotations

from typing import Any, Optional, TYPE_CHECKING

from engine.devices.base.device import Device, DeviceMode

from .modes import HybridDeviceMode

if TYPE_CHECKING:
    from .adapters.base import DeviceAdapter


class HybridDevice:
    """Unified device view for physical, virtual, simulated, and hybrid nodes."""

    def __init__(
        self,
        device_id: str,
        *,
        mode: HybridDeviceMode,
        device_type: str = "generic",
        name: str = "",
        adapter: Optional["DeviceAdapter"] = None,
        underlying: Optional[Device] = None,
        component_id: str = "",
        instance_id: str = "",
        available: bool = True,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        self.device_id = device_id
        self.mode = mode
        self.device_type = device_type
        self.name = name or device_id
        self.adapter = adapter
        self.underlying = underlying
        self.component_id = component_id
        self.instance_id = instance_id
        self.available = available
        self.metadata: dict[str, Any] = dict(metadata or {})

    @classmethod
    def from_physical(cls, device: Device, adapter: "DeviceAdapter") -> "HybridDevice":
        return cls(
            device_id=device.device_id,
            mode=HybridDeviceMode.PHYSICAL,
            device_type=device.device_type,
            name=device.device_name,
            adapter=adapter,
            underlying=device,
            available=device.status.value in {"READY", "BUSY"},
            metadata=device.get_metadata(),
        )

    @classmethod
    def from_virtual(
        cls,
        *,
        device_id: str,
        component_id: str,
        instance_id: str,
        adapter: "DeviceAdapter",
        name: str = "",
    ) -> "HybridDevice":
        return cls(
            device_id=device_id,
            mode=HybridDeviceMode.VIRTUAL,
            device_type="virtual_component",
            name=name or component_id,
            adapter=adapter,
            component_id=component_id,
            instance_id=instance_id,
            available=True,
        )

    @classmethod
    def from_simulated(cls, device_id: str, adapter: "DeviceAdapter", *, name: str = "") -> "HybridDevice":
        return cls(
            device_id=device_id,
            mode=HybridDeviceMode.SIMULATED,
            device_type="simulator",
            name=name or device_id,
            adapter=adapter,
            available=True,
        )

    @classmethod
    def from_hybrid_binding(
        cls,
        binding_id: str,
        *,
        physical: Optional[HybridDevice] = None,
        virtual: Optional[HybridDevice] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> "HybridDevice":
        return cls(
            device_id=binding_id,
            mode=HybridDeviceMode.HYBRID,
            device_type="hybrid_binding",
            name=binding_id,
            available=(physical.available if physical else False) or (virtual.available if virtual else False),
            metadata={
                "physical_id": physical.device_id if physical else None,
                "virtual_id": virtual.device_id if virtual else None,
                **(metadata or {}),
            },
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "device_id": self.device_id,
            "mode": self.mode.value,
            "device_type": self.device_type,
            "name": self.name,
            "component_id": self.component_id,
            "instance_id": self.instance_id,
            "available": self.available,
            "adapter": self.adapter.name if self.adapter else None,
            "metadata": dict(self.metadata),
        }


def map_legacy_mode(mode: DeviceMode) -> HybridDeviceMode:
    return HybridDeviceMode(mode.value.lower())
