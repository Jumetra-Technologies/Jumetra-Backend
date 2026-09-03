"""Hardware profile loading from data/hardware_profiles/."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .capability import Capability


def _default_profiles_dir() -> Path:
    # hhip/engine/hybrid/hardware/profile.py -> hhip/data/hardware_profiles
    return Path(__file__).resolve().parents[3] / "data" / "hardware_profiles"


@dataclass
class HardwareProfile:
    """Static profile describing a supported hardware family."""

    profile_id: str
    vendor: str
    model: str
    category: str
    board_type: str
    label: str = ""
    default_transport: str = "serial"
    interfaces: list[str] = field(default_factory=list)
    capabilities: list[Capability] = field(default_factory=list)
    pins: list[dict[str, Any]] = field(default_factory=list)
    voltage_v: float = 3.3
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "vendor": self.vendor,
            "model": self.model,
            "category": self.category,
            "board_type": self.board_type,
            "label": self.label or self.model,
            "default_transport": self.default_transport,
            "interfaces": list(self.interfaces),
            "capabilities": [c.to_dict() for c in self.capabilities],
            "pins": list(self.pins),
            "voltage_v": self.voltage_v,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HardwareProfile":
        profile_id = str(data.get("profile_id") or data.get("board_type") or "unknown")
        return cls(
            profile_id=profile_id,
            vendor=str(data.get("vendor") or "Unknown"),
            model=str(data.get("model") or profile_id),
            category=str(data.get("category") or "microcontroller"),
            board_type=str(data.get("board_type") or profile_id),
            label=str(data.get("label") or data.get("model") or profile_id),
            default_transport=str(data.get("default_transport") or "serial"),
            interfaces=list(data.get("interfaces") or []),
            capabilities=Capability.from_list(data.get("capabilities")),
            pins=list(data.get("pins") or []),
            voltage_v=float(data.get("voltage_v") or 3.3),
            metadata=dict(data.get("metadata") or {}),
        )


class ProfileRegistry:
    """Load and resolve hardware profiles from JSON files."""

    def __init__(self, profiles_dir: Optional[Path | str] = None) -> None:
        self.profiles_dir = Path(profiles_dir) if profiles_dir else _default_profiles_dir()
        self._profiles: dict[str, HardwareProfile] = {}
        self.reload()

    def reload(self) -> None:
        self._profiles.clear()
        if not self.profiles_dir.exists():
            return
        for path in sorted(self.profiles_dir.glob("*.json")):
            try:
                with path.open("r", encoding="utf-8") as fh:
                    data = json.load(fh)
                profile = HardwareProfile.from_dict(data)
                self._profiles[profile.profile_id] = profile
                self._profiles[profile.board_type] = profile
                # Alias without hyphens/underscores
                self._profiles[profile.board_type.replace("-", "_")] = profile
                self._profiles[profile.board_type.replace("_", "-")] = profile
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                continue

    def list_profiles(self) -> list[HardwareProfile]:
        seen: set[str] = set()
        result: list[HardwareProfile] = []
        for profile in self._profiles.values():
            if profile.profile_id in seen:
                continue
            seen.add(profile.profile_id)
            result.append(profile)
        return sorted(result, key=lambda p: p.profile_id)

    def get(self, key: str) -> Optional[HardwareProfile]:
        if not key:
            return None
        k = key.strip().lower()
        if k in self._profiles:
            return self._profiles[k]
        # Fuzzy match
        for profile in self.list_profiles():
            if k in profile.board_type.lower() or k in profile.model.lower() or k in profile.profile_id.lower():
                return profile
        return None

    def resolve_board_type(self, board_type: str) -> HardwareProfile:
        profile = self.get(board_type)
        if profile is not None:
            return profile
        return HardwareProfile(
            profile_id=board_type or "unknown",
            vendor="Unknown",
            model=board_type or "Unknown Device",
            category="unknown",
            board_type=board_type or "unknown",
            label=board_type or "Unknown Device",
            capabilities=Capability.from_list(["gpio"]),
            pins=[
                {"pin_id": "D0", "name": "GPIO0", "number": 0, "interfaces": ["gpio"]},
            ],
        )


_default_registry: Optional[ProfileRegistry] = None


def get_profile_registry(profiles_dir: Optional[Path | str] = None) -> ProfileRegistry:
    global _default_registry
    if profiles_dir is not None:
        return ProfileRegistry(profiles_dir)
    if _default_registry is None:
        _default_registry = ProfileRegistry()
    return _default_registry
