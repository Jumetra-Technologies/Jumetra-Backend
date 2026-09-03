"""Wire rendering metadata — colors, animation hints for the canvas."""

from __future__ import annotations

from typing import Any

from .pin_connection import WIRE_COLORS, PinConnection


class WireRenderer:
    """Describe how a wire should be drawn (SVG animation + colors)."""

    FLOW_ANIMATION = {
        "digital": {"dash": "8 6", "speed_ms": 800},
        "analog": {"dash": "4 8", "speed_ms": 1200},
        "pwm": {"dash": "2 4", "speed_ms": 400},
        "power": {"dash": None, "speed_ms": 0},
        "ground": {"dash": None, "speed_ms": 0},
        "uart": {"dash": "6 3", "speed_ms": 500},
        "spi": {"dash": "3 3", "speed_ms": 350},
        "i2c": {"dash": "5 5", "speed_ms": 600},
        "hybrid": {"dash": "8 6", "speed_ms": 700},
    }

    @classmethod
    def color_for(cls, wire_type: str) -> str:
        return WIRE_COLORS.get((wire_type or "digital").lower(), WIRE_COLORS["digital"])

    @classmethod
    def render_spec(cls, conn: PinConnection, *, signal_high: bool = False) -> dict[str, Any]:
        anim = dict(cls.FLOW_ANIMATION.get(conn.wire_type, cls.FLOW_ANIMATION["digital"]))
        return {
            "connection_id": conn.connection_id,
            "color": conn.wire_color or cls.color_for(conn.wire_type),
            "wire_type": conn.wire_type,
            "animated": conn.wire_type not in ("power", "ground"),
            "flow": anim,
            "signal_high": signal_high,
            "stroke_width": 3 if signal_high else 2.5,
            "routing": list(conn.routing),
            "status": conn.status,
            "valid": conn.valid,
        }

    @classmethod
    def auto_route(
        cls,
        source_pos: dict[str, float],
        target_pos: dict[str, float],
    ) -> list[dict[str, float]]:
        mid_x = (source_pos.get("x", 0) + target_pos.get("x", 0)) / 2
        return [
            {"x": float(source_pos.get("x", 0)), "y": float(source_pos.get("y", 0))},
            {"x": mid_x, "y": float(source_pos.get("y", 0))},
            {"x": mid_x, "y": float(target_pos.get("y", 0))},
            {"x": float(target_pos.get("x", 0)), "y": float(target_pos.get("y", 0))},
        ]
