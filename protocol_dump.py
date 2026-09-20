#!/usr/bin/env python3
"""
protocol_dump.py — full source dump of the files that matter for C firmware.

backend_inventory.py gives you signatures and docstrings, which is enough to
navigate the codebase but NOT enough to write byte-accurate C against JSON
field names and literal values. This script dumps the FULL literal source of
just the protocol-critical files, concatenated into one file — paste that
one file back into chat and we can design the C framing/dispatch layer
against the real wire format instead of guessing.

Covers, if present:
  - engine/protocol/**               (message envelope, MessageType, SYNC_*)
  - engine/discovery/handshake.py    (HELLO handshake)
  - engine/hybrid/device_agent.py    (the live hhip_agent wire protocol)
  - engine/hybrid/hybrid_router.py   (GPIO event <-> wire routing)
  - engine/hybrid/pin_mapper.py      (virtual<->physical pin mapping)
  - firmware/**/*.ino, *.c, *.cpp, *.h  (every existing C/C++ reference impl)

Usage:
    python protocol_dump.py                      # writes PROTOCOL_DUMP.md here
    python protocol_dump.py --root path/to/backend
    python protocol_dump.py --out PROTOCOL_DUMP.md
"""

from __future__ import annotations

import argparse
from pathlib import Path

# Specific files (relative to root) whose full source matters for the wire
# protocol. Order matters: envelope/message format first, then handshake,
# then the live agent protocol, then routing, then existing C references.
TARGET_FILES = [
    "engine/protocol/__init__.py",
    "engine/protocol/messages.py",
    "engine/protocol/reliability.py",
    "engine/protocol/sync_wire.py",
    "engine/protocol/correction.py",
    "engine/protocol/correction_wire.py",
    "engine/discovery/handshake.py",
    "engine/discovery/identify.py",
    "engine/hybrid/device_agent.py",
    "engine/hybrid/hybrid_router.py",
    "engine/hybrid/pin_mapper.py",
    "engine/hybrid/physical_device.py",
    "engine/communication/serial_adapter.py",
]

FIRMWARE_EXTS = {".ino", ".c", ".cpp", ".h", ".hpp"}


def find_root(given: Path) -> Path:
    if (given / "engine").exists() and (given / "firmware").exists():
        return given
    if (given / "hhip" / "engine").exists():
        return given / "hhip"
    return given


def dump_file(path: Path, rel: Path, lines: list[str]) -> None:
    lang = "python" if path.suffix == ".py" else "cpp"
    lines.append(f"## `{rel}`\n")
    lines.append(f"```{lang}")
    try:
        lines.append(path.read_text(encoding="utf-8", errors="replace").rstrip("\n"))
    except OSError as exc:
        lines.append(f"<< could not read: {exc} >>")
    lines.append("```\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default=".", help="Path to the backend root (default: current dir)")
    parser.add_argument("--out", default="PROTOCOL_DUMP.md", help="Output file")
    args = parser.parse_args()

    root = find_root(Path(args.root).resolve())
    if not root.exists():
        print(f"Path does not exist: {root}")
        raise SystemExit(1)

    lines: list[str] = [f"# Protocol source dump — from `{root}`\n"]

    lines.append("## 1. Protocol / handshake / agent source (Python)\n")
    found_py = 0
    missing_py = []
    for rel_str in TARGET_FILES:
        rel = Path(rel_str)
        path = root / rel
        if path.exists():
            dump_file(path, rel, lines)
            found_py += 1
        else:
            missing_py.append(rel_str)

    if missing_py:
        lines.append("### Not found (skipped)\n")
        for m in missing_py:
            lines.append(f"- `{m}`")
        lines.append("")

    lines.append("## 2. Existing firmware source (C/C++)\n")
    fw_dir = root / "firmware"
    found_fw = 0
    if fw_dir.exists():
        for path in sorted(fw_dir.rglob("*")):
            if path.suffix.lower() in FIRMWARE_EXTS:
                dump_file(path, path.relative_to(root), lines)
                found_fw += 1
    else:
        lines.append("_No firmware/ directory found._\n")

    out_path = root / args.out
    try:
        out_path.write_text("\n".join(lines), encoding="utf-8")
    except OSError as exc:
        print(f"Could not write {out_path}: {exc}")
        raise SystemExit(1)

    print(f"Wrote {out_path}")
    print(f"  protocol/handshake/agent files found: {found_py} (missing: {len(missing_py)})")
    print(f"  firmware source files found: {found_fw}")
    size_kb = out_path.stat().st_size / 1024
    print(f"  output size: {size_kb:.1f} KB")
    if size_kb > 400:
        print("  (large — if pasting into chat is awkward, upload the file instead)")


if __name__ == "__main__":
    main()
