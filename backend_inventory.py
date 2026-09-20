#!/usr/bin/env python3
"""
backend_inventory.py — map the HHIP backend for someone about to write firmware.

Walks the Python backend (engine/, api/) plus firmware/ sketches, using the
`ast` module to read real classes, functions and docstrings without ever
importing or executing your code (safe on a half-finished tree). Produces:

  1. A package-by-package map of engine/ and api/ (classes, functions,
     one-line docstrings).
  2. A dedicated "Protocol & Communication" section — the modules a C
     firmware needs to match wire-format with.
  3. An inventory of existing firmware/*.ino sketches (line counts, so you
     know what already exists vs. what you're adding).
  4. A REST endpoint map extracted from api/routes/*.py (method + path),
     so you know what the dashboard/tooling expects from the backend.

Usage (from anywhere; point --root at your hhip/ folder if not run from it):

    python backend_inventory.py
    python backend_inventory.py --root path/to/hhip
    python backend_inventory.py --out BACKEND_MAP.md

No third-party dependencies — stdlib only.
"""

from __future__ import annotations

import argparse
import ast
import re
from dataclasses import dataclass, field
from pathlib import Path

SKIP_DIRS = {
    "__pycache__", ".venv", "venv", "node_modules", ".git",
    "dashboard", ".next", "dist", "build",
}

# Modules a firmware author most needs to read closely: these define the
# wire format / framing / device handshake a C implementation must match.
PROTOCOL_HINT_DIRS = {"protocol", "communication", "routing", "events"}


@dataclass
class FuncInfo:
    name: str
    args: list[str]
    doc: str | None
    is_async: bool


@dataclass
class ClassInfo:
    name: str
    doc: str | None
    bases: list[str]
    methods: list[FuncInfo] = field(default_factory=list)


@dataclass
class ModuleInfo:
    path: Path
    doc: str | None
    classes: list[ClassInfo] = field(default_factory=list)
    functions: list[FuncInfo] = field(default_factory=list)
    line_count: int = 0


def first_line(doc: str | None) -> str | None:
    if not doc:
        return None
    return doc.strip().splitlines()[0].strip()


def func_info(node: ast.FunctionDef | ast.AsyncFunctionDef) -> FuncInfo:
    args = [a.arg for a in node.args.args if a.arg != "self"]
    return FuncInfo(
        name=node.name,
        args=args,
        doc=first_line(ast.get_docstring(node)),
        is_async=isinstance(node, ast.AsyncFunctionDef),
    )


def parse_module(path: Path) -> ModuleInfo | None:
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source, filename=str(path))
    except (SyntaxError, UnicodeDecodeError):
        return None

    mod = ModuleInfo(path=path, doc=first_line(ast.get_docstring(tree)), line_count=source.count("\n") + 1)

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            cls = ClassInfo(
                name=node.name,
                doc=first_line(ast.get_docstring(node)),
                bases=[ast.unparse(b) for b in node.bases] if hasattr(ast, "unparse") else [],
            )
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if item.name.startswith("_") and item.name != "__init__":
                        continue
                    cls.methods.append(func_info(item))
            mod.classes.append(cls)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("_"):
                continue
            mod.functions.append(func_info(node))

    return mod


def walk_python(root: Path) -> list[ModuleInfo]:
    modules = []
    for path in sorted(root.rglob("*.py")):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.name.startswith("test_"):
            continue
        info = parse_module(path)
        if info:
            modules.append(info)
    return modules


def render_func(f: FuncInfo, indent: str) -> str:
    prefix = "async def" if f.is_async else "def"
    sig = f"{prefix} {f.name}({', '.join(f.args)})"
    line = f"{indent}- `{sig}`"
    if f.doc:
        line += f" — {f.doc}"
    return line


def render_module(mod: ModuleInfo, root: Path) -> list[str]:
    rel = mod.path.relative_to(root)
    lines = [f"### `{rel}` ({mod.line_count} lines)"]
    if mod.doc:
        lines.append(f"> {mod.doc}")
    if not mod.classes and not mod.functions:
        lines.append("_(no top-level classes/functions — constants/config only)_")
    for cls in mod.classes:
        bases = f"({', '.join(cls.bases)})" if cls.bases else ""
        header = f"- **class `{cls.name}{bases}`**"
        if cls.doc:
            header += f" — {cls.doc}"
        lines.append(header)
        for m in cls.methods:
            lines.append(render_func(m, "  "))
    for fn in mod.functions:
        lines.append(render_func(fn, ""))
    lines.append("")
    return lines


def group_by_package(modules: list[ModuleInfo], root: Path) -> dict[str, list[ModuleInfo]]:
    groups: dict[str, list[ModuleInfo]] = {}
    for mod in modules:
        rel = mod.path.relative_to(root)
        pkg = str(rel.parent) if rel.parent != Path(".") else "(root)"
        groups.setdefault(pkg, []).append(mod)
    return groups


ROUTE_RE = re.compile(
    r'@\w*router\.(get|post|patch|put|delete)\(\s*["\']([^"\']+)["\']', re.IGNORECASE
)


def extract_routes(routes_dir: Path) -> dict[str, list[tuple[str, str]]]:
    result: dict[str, list[tuple[str, str]]] = {}
    if not routes_dir.exists():
        return result
    for path in sorted(routes_dir.glob("*.py")):
        text = path.read_text(encoding="utf-8", errors="replace")
        hits = ROUTE_RE.findall(text)
        if hits:
            result[path.name] = [(m.upper(), p) for m, p in hits]
    return result


def inventory_firmware(firmware_dir: Path) -> list[tuple[Path, int]]:
    if not firmware_dir.exists():
        return []
    out = []
    for path in sorted(firmware_dir.rglob("*")):
        if path.suffix.lower() in {".ino", ".c", ".cpp", ".h", ".hpp"}:
            try:
                lines = path.read_text(encoding="utf-8", errors="replace").count("\n") + 1
            except OSError:
                lines = 0
            out.append((path, lines))
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default=".", help="Path to the hhip/ backend root (default: current dir)")
    parser.add_argument("--out", default="BACKEND_MAP.md", help="Output Markdown file")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    if not (root / "engine").exists() and not (root / "api").exists():
        # Maybe they ran it from the repo root instead of hhip/
        if (root / "hhip" / "engine").exists():
            root = root / "hhip"

    engine_dir = root / "engine"
    api_dir = root / "api"
    routes_dir = api_dir / "routes"
    firmware_dir = root / "firmware"

    lines: list[str] = []
    lines.append(f"# Backend map — generated from `{root}`\n")

    # --- 1. Protocol & communication (read this first) ---
    proto_modules = [
        m for m in walk_python(engine_dir)
        if any(part in PROTOCOL_HINT_DIRS for part in m.path.relative_to(root).parts)
    ]
    lines.append("## 1. Protocol & Communication layer — read this before writing firmware\n")
    lines.append(
        "These modules define the wire format, framing and handshake the Python side "
        "expects. A C firmware talking to this backend (serial/WiFi) needs to match "
        "whatever these encode/decode.\n"
    )
    if proto_modules:
        for mod in proto_modules:
            lines.extend(render_module(mod, root))
    else:
        lines.append("_No modules found under engine/{protocol,communication,routing,events} — check --root._\n")

    # --- 2. Existing firmware sketches ---
    lines.append("## 2. Existing firmware (C/C++) — what's already there\n")
    fw_files = inventory_firmware(firmware_dir)
    if fw_files:
        for path, n in fw_files:
            lines.append(f"- `{path.relative_to(root)}` — {n} lines")
    else:
        lines.append("_No firmware/ directory found, or it's empty._")
    lines.append("")

    # --- 3. REST API surface ---
    lines.append("## 3. REST API surface (api/routes/)\n")
    routes = extract_routes(routes_dir)
    if routes:
        for fname, hits in routes.items():
            lines.append(f"**{fname}**")
            for method, path in hits:
                lines.append(f"- `{method} {path}`")
            lines.append("")
    else:
        lines.append("_No routes found — check --root points at hhip/._\n")

    # --- 4. Everything else in engine/, grouped by sub-package ---
    lines.append("## 4. Engine — full module map\n")
    all_engine = walk_python(engine_dir)
    groups = group_by_package(all_engine, root)
    for pkg in sorted(groups):
        lines.append(f"### 📦 {pkg}\n")
        for mod in groups[pkg]:
            lines.extend(render_module(mod, root))

    # --- 5. API layer (non-route modules: main.py, dependencies, etc.) ---
    lines.append("## 5. API — app setup & non-route modules\n")
    api_modules = [m for m in walk_python(api_dir) if "routes" not in m.path.parts]
    for mod in api_modules:
        lines.extend(render_module(mod, root))

    out_path = root / args.out
    out_path.write_text("\n".join(lines), encoding="utf-8")

    print(f"Wrote {out_path}")
    print(f"  engine/: {len(all_engine)} modules")
    print(f"  api/:    {len(api_modules)} non-route modules, {sum(len(h) for h in routes.values())} routes across {len(routes)} route files")
    print(f"  firmware/: {len(fw_files)} C/C++ files")
    print(f"  protocol/communication modules highlighted: {len(proto_modules)}")


if __name__ == "__main__":
    main()
