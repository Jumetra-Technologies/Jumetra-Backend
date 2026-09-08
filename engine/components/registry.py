"""Component registry and search."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from .loader import ComponentLoader
from .models import ComponentSearchResult, ComponentSpec
from .paths import resolve_components_dir
from .seed import SEED_COMPONENTS
from .package_loader import ComponentPackageLoader
from .resolution import ComponentResolver
from .schema import ComponentDefinition
from .versioning import resolve_latest, versioned_id

logger = logging.getLogger("hhip.components")

CATEGORY_ALIASES: dict[str, set[str]] = {
    "sensor": {"sensor", "sensors"},
    "sensors": {"sensor", "sensors"},
    "actuator": {"actuator", "actuators"},
    "actuators": {"actuator", "actuators"},
    "display": {"display", "displays"},
    "displays": {"display", "displays"},
    "communication": {"communication", "comms"},
    "mcu": {"mcu", "module", "microcontroller", "controller"},
    "module": {"mcu", "module"},
    "power": {"power"},
}

INTERFACE_ALIASES: dict[str, set[str]] = {
    "gpio": {"gpio", "digital"},
    "digital": {"gpio", "digital"},
    "pwm": {"pwm"},
    "uart": {"uart"},
    "i2c": {"i2c"},
    "spi": {"spi"},
    "analog": {"analog", "adc"},
    "adc": {"analog", "adc"},
}


class ComponentRegistry:
    """In-memory catalog of hardware components."""

    def __init__(self) -> None:
        self._components: dict[str, ComponentSpec] = {}
        self._versions: dict[str, dict[str, ComponentSpec]] = {}
        self._definitions: dict[str, ComponentDefinition] = {}
        self.components_dir = resolve_components_dir()
        self.json_loaded = 0

    def register(self, component: ComponentSpec) -> None:
        self._components[component.component_id] = component
        self._versions.setdefault(component.component_id, {})[component.version] = component

    def register_definition(self, definition: ComponentDefinition) -> None:
        self._definitions[versioned_id(definition.component_id, definition.version)] = definition
        self.register(definition.to_spec())

    def load_components(self, path: Optional[str] = None) -> int:
        """Load and register validated JSON definitions recursively."""
        if path:
            self.components_dir = Path(path).expanduser().resolve()
        legacy_loader = ComponentLoader()
        loaded = legacy_loader.load(self.components_dir)
        packages = ComponentPackageLoader().load(self.components_dir)
        selected = ComponentResolver().resolve(packages, loaded)
        package_by_id = {package.spec.component_id: package for package in packages}
        package_ids = set(package_by_id)
        for selected_component in selected:
            component = getattr(selected_component, "spec", selected_component)
            if component.component_id in package_ids:
                package = selected_component if hasattr(selected_component, "definition") else package_by_id[component.component_id]
                self.register_definition(package.definition)
                logger.info("Loaded component package: %s@%s", component.component_id, component.version)
            else:
                self.register(component)
                logger.info("Loaded legacy component: %s@legacy", component.component_id)
        for component in loaded:
            if component.component_id in package_ids:
                source = legacy_loader.source_paths.get(component.component_id)
                logger.info("Ignored duplicate legacy component: %s", source.name if source else component.component_id)
        self.json_loaded = len(selected)
        return len(selected)

    def get(self, component_id: str) -> Optional[ComponentSpec]:
        if "@" in component_id:
            base_id, requested_version = component_id.rsplit("@", 1)
            return self._versions.get(base_id, {}).get(requested_version)
        return self._components.get(component_id)

    def list_versions(self, component_id: str) -> list[str]:
        return sorted(self._versions.get(component_id, {}), key=lambda value: tuple(int(part) for part in value.split(".")[:3]))

    def latest_version(self, component_id: str) -> Optional[str]:
        versions = self.list_versions(component_id)
        return resolve_latest(versions) if versions else None

    def get_definition(self, component_id: str, version: str | None = None) -> Optional[ComponentDefinition]:
        selected = version or self.latest_version(component_id)
        return self._definitions.get(versioned_id(component_id, selected)) if selected else None

    def require(self, component_id: str) -> ComponentSpec:
        comp = self.get(component_id)
        if comp is None:
            raise KeyError(f"component not found: {component_id}")
        return comp

    def list_all(self) -> list[ComponentSpec]:
        return sorted(self._components.values(), key=lambda c: c.name)

    def search(self, query: str = "", **filters: object) -> list[ComponentSearchResult]:
        """Search registered components using the registry's standard search engine."""
        return ComponentSearch(self).search(query, **filters)

    def load_seed(self) -> None:
        for component in SEED_COMPONENTS:
            self.register(component)

    def load_json_catalog(self, components_dir: Optional[str] = None) -> int:
        """Backward-compatible alias for the external component loader."""
        return self.load_components(components_dir)


class ComponentSearch:
    """Search components by name, id, aliases, keywords, category, or interface."""

    def __init__(self, registry: ComponentRegistry) -> None:
        self.registry = registry

    def search(
        self,
        query: str = "",
        *,
        category: Optional[str] = None,
        interface: Optional[str] = None,
        limit: int = 50,
    ) -> list[ComponentSearchResult]:
        query_lower = query.strip().lower()
        results: list[ComponentSearchResult] = []
        wanted_cats = CATEGORY_ALIASES.get((category or "").lower(), {category.lower()}) if category else None
        wanted_ifaces = None
        if interface:
            key = interface.lower()
            wanted_ifaces = INTERFACE_ALIASES.get(key, {key})

        for component in self.registry.list_all():
            if wanted_cats and component.category.lower() not in wanted_cats:
                continue
            if wanted_ifaces:
                comp_ifaces = {i.lower() for i in component.interfaces}
                if not (comp_ifaces & wanted_ifaces):
                    continue

            score = self._score(component, query_lower)
            if query_lower and score <= 0:
                continue

            results.append(ComponentSearchResult(component=component, score=score))

        results.sort(key=lambda r: (-r.score, r.component.name))
        return results[:limit]

    @staticmethod
    def _score(component: ComponentSpec, query: str) -> float:
        if not query:
            return 1.0
        cid = component.component_id.lower()
        name = component.name.lower()
        tags = [t.lower() for t in component.tags]
        haystack = " ".join(
            [
                name,
                cid,
                component.description.lower(),
                component.category.lower(),
                component.manufacturer.lower(),
                " ".join(tags),
                " ".join(i.lower() for i in component.interfaces),
            ]
        )
        score = 0.0
        if query == cid or query.replace(" ", "-") == cid:
            score += 12
        if query == name or name.startswith(query):
            score += 10
        if any(query == t or query in t or t in query for t in tags):
            score += 8
        if query in haystack:
            score += 3
        tokens = [t for t in query.replace(",", " ").split() if t]
        for tok in tokens:
            if tok in cid or tok in name:
                score += 4
            elif any(tok in t or t in tok for t in tags):
                score += 3
            elif tok in haystack:
                score += 1
        return score


def default_registry() -> ComponentRegistry:
    registry = ComponentRegistry()
    added = registry.load_components()
    total = len(registry.list_all())
    logger.info(
        "Loaded components: %s (seed + %s from %s)",
        total,
        added,
        registry.components_dir,
    )
    print(f"Loaded components: {total}", flush=True)
    return registry
