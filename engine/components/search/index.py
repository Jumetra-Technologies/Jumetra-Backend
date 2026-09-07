"""In-memory full-text index over the JSON component catalog."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

from engine.components.paths import resolve_components_dir

logger = logging.getLogger("hhip.components")


def default_components_dir() -> Path:
    return resolve_components_dir()


class ComponentIndex:
    """Load and index component JSON documents for search."""

    def __init__(self, components_dir: Optional[Path | str] = None) -> None:
        self.components_dir = (
            Path(components_dir).resolve() if components_dir else resolve_components_dir()
        )
        self._docs: dict[str, dict[str, Any]] = {}
        self._haystacks: dict[str, str] = {}
        self.reload()

    def reload(self) -> int:
        self._docs.clear()
        self._haystacks.clear()
        if not self.components_dir.exists():
            logger.warning("Component catalog missing: %s", self.components_dir)
            return 0
        for path in sorted(self.components_dir.rglob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning("Skipping invalid component JSON %s: %s", path, exc)
                continue
            cid = str(data.get("id") or data.get("component_id") or path.stem)
            data["id"] = cid
            data.setdefault("component_id", cid)
            self._docs[cid] = data
            self._haystacks[cid] = self._build_haystack(data)
        logger.info(
            "Loaded components: %s (from %s)",
            len(self._docs),
            self.components_dir,
        )
        return len(self._docs)

    def all(self) -> list[dict[str, Any]]:
        return list(self._docs.values())

    def get(self, component_id: str) -> Optional[dict[str, Any]]:
        return self._docs.get(component_id)

    def haystack(self, component_id: str) -> str:
        return self._haystacks.get(component_id, "")

    @staticmethod
    def _build_haystack(data: dict[str, Any]) -> str:
        parts = [
            str(data.get("id") or ""),
            str(data.get("name") or ""),
            str(data.get("category") or ""),
            str(data.get("manufacturer") or ""),
            str(data.get("description") or ""),
            " ".join(str(x) for x in (data.get("interfaces") or [])),
            " ".join(str(x) for x in (data.get("keywords") or [])),
            " ".join(str(x) for x in (data.get("aliases") or [])),
            " ".join(str(x) for x in (data.get("compatible_controllers") or [])),
            " ".join(str(p.get("name") or "") for p in (data.get("pins") or []) if isinstance(p, dict)),
        ]
        return " ".join(parts).lower()

    def to_explorer_item(self, data: dict[str, Any]) -> dict[str, Any]:
        """Shape compatible with lab_workspace explorer + workspace add_node."""
        cat = str(data.get("category") or "module")
        explorer_cat = {
            "mcu": _mcu_bucket(str(data.get("id") or "")),
            "sensor": "sensors",
            "actuator": "actuators",
            "display": "displays",
            "communication": "communication",
            "power": "actuators",
        }.get(cat, cat if cat.endswith("s") else f"{cat}s")
        voltage = data.get("voltage") or {}
        vmax = float(voltage.get("max", voltage.get("min", 3.3)))
        protocols = [str(i).lower() for i in (data.get("interfaces") or [])]
        if "gpio" not in protocols and "digital" in protocols:
            protocols.append("gpio")
        return {
            "component_id": data["id"],
            "name": data.get("name") or data["id"],
            "category": explorer_cat,
            "catalog_category": cat,
            "manufacturer": data.get("manufacturer") or "",
            "description": data.get("description") or "",
            "protocols": protocols,
            "interfaces": list(data.get("interfaces") or []),
            "voltage_v": vmax,
            "voltage": voltage,
            "pins": data.get("pins") or [],
            "keywords": data.get("keywords") or [],
            "aliases": data.get("aliases") or [],
            "compatible_controllers": data.get("compatible_controllers") or [],
            "simulation": data.get("simulation") or {},
        }


def _mcu_bucket(cid: str) -> str:
    c = cid.lower()
    if "arduino" in c:
        return "arduino"
    if "esp" in c:
        return "esp32"
    if "stm" in c:
        return "stm32"
    if "pico" in c or "raspberry-pi-4" in c or c.startswith("raspberry"):
        return "pico"
    if "teensy" in c or "microbit" in c:
        return "arduino"
    return "esp32"
