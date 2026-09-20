#!/usr/bin/env python3
"""
node_reconciliation_dump.py — full source of the physical<->virtual
node reconciliation layer.

Scope: exactly the files that own how a HardwareNode (physical digital
twin) and a CanvasNode (workspace canvas node) get created, linked,
and torn down as devices connect/disconnect/reconnect. Nothing else —
this is deliberately narrow so the output is small enough to review
in one pass and paste back in one message.

Usage:
    python node_reconciliation_dump.py
    python node_reconciliation_dump.py --root path/to/backend
    python node_reconciliation_dump.py --out RECONCILIATION_DUMP.md
"""

from __future__ import annotations

import argparse
from pathlib import Path

TARGET_FILES = [
    # The two node models being reconciled, and the service that does it.
    "engine/hardware_nodes/__init__.py",
    "engine/hardware_nodes/hardware_node.py",
    "engine/hardware_nodes/hardware_node_factory.py",
    "engine/hardware_nodes/pin_layout.py",
    "engine/hardware_nodes/workspace_sync.py",
    "engine/hardware_nodes/discovery_listener.py",
    # The canvas-native node model + the workspace service that owns it.
    "engine/lab_workspace/models.py",
    "engine/lab_workspace/service.py",
    "engine/lab_workspace/storage.py",
    # What actually triggers connect/disconnect in the first place.
    "engine/discovery/service.py",
    "engine/hybrid/registry.py",
    # The API surface that exposes reconciliation to the frontend.
    "api/services/workspace_hardware_service.py",
    "api/routes/workspace_hardware.py",
]


def find_root(given: Path) -> Path:
    if (given / "engine").exists():
        return given
    if (given / "hhip" / "engine").exists():
        return given / "hhip"
    return given


def dump_file(path: Path, rel: Path, lines: list[str]) -> None:
    lines.append(f"## `{rel}`\n")
    lines.append("```python")
    try:
        lines.append(path.read_text(encoding="utf-8", errors="replace").rstrip("\n"))
    except OSError as exc:
        lines.append(f"<< could not read: {exc} >>")
    lines.append("```\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default=".", help="Path to the backend root (default: current dir)")
    parser.add_argument("--out", default="RECONCILIATION_DUMP.md", help="Output file")
    args = parser.parse_args()

    root = find_root(Path(args.root).resolve())
    if not root.exists():
        print(f"Path does not exist: {root}")
        raise SystemExit(1)

    lines: list[str] = [f"# Node reconciliation source dump — from `{root}`\n"]

    found = 0
    missing: list[str] = []
    for rel_str in TARGET_FILES:
        rel = Path(rel_str)
        path = root / rel
        if path.exists():
            dump_file(path, rel, lines)
            found += 1
        else:
            missing.append(rel_str)

    if missing:
        lines.append("## Not found (skipped)\n")
        for m in missing:
            lines.append(f"- `{m}`")
        lines.append("")

    out_path = root / args.out
    try:
        out_path.write_text("\n".join(lines), encoding="utf-8")
    except OSError as exc:
        print(f"Could not write {out_path}: {exc}")
        raise SystemExit(1)

    print(f"Wrote {out_path}")
    print(f"  files found: {found} (missing: {len(missing)})")
    size_kb = out_path.stat().st_size / 1024
    print(f"  output size: {size_kb:.1f} KB")
    if size_kb > 400:
        print("  (large — if pasting into chat is awkward, upload the file instead)")


if __name__ == "__main__":
    main()
