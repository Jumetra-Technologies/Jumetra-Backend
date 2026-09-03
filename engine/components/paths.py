"""Resolve absolute path to data/components catalog directory."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("hhip.components")


def project_root() -> Path:
    """Absolute HHIP package root (directory containing ``data/`` and ``engine/``)."""
    # engine/components/paths.py → parents[0]=components, [1]=engine, [2]=hhip
    return Path(__file__).resolve().parents[2]


def resolve_components_dir(explicit: Optional[Path | str] = None) -> Path:
    """
    Resolve ``data/components`` using absolute paths.

    Candidates (first existing wins):
    1. Explicit path
    2. ``{hhip_package}/data/components``
    3. ``{repo_root}/data/components`` (parent of hhip package)
    4. ``{cwd}/data/components`` and ``{cwd}/hhip/data/components``
    """
    if explicit is not None:
        path = Path(explicit).expanduser().resolve()
        if path.is_dir():
            return path

    root = project_root()
    candidates = [
        root / "data" / "components",
        root.parent / "data" / "components",
        Path.cwd() / "data" / "components",
        Path.cwd() / "hhip" / "data" / "components",
    ]
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved.is_dir() and any(resolved.glob("*.json")):
            return resolved

    # Prefer package-local path even if empty (stable default for logging)
    fallback = (root / "data" / "components").resolve()
    logger.warning("components dir not found with JSON; using fallback %s", fallback)
    return fallback
