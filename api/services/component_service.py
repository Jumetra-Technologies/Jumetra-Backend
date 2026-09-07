"""Component and controller API service."""

from __future__ import annotations

from typing import Any, Optional

from engine.components import ComponentRegistry, ComponentSearch, ComponentSearchIndex, default_registry
from engine.components.paths import resolve_components_dir
from engine.components.search import ComponentIndex
from engine.controllers import CompatibilityEngine, ControllerRegistry, default_controller_registry

# Explorer UI category → registry category
_UI_CATEGORY_MAP = {
    "sensors": "sensor",
    "sensor": "sensor",
    "actuators": "actuator",
    "actuator": "actuator",
    "displays": "display",
    "display": "display",
    "communication": "communication",
    "mcu": "mcu",
    "power": "power",
}


class ComponentService:
    """Expose component catalog, search, and compatibility to the API."""

    def __init__(
        self,
        component_registry: Optional[ComponentRegistry] = None,
        controller_registry: Optional[ControllerRegistry] = None,
    ) -> None:
        self.registry = component_registry or default_registry()
        self.controllers = controller_registry or default_controller_registry()
        self.search_engine = ComponentSearch(self.registry)
        self.compatibility = CompatibilityEngine()
        self.index = ComponentIndex(self.registry.components_dir)
        self.intelligence_index = ComponentSearchIndex(self.registry)

    def search(
        self,
        query: str = "",
        *,
        category: Optional[str] = None,
        interface: Optional[str] = None,
        controller_id: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        mapped_category = _UI_CATEGORY_MAP.get((category or "").lower(), category)
        results = self.search_engine.search(
            query, category=mapped_category, interface=interface, limit=limit
        )
        output: list[dict[str, Any]] = []
        for result in results:
            compatible = self.compatibility.compatible_controllers(
                result.component, self.controllers
            )
            compatible_ids = [c.controller_id for c in compatible]
            if controller_id:
                # Prefer explicit JSON compatible_controllers, then CompatibilityEngine
                doc = self.index.get(result.component.component_id) or {}
                declared = [str(c).lower() for c in (doc.get("compatible_controllers") or [])]
                cid = controller_id.lower()
                engine_match = next((c for c in compatible if c.controller_id == controller_id), None)
                if engine_match is None and cid not in declared and not any(cid in d for d in declared):
                    # MCU boards match themselves
                    if cid not in result.component.component_id.lower():
                        continue
            item = result.to_dict()
            item["version"] = result.component.version
            item["manufacturer"] = result.component.manufacturer
            item["tags"] = list(result.component.tags)
            item["compatible_controllers"] = compatible_ids or [
                str(c) for c in ((self.index.get(result.component.component_id) or {}).get("compatible_controllers") or [])
            ]
            # Enrich for ComponentExplorerPro (pins / aliases / keywords)
            doc = self.index.get(result.component.component_id)
            if doc:
                explorer = self.index.to_explorer_item(doc)
                item["pins"] = explorer.get("pins") or []
                item["keywords"] = explorer.get("keywords") or []
                item["aliases"] = explorer.get("aliases") or []
                item["voltage"] = explorer.get("voltage") or {}
                item["catalog_category"] = explorer.get("catalog_category")
                item["interfaces"] = explorer.get("interfaces") or result.component.interfaces
                # Flat fields for explorer convenience
                item["component_id"] = result.component.component_id
                item["name"] = result.component.name
                item["category"] = explorer.get("category") or result.component.category
                item["voltage_v"] = result.component.voltage_v
                simulation = explorer.get("simulation") or {}
                item["simulation_support"] = bool(simulation.get("supported", False))
                item["renderer"] = simulation.get("renderer", "")
                item["firmware_support"] = list((doc.get("firmware") or {}).get("supported_frameworks", []))
            else:
                item["component_id"] = result.component.component_id
                item["name"] = result.component.name
                item["category"] = result.component.category
                item["voltage_v"] = result.component.voltage_v
                item["interfaces"] = result.component.interfaces
                item["pins"] = []
                item["simulation_support"] = False
                item["renderer"] = ""
                item["firmware_support"] = []
            output.append(item)
        return output

    def get_component(self, component_id: str) -> dict[str, Any]:
        component = self.registry.require(component_id)
        compatible = self.compatibility.compatible_controllers(component, self.controllers)
        result = {
            "component": component.to_dict(),
            "compatibility": [c.to_dict() for c in compatible],
        }
        document = self.index.get(component.component_id) or {}
        simulation = document.get("simulation") or {}
        result["version"] = component.version
        result["manufacturer"] = component.manufacturer
        result["tags"] = list(component.tags)
        result["simulation_support"] = bool(simulation.get("supported", False))
        result["renderer"] = simulation.get("renderer", "")
        result["firmware_support"] = list((document.get("firmware") or {}).get("supported_frameworks", []))
        return result

    def list_versions(self, component_id: str) -> list[dict[str, Any]]:
        if self.registry.get(component_id) is None:
            raise KeyError(f"component not found: {component_id}")
        return [{"component_id": component_id, "version": version} for version in self.registry.list_versions(component_id)]

    def get_metadata(self, component_id: str) -> dict[str, Any]:
        component = self.registry.require(component_id)
        document = self.index.get(component_id) or {}
        return {
            "id": component.component_id,
            "name": component.name,
            "version": component.version,
            "manufacturer": component.manufacturer,
            "description": component.description,
            "category": component.category,
            "tags": list(component.tags),
            "interfaces": list(component.interfaces),
            "simulation_support": bool((document.get("simulation") or {}).get("supported", False)),
            "renderer": (document.get("rendering") or {}).get("renderer_type", ""),
            "firmware_support": list((document.get("firmware") or {}).get("supported_frameworks", [])),
        }

    def list_controllers(self) -> list[dict[str, Any]]:
        return [c.to_dict() for c in self.controllers.list_all()]

    def debug(self) -> dict[str, Any]:
        components = self.registry.list_all()
        categories = sorted({c.category for c in components})
        samples = []
        for comp in components[:12]:
            doc = self.index.get(comp.component_id)
            samples.append(
                {
                    "id": comp.component_id,
                    "name": comp.name,
                    "category": comp.category,
                    "interfaces": list(comp.interfaces),
                    "keywords": list(comp.tags)[:8],
                    "has_json": doc is not None,
                }
            )
        return {
            "total_components": len(components),
            "json_catalog_count": len(self.index.all()),
            "components_dir": str(resolve_components_dir()),
            "categories": categories,
            "sample_components": samples,
        }
