"""Component Engine v2 API service."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from engine.components.v2 import (
    BehaviorRegistry,
    ComponentRegistryV2,
    HardwareBinding,
    HardwareBindingStore,
    RendererRegistry,
    default_behavior_registry,
    default_registry_v2,
    publish_component_signal,
)
from engine.events.event_bus import EventBus


class ComponentEngineV2Service:
    def __init__(
        self,
        registry: Optional[ComponentRegistryV2] = None,
        *,
        event_bus: Optional[EventBus] = None,
    ) -> None:
        self.registry = registry or default_registry_v2()
        self.renderers = RendererRegistry(self.registry)
        self.behaviors = default_behavior_registry
        self.bindings = HardwareBindingStore()
        self.event_bus = event_bus or EventBus()
        self._runtime: dict[str, Any] = {}

    def search(self, q: str = "", *, category: str | None = None, interface: str | None = None, limit: int = 50) -> dict[str, Any]:
        results = self.registry.search(q, category=category, interface=interface, limit=limit)
        return {"results": results, "total": len(results)}

    def get(self, component_id: str) -> dict[str, Any]:
        comp = self.registry.require(component_id)
        data = comp.to_dict()
        data["datasheet"] = comp.datasheet_md
        data["renderer_svg"] = comp.renderer_svg
        return data

    def list_packages(self) -> list[dict[str, Any]]:
        return [c.to_search_hit() for c in self.registry.list_all()]

    def get_renderer_svg(self, component_id: str) -> str:
        svg = self.renderers.get_svg(component_id)
        if svg is None:
            raise KeyError(f"renderer not found: {component_id}")
        return svg

    def debug(self) -> dict[str, Any]:
        return {
            "total_packages": len(self.registry.list_all()),
            "categories": self.registry.categories(),
            "renderers": self.renderers.list_renderers(),
            "behaviors": self.behaviors.known()[:20],
            "packages_dir": str(self.registry.packages_dir),
            "sample": [c.id for c in self.registry.list_all()[:8]],
        }

    def create_binding(self, body: dict[str, Any]) -> dict[str, Any]:
        binding = HardwareBinding.from_dict(body)
        self.bindings.upsert(binding)
        return binding.to_dict()

    def switch_binding(self, instance_id: str, mode: str, **kwargs: Any) -> dict[str, Any]:
        return self.bindings.switch_mode(instance_id, mode, **kwargs).to_dict()

    def simulate_tick(self, component_id: str, *, instance_id: str = "", t_s: float = 0.0, inputs: dict | None = None) -> dict[str, Any]:
        comp = self.registry.require(component_id)
        behavior = self.behaviors.create(
            comp.simulation.behavior or comp.id,
            component_id=component_id,
            instance_id=instance_id or component_id,
        )
        signal = behavior.tick(t_s, inputs)
        publish_component_signal(
            self.event_bus,
            component_id=component_id,
            instance_id=instance_id or component_id,
            signal=signal,
        )
        return {"component_id": component_id, "instance_id": instance_id or component_id, "signal": signal}
