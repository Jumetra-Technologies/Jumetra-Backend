"""Interactive hybrid wiring — Wokwi-style pin connections for HHIP."""

from __future__ import annotations

from .auto_mapper import AutoMapper
from .connection_events import WiringEventType, publish_wiring_event
from .connection_graph import ConnectionGraph
from .connection_history import ConnectionHistory, HistoryEntry
from .pin_connection import (
    WIRE_COLORS,
    ConnectionDirection,
    ConnectionStatus,
    PinConnection,
    PinEndpoint,
    WireType,
)
from .pin_validator import PinValidator, ValidationResult
from .wire_manager import WireManager
from .wire_renderer import WireRenderer

__all__ = [
    "AutoMapper",
    "ConnectionDirection",
    "ConnectionGraph",
    "ConnectionHistory",
    "ConnectionStatus",
    "HistoryEntry",
    "PinConnection",
    "PinEndpoint",
    "PinValidator",
    "ValidationResult",
    "WIRE_COLORS",
    "WireManager",
    "WireRenderer",
    "WireType",
    "WiringEventType",
    "publish_wiring_event",
]
