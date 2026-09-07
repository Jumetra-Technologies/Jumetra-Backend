"""Secure recursive loader for external component definitions."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .catalog_loader import json_doc_to_spec
from .models import ComponentSpec
from .paths import resolve_components_dir
from .validator import ComponentValidator

logger = logging.getLogger("hhip.components")
MAX_FILE_BYTES = 1024 * 1024


class ComponentLoader:
    def __init__(self, validator: ComponentValidator | None = None) -> None:
        self.validator = validator or ComponentValidator()

    def load(self, path: Path | str) -> list[ComponentSpec]:
        root = Path(path).expanduser().resolve()
        if not root.is_dir():
            return []
        specs: list[ComponentSpec] = []
        seen_ids: set[str] = set()
        files = sorted(
            root.rglob("*.json"),
            key=lambda candidate: (-len(candidate.relative_to(root).parts), str(candidate)),
        )
        for file_path in files:
            if file_path.name in {"manifest.json", "pins.json", "metadata.json", "firmware.json"}:
                continue
            if not self._is_allowed_file(root, file_path):
                logger.warning("Skipping component outside catalog: %s", file_path)
                continue
            try:
                if file_path.stat().st_size > MAX_FILE_BYTES:
                    raise ValueError("JSON file exceeds 1MB")
                document = json.loads(file_path.read_text(encoding="utf-8"))
                if not isinstance(document, dict):
                    continue
                errors = self.validator.validate(document, seen_ids)
                if errors:
                    raise ValueError("; ".join(errors))
                spec = json_doc_to_spec(document)
            except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
                logger.warning("Skipping invalid component JSON %s: %s", file_path, exc)
                continue
            specs.append(spec)
            seen_ids.add(spec.component_id)
        return specs

    @staticmethod
    def _is_allowed_file(root: Path, file_path: Path) -> bool:
        try:
            relative = file_path.resolve().relative_to(root.resolve())
        except ValueError:
            return False
        return relative.suffix.lower() == ".json" and ".." not in relative.parts


def load_components(path: Path | str = "data/components") -> list[ComponentSpec]:
    """Load all valid component definitions beneath ``path``."""
    return ComponentLoader().load(path)