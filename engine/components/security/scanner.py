"""Non-executing security scanner for component package files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .policy import ComponentSecurityPolicy


class SecurityViolation(ValueError):
    """Raised when a component package violates the loading policy."""


class ComponentSecurityScanner:
    def __init__(self, policy: ComponentSecurityPolicy | None = None) -> None:
        self.policy = policy or ComponentSecurityPolicy()

    def validate_package(self, root: Path, package: Path) -> None:
        try:
            package.resolve().relative_to(root.resolve())
        except ValueError as exc:
            raise SecurityViolation("component package escapes catalog root") from exc
        if not package.is_dir():
            raise SecurityViolation("component package must be a directory")
        for path in package.rglob("*"):
            if not path.is_file():
                continue
            self.validate_path(root, path)

    def validate_path(self, root: Path, path: Path) -> None:
        try:
            path.resolve().relative_to(root.resolve())
        except ValueError as exc:
            raise SecurityViolation("component file escapes catalog root") from exc
        if path.suffix.lower() not in self.policy.allowed_extensions:
            raise SecurityViolation(f"unsupported component file extension: {path.suffix}")
        if path.stat().st_size > self.policy.max_file_bytes:
            raise SecurityViolation(f"component file exceeds {self.policy.max_file_bytes} bytes")

    def read_json(self, root: Path, path: Path) -> Any:
        self.validate_path(root, path)
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise SecurityViolation(f"invalid JSON: {path.name}") from exc
        self._check_metadata(value)
        return value

    def _check_metadata(self, value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if str(key).lower() in self.policy.blocked_metadata_keys:
                    raise SecurityViolation(f"unsupported executable metadata: {key}")
                self._check_metadata(child)
        elif isinstance(value, list):
            for child in value:
                self._check_metadata(child)