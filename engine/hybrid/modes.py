"""Hybrid device mode enumeration."""

from __future__ import annotations

from enum import Enum


class HybridDeviceMode(str, Enum):
    """How a device participates in a hybrid experiment."""

    PHYSICAL = "physical"
    VIRTUAL = "virtual"
    SIMULATED = "simulated"
    HYBRID = "hybrid"
