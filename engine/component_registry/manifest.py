"""Component package manifest model."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class ComponentManifest:
    package: str
    version: str
    author: str
    license: str
    engine_version: str
    trust_level: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ComponentManifest":
        return cls(**{key: str(data[key]) for key in ("package", "version", "author", "license", "engine_version", "trust_level")})

    def to_dict(self) -> dict[str, str]:
        return {"package": self.package, "version": self.version, "author": self.author, "license": self.license, "engine_version": self.engine_version, "trust_level": self.trust_level}
