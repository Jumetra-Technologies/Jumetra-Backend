"""ComponentDefinition — full v2 package model."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .pin_model import PinDefinition
from .schema import validate_manifest_shape


@dataclass
class VisualSpec:
    renderer: str = "renderer.svg"
    width: float = 140
    height: float = 100

    def to_dict(self) -> dict[str, Any]:
        return {"renderer": self.renderer, "width": self.width, "height": self.height}

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "VisualSpec":
        data = data or {}
        return cls(
            renderer=str(data.get("renderer") or "renderer.svg"),
            width=float(data.get("width", 140)),
            height=float(data.get("height", 100)),
        )


@dataclass
class SimulationSpec:
    behavior: str = ""
    supported: bool = True
    model: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"behavior": self.behavior, "supported": self.supported, "model": self.model or self.behavior}

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "SimulationSpec":
        data = data or {}
        behavior = str(data.get("behavior") or data.get("model") or "")
        return cls(
            behavior=behavior,
            supported=bool(data.get("supported", True)),
            model=str(data.get("model") or behavior),
        )


@dataclass
class HardwareSpec:
    physical_supported: bool = False
    transports: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"physical_supported": self.physical_supported, "transports": list(self.transports)}

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "HardwareSpec":
        data = data or {}
        return cls(
            physical_supported=bool(data.get("physical_supported", False)),
            transports=list(data.get("transports") or []),
        )


@dataclass
class ComponentDefinition:
    id: str
    name: str
    category: str
    manufacturer: str = "Generic"
    description: str = ""
    visual: VisualSpec = field(default_factory=VisualSpec)
    pins: list[PinDefinition] = field(default_factory=list)
    interfaces: list[str] = field(default_factory=list)
    simulation: SimulationSpec = field(default_factory=SimulationSpec)
    hardware: HardwareSpec = field(default_factory=HardwareSpec)
    keywords: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    package_path: Optional[Path] = None
    datasheet_md: str = ""
    renderer_svg: str = ""

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.id:
            errors.append("id required")
        if not self.name:
            errors.append("name required")
        if not self.pins:
            errors.append("at least one pin required")
        for pin in self.pins:
            errors.extend(pin.validate())
        ids = [p.id for p in self.pins]
        if len(ids) != len(set(ids)):
            errors.append("duplicate pin ids")
        return errors

    def pin_by_id(self, pin_id: str) -> Optional[PinDefinition]:
        for pin in self.pins:
            if pin.id == pin_id or pin.name.upper() == pin_id.upper():
                return pin
        return None

    def renderer_path(self) -> Optional[Path]:
        if not self.package_path:
            return None
        path = self.package_path / self.visual.renderer
        return path if path.exists() else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "manufacturer": self.manufacturer,
            "description": self.description,
            "visual": self.visual.to_dict(),
            "pins": [p.to_dict() for p in self.pins],
            "interfaces": list(self.interfaces),
            "simulation": self.simulation.to_dict(),
            "hardware": self.hardware.to_dict(),
            "keywords": list(self.keywords),
            "aliases": list(self.aliases),
            "package_path": str(self.package_path) if self.package_path else "",
            "has_renderer": bool(self.renderer_svg or self.renderer_path()),
            "has_datasheet": bool(self.datasheet_md),
        }

    def to_search_hit(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "manufacturer": self.manufacturer,
            "description": self.description,
            "preview": f"/api/components/v2/{self.id}/renderer.svg",
            "pins": [p.to_dict() for p in self.pins],
            "interfaces": list(self.interfaces),
            "keywords": list(self.keywords),
            "aliases": list(self.aliases),
            "simulation": self.simulation.to_dict(),
            "hardware": self.hardware.to_dict(),
            "visual": self.visual.to_dict(),
        }

    @classmethod
    def from_manifest(
        cls,
        data: dict[str, Any],
        *,
        package_path: Path | None = None,
        datasheet_md: str = "",
        renderer_svg: str = "",
    ) -> "ComponentDefinition":
        shape_errors = validate_manifest_shape(data)
        if shape_errors:
            raise ValueError("; ".join(shape_errors))
        pins = [PinDefinition.from_dict(p) for p in (data.get("pins") or []) if isinstance(p, dict)]
        return cls(
            id=str(data["id"]),
            name=str(data["name"]),
            category=str(data.get("category") or "module").lower(),
            manufacturer=str(data.get("manufacturer") or "Generic"),
            description=str(data.get("description") or data.get("name") or ""),
            visual=VisualSpec.from_dict(data.get("visual") if isinstance(data.get("visual"), dict) else None),
            pins=pins,
            interfaces=[str(i) for i in (data.get("interfaces") or [])],
            simulation=SimulationSpec.from_dict(data.get("simulation") if isinstance(data.get("simulation"), dict) else None),
            hardware=HardwareSpec.from_dict(data.get("hardware") if isinstance(data.get("hardware"), dict) else None),
            keywords=[str(k) for k in (data.get("keywords") or [])],
            aliases=[str(a) for a in (data.get("aliases") or [])],
            package_path=package_path,
            datasheet_md=datasheet_md,
            renderer_svg=renderer_svg,
        )
