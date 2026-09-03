"""Hardware nodes — digital twin of physical boards in the Engineering Workspace."""

from __future__ import annotations

from .board_renderer import BoardRenderer, get_pin_layout, layout_as_dicts
from .discovery_listener import DiscoveryListener
from .hardware_node import HardwareNode, HardwareNodeStatus
from .hardware_node_factory import HardwareNodeFactory
from .pin_layout import (
    PIN_COLORS,
    HardwarePinDef,
    LivePinState,
    PinKind,
    PinLogicState,
)
from .workspace_sync import WorkspaceEventType, WorkspaceSyncService

__all__ = [
    "BoardRenderer",
    "DiscoveryListener",
    "HardwareNode",
    "HardwareNodeFactory",
    "HardwareNodeStatus",
    "HardwarePinDef",
    "LivePinState",
    "PIN_COLORS",
    "PinKind",
    "PinLogicState",
    "WorkspaceEventType",
    "WorkspaceSyncService",
    "get_pin_layout",
    "layout_as_dicts",
]
