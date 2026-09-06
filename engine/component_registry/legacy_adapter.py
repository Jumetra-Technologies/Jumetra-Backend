"""Compatibility bridge for the existing, code-backed component catalog."""
from __future__ import annotations
from pathlib import Path
from engine.components.models import ComponentSpec
from .manifest import ComponentManifest
from .metadata import ComponentMetadata

def from_legacy(spec: ComponentSpec) -> ComponentMetadata:
    return ComponentMetadata(component_id=spec.component_id, name=spec.name, category=spec.category, manufacturer=spec.manufacturer, interfaces=list(spec.interfaces), voltage=[spec.voltage_v], behavior="legacy", renderer="", pins=[], keywords=list(spec.tags), manifest=ComponentManifest(package=f"legacy.{spec.component_id}", version="0.0.0", author="HHIP legacy catalog", license="unknown", engine_version="1.0", trust_level="local"), location=Path("legacy") / spec.component_id, source="legacy", trusted=True, extras={"legacy": True})
