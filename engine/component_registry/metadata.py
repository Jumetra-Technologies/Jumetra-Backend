"""Normalized metadata exposed by the component package registry."""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from .manifest import ComponentManifest

@dataclass
class ComponentMetadata:
    component_id: str
    name: str
    category: str
    manufacturer: str
    interfaces: list[str]
    voltage: list[float]
    behavior: str
    renderer: str
    pins: list[dict[str, Any]]
    keywords: list[str]
    manifest: ComponentManifest
    location: Path
    checksum: str = ""
    source: str = "community"
    trusted: bool = False
    extras: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.component_id, "name": self.name, "category": self.category, "manufacturer": self.manufacturer, "interfaces": list(self.interfaces), "voltage": list(self.voltage), "behavior": self.behavior, "renderer": self.renderer, "pins": list(self.pins), "keywords": list(self.keywords), "manifest": self.manifest.to_dict(), "location": str(self.location), "checksum": self.checksum, "source": self.source, "trusted": self.trusted, **self.extras}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "ComponentMetadata":
        data = dict(raw)
        known = {"id", "name", "category", "manufacturer", "interfaces", "voltage", "behavior", "renderer", "pins", "keywords", "manifest", "location", "checksum", "source", "trusted"}
        return cls(component_id=str(data["id"]), name=str(data["name"]), category=str(data["category"]), manufacturer=str(data["manufacturer"]), interfaces=[str(x) for x in data["interfaces"]], voltage=[float(x) for x in data["voltage"]], behavior=str(data["behavior"]), renderer=str(data["renderer"]), pins=list(data["pins"]), keywords=[str(x) for x in data["keywords"]], manifest=ComponentManifest.from_dict(data["manifest"]), location=Path(data["location"]), checksum=str(data.get("checksum") or ""), source=str(data.get("source") or "community"), trusted=bool(data.get("trusted")), extras={k: v for k, v in data.items() if k not in known})
