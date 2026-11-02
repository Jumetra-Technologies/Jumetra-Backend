#!/usr/bin/env python3
"""Write the API's OpenAPI document to docs/openapi.json.

    python scripts/export_openapi.py            write it
    python scripts/export_openapi.py --check    exit 1 if docs/openapi.json is out of date

tests/test_openapi.py runs the check, so a pull request that changes a route
must also commit the regenerated file. The desktop app and the website build
against this file before the endpoints are live (sprint plan, working agreement).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "openapi.json"


def document() -> dict:
    os.environ.setdefault("HHIP_DISABLE_DISCOVERY", "1")
    sys.path.insert(0, str(ROOT))
    from api.main import create_app

    spec = create_app().openapi()
    spec.setdefault("info", {})["title"] = "Kiungo API"
    return spec


def render(spec: dict) -> str:
    return json.dumps(spec, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv: list[str]) -> int:
    text = render(document())
    if "--check" in argv:
        current = OUT.read_text(encoding="utf-8") if OUT.is_file() else ""
        if current != text:
            print(f"{OUT.relative_to(ROOT)} is out of date. Run: python scripts/export_openapi.py", file=sys.stderr)
            return 1
        print("docs/openapi.json is current")
        return 0
    OUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} ({len(json.loads(text)['paths'])} paths)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
