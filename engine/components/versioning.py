"""Small SemVer-compatible resolver for component package versions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

VERSION_PATTERN = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-([0-9A-Za-z.-]+))?(?:\+([0-9A-Za-z.-]+))?$")


@dataclass(frozen=True, order=True)
class ComponentVersion:
    major: int
    minor: int
    patch: int
    prerelease: str = ""

    @classmethod
    def parse(cls, value: str) -> "ComponentVersion":
        match = VERSION_PATTERN.fullmatch(str(value).strip())
        if not match:
            raise ValueError(f"invalid component version: {value}")
        return cls(int(match.group(1)), int(match.group(2)), int(match.group(3)), match.group(4) or "")

    def __str__(self) -> str:
        suffix = f"-{self.prerelease}" if self.prerelease else ""
        return f"{self.major}.{self.minor}.{self.patch}{suffix}"


def resolve_latest(versions: Iterable[str]) -> str:
    parsed = [(ComponentVersion.parse(version), version) for version in versions]
    if not parsed:
        raise ValueError("cannot resolve latest version from an empty collection")
    return max(parsed, key=lambda item: item[0])[1]


def versioned_id(component_id: str, version: str) -> str:
    ComponentVersion.parse(version)
    return f"{component_id}@{version}"