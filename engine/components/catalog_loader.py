"""Load structured JSON component catalog into ComponentSpec registry."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from .models import ComponentSpec, PinRequirement
from .paths import resolve_components_dir
from .search.index import ComponentIndex


_IFACE_MAP = {
    "gpio": "digital",
    "digital": "digital",
    "analog": "analog",
    "adc": "analog",
    "pwm": "pwm",
    "i2c": "i2c",
    "spi": "spi",
    "uart": "uart",
    "onewire": "onewire",
    "wifi": "wifi",
    "bluetooth": "bluetooth",
}


def normalize_interfaces(raw: list[Any]) -> list[str]:
    out: list[str] = []
    for item in raw:
        key = str(item).strip().lower()
        mapped = _IFACE_MAP.get(key, key)
        if mapped and mapped not in out:
            out.append(mapped)
    return out


def json_doc_to_spec(data: dict[str, Any]) -> ComponentSpec:
    cid = str(data.get("id") or data.get("component_id") or "")
    voltage = data.get("voltage") or {}
    vmax = float(voltage.get("max", voltage.get("min", data.get("voltage_v", 3.3))))
    pin_list = data.get("pins") if isinstance(data.get("pins"), list) else []
    interfaces = normalize_interfaces(list(data.get("interfaces") or []))
    keywords = [str(k) for k in (data.get("keywords") or [])]
    aliases = [str(a) for a in (data.get("aliases") or [])]
    category = str(data.get("category") or "module").lower()
    return ComponentSpec(
        component_id=cid,
        name=str(data.get("name") or cid),
        category=category,
        description=str(data.get("description") or ""),
        manufacturer=str(data.get("manufacturer") or "Generic"),
        interfaces=interfaces,
        voltage_v=vmax,
        current_ma=float(data.get("current_ma", 0.0)),
        pins=PinRequirement(
            count=max(1, len(pin_list)),
            interfaces=interfaces[:3] or ["digital"],
            notes=", ".join(str(p.get("name") or "") for p in pin_list if isinstance(p, dict)),
        ),
        libraries=list(data.get("libraries") or []),
        tags=keywords + aliases,
        datasheet_url=str(data.get("datasheet_url") or ""),
    )


def load_json_specs(components_dir: Optional[Path | str] = None) -> list[ComponentSpec]:
    directory = resolve_components_dir(components_dir) if components_dir else resolve_components_dir()
    index = ComponentIndex(directory)
    specs: list[ComponentSpec] = []
    for doc in index.all():
        try:
            specs.append(json_doc_to_spec(doc))
        except (KeyError, TypeError, ValueError):
            continue
    return specs
