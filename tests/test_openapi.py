"""docs/openapi.json must match the app. Regenerate with scripts/export_openapi.py."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import export_openapi  # noqa: E402


def test_openapi_file_is_current():
    expected = export_openapi.render(export_openapi.document())
    actual = (ROOT / "docs" / "openapi.json").read_text(encoding="utf-8")
    assert actual == expected, "docs/openapi.json is out of date. Run: python scripts/export_openapi.py"


def test_openapi_lists_the_desktop_sign_in_routes():
    spec = json.loads((ROOT / "docs" / "openapi.json").read_text(encoding="utf-8"))
    for path, method in [
        ("/auth/desktop/codes", "post"),
        ("/auth/desktop/codes/{code_id}", "get"),
        ("/auth/desktop/codes/{code_id}/approve", "post"),
        ("/auth/desktop/token", "post"),
        ("/auth/desktop/refresh", "post"),
        ("/auth/desktop/logout", "post"),
        ("/auth/me/devices", "get"),
        ("/auth/me/devices/{device_id}", "delete"),
        ("/auth/github", "post"),
        ("/auth/me/lab-sessions/{session_id}", "put"),
    ]:
        assert method in spec["paths"][path], f"{method.upper()} {path} missing from docs/openapi.json"


def test_no_duplicate_operation_ids():
    spec = json.loads((ROOT / "docs" / "openapi.json").read_text(encoding="utf-8"))
    seen: dict[str, str] = {}
    for path, methods in spec["paths"].items():
        for method, op in methods.items():
            oid = op.get("operationId")
            assert oid not in seen, f"operationId {oid} is used by {seen.get(oid)} and {method.upper()} {path}"
            seen[oid] = f"{method.upper()} {path}"
