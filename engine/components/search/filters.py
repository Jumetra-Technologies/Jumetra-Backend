"""Search filters for the component catalog."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


CATEGORY_ALIASES: dict[str, set[str]] = {
    "mcu": {"mcu", "microcontroller", "arduino", "esp32", "stm32", "pico", "controller"},
    "sensor": {"sensor", "sensors"},
    "actuator": {"actuator", "actuators"},
    "display": {"display", "displays"},
    "communication": {"communication", "comms", "wireless"},
    "power": {"power"},
}


@dataclass
class SearchFilters:
    """Structured filters for ComponentSearchEngine."""

    category: Optional[str] = None
    categories: list[str] = field(default_factory=list)
    interface: Optional[str] = None
    interfaces: list[str] = field(default_factory=list)
    voltage: Optional[float] = None  # e.g. 3.3 or 5.0
    voltages: list[float] = field(default_factory=list)
    controller_id: Optional[str] = None
    simulation_only: bool = False

    @classmethod
    def from_params(cls, params: dict[str, Any]) -> "SearchFilters":
        cats = params.get("categories") or []
        if isinstance(cats, str):
            cats = [c.strip() for c in cats.split(",") if c.strip()]
        ifaces = params.get("interfaces") or []
        if isinstance(ifaces, str):
            ifaces = [i.strip() for i in ifaces.split(",") if i.strip()]
        volts = params.get("voltages") or []
        if isinstance(volts, str):
            volts = [float(v) for v in volts.split(",") if v.strip()]
        voltage = params.get("voltage")
        return cls(
            category=str(params["category"]).lower() if params.get("category") else None,
            categories=[str(c).lower() for c in cats],
            interface=str(params["interface"]) if params.get("interface") else None,
            interfaces=[str(i) for i in ifaces],
            voltage=float(voltage) if voltage not in (None, "") else None,
            voltages=[float(v) for v in volts],
            controller_id=str(params["controller_id"]) if params.get("controller_id") else None,
            simulation_only=bool(params.get("simulation_only", False)),
        )

    def matches(self, doc: dict[str, Any]) -> bool:
        cat = str(doc.get("category") or "").lower()
        wanted_cats = set(self.categories)
        if self.category:
            wanted_cats.add(self.category)
        if wanted_cats:
            expanded: set[str] = set()
            for w in wanted_cats:
                expanded |= CATEGORY_ALIASES.get(w, {w})
                expanded.add(w)
            if cat not in expanded and not any(w in cat for w in expanded):
                return False

        doc_ifaces = {str(i).upper() for i in (doc.get("interfaces") or [])}
        wanted_ifaces = {i.upper() for i in self.interfaces}
        if self.interface:
            wanted_ifaces.add(self.interface.upper())
        if wanted_ifaces and not (doc_ifaces & wanted_ifaces):
            # also allow lowercase digital/gpio aliases
            aliases = set()
            for w in wanted_ifaces:
                if w in ("GPIO", "DIGITAL"):
                    aliases.update({"GPIO", "DIGITAL"})
            if not (doc_ifaces & (wanted_ifaces | aliases)):
                return False

        vmin = float((doc.get("voltage") or {}).get("min", doc.get("voltage_v", 3.3)))
        vmax = float((doc.get("voltage") or {}).get("max", doc.get("voltage_v", vmin)))
        wanted_volts = list(self.voltages)
        if self.voltage is not None:
            wanted_volts.append(self.voltage)
        if wanted_volts:
            ok = False
            for v in wanted_volts:
                if vmin - 0.05 <= v <= vmax + 0.05 or abs(vmin - v) < 0.2 or abs(vmax - v) < 0.2:
                    ok = True
                    break
            if not ok:
                return False

        if self.controller_id:
            controllers = [str(c).lower() for c in (doc.get("compatible_controllers") or [])]
            cid = self.controller_id.lower()
            if cid not in controllers and not any(cid in c or c in cid for c in controllers):
                return False

        if self.simulation_only:
            sim = doc.get("simulation") or {}
            if not sim.get("supported", False):
                return False

        return True
