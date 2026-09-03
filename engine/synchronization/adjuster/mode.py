"""Correction modes for SafeClockAdjuster."""

from __future__ import annotations

from enum import Enum


class CorrectionMode(str, Enum):
    """How corrections are applied (default: dry run only)."""

    DRY_RUN = "dry_run"
    SOFT = "soft"
    STEP = "step"
    DISABLED = "disabled"

    @classmethod
    def default(cls) -> "CorrectionMode":
        return cls.DRY_RUN
