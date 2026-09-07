"""Configuration for component package security checks."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ComponentSecurityPolicy:
    max_file_bytes: int = 1024 * 1024
    allowed_extensions: frozenset[str] = field(
        default_factory=lambda: frozenset({".json", ".md", ".txt", ".svg"})
    )
    blocked_metadata_keys: frozenset[str] = field(
        default_factory=lambda: frozenset({"script", "exec", "command", "executable", "code"})
    )