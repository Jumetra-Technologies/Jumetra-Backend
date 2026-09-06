from __future__ import annotations
import json
from pathlib import Path
from engine.component_registry.checksum import ChecksumVerifier

def make_package(root: Path, component_id: str = "dht11", *, source: str = "community", valid: bool = True, manufacturer: str = "Aosong") -> Path:
    package = root / source / "sensors" / component_id
    package.mkdir(parents=True)
    component = {"id": component_id, "name": component_id.upper(), "category": "sensor", "manufacturer": manufacturer, "interfaces": ["GPIO"], "voltage": [3.3], "behavior": "digital_sensor", "renderer": "renderer.svg", "pins": "pins.json", "keywords": ["temperature", "sensor"]}
    if not valid: component.pop("name")
    manifest = {"package": f"{source}.{component_id}", "version": "1.0.0", "author": "Test", "license": "MIT", "engine_version": "1.0", "trust_level": source if source in {"official", "community"} else "unverified"}
    (package / "component.json").write_text(json.dumps(component), encoding="utf-8")
    (package / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (package / "pins.json").write_text(json.dumps([{ "name": "DATA", "type": "GPIO"}]), encoding="utf-8")
    (package / "renderer.svg").write_text("<svg/>", encoding="utf-8")
    if source == "official": (package / "checksum.sha256").write_text(ChecksumVerifier.calculate(package), encoding="utf-8")
    return package
