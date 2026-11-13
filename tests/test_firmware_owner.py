"""Firmware projects belong to the account that made them (S2, 12 Nov 2026)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from auth import firebase


def _claims(uid):
    return {"uid": uid, "sub": uid, "email": f"{uid}@example.test", "email_verified": True, "name": uid, "firebase": {"sign_in_provider": "google.com", "identities": {"google.com": [f"g-{uid}"]}}}


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("HHIP_REQUIRE_AUTH", "true")
    monkeypatch.setenv("HHIP_DISABLE_DISCOVERY", "1")
    monkeypatch.setenv("HHIP_FIRMWARE_DRY_RUN", "1")
    monkeypatch.setattr(firebase, "verify_id_token", lambda token: _claims(token))
    return create_app(data_dir=tmp_path)


def _sign_in(c, uid):
    session = c.post("/auth/google", json={"id_token": uid}).json()
    c.cookies.clear()
    c.headers["Authorization"] = f"Bearer {session['access_token']}"
    return c


def test_reads_need_sign_in(app):
    with TestClient(app) as anon:
        assert anon.get("/firmware/projects").status_code == 401
        assert anon.get("/firmware/projects/FW_0123456789").status_code == 401
        assert anon.get("/firmware/logs").status_code == 401
        assert anon.get("/firmware/serial").status_code == 401
        # Templates and toolchains describe the product, not anyone's work.
        assert anon.get("/firmware/templates").status_code == 200
        assert anon.get("/firmware/toolchains").status_code == 200


def test_one_account_never_sees_or_changes_anothers_project(app):
    with TestClient(app) as ada_c, TestClient(app) as bob_c:
        ada = _sign_in(ada_c, "ada")
        bob = _sign_in(bob_c, "bob")
        pid = ada.post("/firmware/projects", json={"name": "Ada's blink", "board_type": "arduino-uno", "template_id": "blink"}).json()["project_id"]

        assert [p["project_id"] for p in ada.get("/firmware/projects").json()["projects"]] == [pid]
        assert ada.get(f"/firmware/projects/{pid}").status_code == 200

        assert bob.get("/firmware/projects").json() == {"projects": [], "count": 0}
        assert bob.get(f"/firmware/projects/{pid}").status_code == 404
        assert bob.put(f"/firmware/projects/{pid}/files", json={"path": "src/main.ino", "content": "// bob"}).status_code == 404
        assert bob.post("/firmware/build", json={"project_id": pid}).status_code == 404
        assert bob.post("/firmware/build/jobs", json={"project_id": pid}).status_code == 404
        assert bob.post("/firmware/upload", json={"project_id": pid}).status_code == 404

        # Ada's code is untouched, and she can still build it.
        files = {f["path"]: f["content"] for f in ada.get(f"/firmware/projects/{pid}").json()["files"]}
        assert "// bob" not in files.get("src/main.ino", "")
        assert ada.post("/firmware/build", json={"project_id": pid}).status_code == 200
