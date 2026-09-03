"""Wire validation and auto-routing helpers for the engineering canvas."""

from __future__ import annotations

from typing import Any

from .bus import build_bus_metadata, infer_bus_type
from .catalog import get_component
from .models import CanvasNode, CanvasWire


WIRE_COLORS = {
    "digital": "#2563eb",
    "analog": "#059669",
    "pwm": "#d97706",
    "i2c": "#7c3aed",
    "spi": "#db2777",
    "uart": "#0891b2",
    "power": "#dc2626",
    "ground": "#52525b",
}


def _voltage_range(spec: dict[str, Any] | None) -> tuple[float, float]:
    if not spec:
        return 3.3, 3.3
    voltage = spec.get("voltage") or {}
    if isinstance(voltage, dict) and voltage:
        vmin = float(voltage.get("min", voltage.get("max", spec.get("voltage_v", 3.3))))
        vmax = float(voltage.get("max", voltage.get("min", vmin)))
        return vmin, vmax
    v = float(spec.get("voltage_v", 3.3))
    return v, v


def validate_wire(
    wire: CanvasWire,
    nodes: dict[str, CanvasNode],
) -> CanvasWire:
    issues: list[str] = []
    source = nodes.get(wire.source)
    target = nodes.get(wire.target)

    if source is None or target is None:
        issues.append("Missing endpoint node")
        wire.valid = False
        wire.issues = issues
        return wire

    src_spec = get_component(source.component_id)
    tgt_spec = get_component(target.component_id)

    if src_spec and tgt_spec:
        src_protocols = {str(p).lower() for p in (src_spec.get("protocols") or src_spec.get("interfaces") or [])}
        tgt_protocols = {str(p).lower() for p in (tgt_spec.get("protocols") or tgt_spec.get("interfaces") or [])}
        # Normalize GPIO/Digital aliases
        for bag in (src_protocols, tgt_protocols):
            if "gpio" in bag:
                bag.add("digital")
            if "digital" in bag:
                bag.add("gpio")

        if wire.protocol not in src_protocols and wire.protocol not in {"power", "ground"}:
            issues.append(f"Source does not support protocol {wire.protocol}")
        if wire.protocol not in tgt_protocols and wire.protocol not in {"power", "ground"}:
            issues.append(f"Target does not support protocol {wire.protocol}")

        src_min, src_max = _voltage_range(src_spec)
        tgt_min, tgt_max = _voltage_range(tgt_spec)
        # Hard reject: 5V rail / high-voltage source into 3.3V-only device
        if wire.protocol == "power" or "5V" in (wire.source_handle or "").upper():
            if src_max >= 4.5 and tgt_max <= 3.4:
                issues.append(
                    f"Voltage mismatch: {source.component_id} {wire.source_handle or 'output'} "
                    f"is {src_max}V (target max {tgt_max}V)"
                )
                wire.valid = False
                wire.issues = issues
                wire.color = "#dc2626"
                return wire
        if abs(src_max - tgt_max) > 0.6 and wire.protocol not in {"power", "ground"}:
            if src_max >= 4.5 and tgt_max <= 3.4:
                issues.append(
                    f"Voltage mismatch: {source.component_id} GPIO is {src_max}V"
                )
                wire.valid = False
                wire.issues = issues
                wire.color = "#dc2626"
                return wire
            issues.append(f"Voltage mismatch: {src_max}V vs {tgt_max}V")

    if wire.source_handle and wire.target_handle and wire.source_handle == wire.target_handle:
        if wire.source == wire.target:
            issues.append("Cannot connect a pin to itself")

    bus = build_bus_metadata(
        protocol=wire.protocol,
        source_handle=wire.source_handle,
        target_handle=wire.target_handle,
        source_component_id=source.component_id,
        target_component_id=target.component_id,
    )
    if bus:
        wire.bus = bus
        inferred = infer_bus_type(wire.source_handle, wire.target_handle, wire.protocol)
        if inferred:
            wire.protocol = inferred
        if bus.get("address") and not wire.label:
            wire.label = f"{bus['type']} {bus['address']}"
        elif not wire.label:
            wire.label = str(bus.get("type") or wire.protocol).upper()

    wire.issues = issues
    hard = any("Cannot" in i or "Missing" in i or i.startswith("Voltage mismatch") for i in issues)
    # Voltage mismatch already returned early when hard-rejected; remaining voltage notes are warnings
    wire.valid = not any("Cannot" in i or "Missing" in i for i in issues)
    if issues and not hard:
        wire.valid = True
    wire.color = WIRE_COLORS.get(wire.protocol, "#2563eb")
    if not wire.valid:
        wire.color = "#dc2626"
    if not wire.label:
        wire.label = f"{wire.source_handle}→{wire.target_handle}"
    return wire


def validate_wire_with_peers(
    wire: CanvasWire,
    nodes: dict[str, CanvasNode],
    all_wires: dict[str, CanvasWire],
) -> CanvasWire:
    wire = validate_wire(wire, nodes)
    for other in all_wires.values():
        if other.wire_id == wire.wire_id:
            continue
        if (
            other.source == wire.source
            and other.source_handle == wire.source_handle
            and other.source_handle
        ):
            wire.issues.append(f"Duplicate source pin {wire.source_handle}")
        if (
            other.target == wire.target
            and other.target_handle == wire.target_handle
            and other.target_handle
        ):
            wire.issues.append(f"Duplicate target pin {wire.target_handle}")
    return wire


def auto_route_points(
    source_pos: dict[str, float],
    target_pos: dict[str, float],
) -> list[dict[str, float]]:
    """Simple orthogonal auto-route between two node centers."""
    mid_x = (source_pos.get("x", 0) + target_pos.get("x", 0)) / 2
    return [
        {"x": source_pos.get("x", 0), "y": source_pos.get("y", 0)},
        {"x": mid_x, "y": source_pos.get("y", 0)},
        {"x": mid_x, "y": target_pos.get("y", 0)},
        {"x": target_pos.get("x", 0), "y": target_pos.get("y", 0)},
    ]
