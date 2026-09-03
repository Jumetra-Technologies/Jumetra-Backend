"""Physical / virtual / hybrid binding for component instances."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional


class BindingMode(str, Enum):
    VIRTUAL = "virtual"
    PHYSICAL = "physical"
    HYBRID = "hybrid"


@dataclass
class HardwareBinding:
    component_id: str
    instance_id: str = ""
    mode: str = BindingMode.VIRTUAL.value
    transport: str = ""
    device_id: str = ""
    port: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.instance_id:
            self.instance_id = self.component_id
        self.mode = str(self.mode).lower()

    def to_dict(self) -> dict[str, Any]:
        return {
            "component_id": self.component_id,
            "instance_id": self.instance_id,
            "mode": self.mode,
            "transport": self.transport,
            "device_id": self.device_id,
            "port": self.port,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HardwareBinding":
        return cls(
            component_id=str(data["component_id"]),
            instance_id=str(data.get("instance_id") or ""),
            mode=str(data.get("mode") or BindingMode.VIRTUAL.value),
            transport=str(data.get("transport") or ""),
            device_id=str(data.get("device_id") or ""),
            port=str(data.get("port") or ""),
            metadata=dict(data.get("metadata") or {}),
        )

    def bind_physical(self, *, device_id: str, transport: str = "serial", port: str = "") -> "HardwareBinding":
        self.mode = BindingMode.PHYSICAL.value
        self.device_id = device_id
        self.transport = transport
        self.port = port
        return self

    def bind_hybrid(self, *, device_id: str, transport: str = "serial") -> "HardwareBinding":
        self.mode = BindingMode.HYBRID.value
        self.device_id = device_id
        self.transport = transport
        return self

    def to_virtual(self) -> "HardwareBinding":
        self.mode = BindingMode.VIRTUAL.value
        self.device_id = ""
        self.transport = ""
        self.port = ""
        return self


class HardwareBindingStore:
    """In-memory bindings keyed by instance_id (wiring preserved across modes)."""

    def __init__(self) -> None:
        self._bindings: dict[str, HardwareBinding] = {}

    def upsert(self, binding: HardwareBinding) -> HardwareBinding:
        self._bindings[binding.instance_id] = binding
        return binding

    def get(self, instance_id: str) -> Optional[HardwareBinding]:
        return self._bindings.get(instance_id)

    def list_all(self) -> list[HardwareBinding]:
        return list(self._bindings.values())

    def switch_mode(self, instance_id: str, mode: str, **kwargs: Any) -> HardwareBinding:
        binding = self._bindings.get(instance_id)
        if binding is None:
            raise KeyError(f"binding not found: {instance_id}")
        mode_l = mode.lower()
        if mode_l == BindingMode.PHYSICAL.value:
            binding.bind_physical(
                device_id=str(kwargs.get("device_id") or binding.device_id),
                transport=str(kwargs.get("transport") or binding.transport or "serial"),
                port=str(kwargs.get("port") or binding.port),
            )
        elif mode_l == BindingMode.HYBRID.value:
            binding.bind_hybrid(
                device_id=str(kwargs.get("device_id") or binding.device_id),
                transport=str(kwargs.get("transport") or binding.transport or "serial"),
            )
        else:
            binding.to_virtual()
        return binding
