"""Deleting an account deletes everything under it (audit 13 Nov 2026: API-006, API-024).

The check walks every table with a ``user_id`` or ``owner_id`` column, so a table added later
that delete_user forgets fails this test instead of keeping someone's data.
"""

from __future__ import annotations

import base64
import hashlib
from datetime import date, datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from api.db.base import Base
from api.main import create_app
from auth import firebase
from database.models import ActivityDaily, ActivityPresence, CrashReport


def _claims(uid: str) -> dict:
    return {"uid": uid, "sub": uid, "email": f"{uid}@example.test", "email_verified": True, "name": uid, "firebase": {"sign_in_provider": "google.com", "identities": {"google.com": [f"g-{uid}"]}}}


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("HHIP_REQUIRE_AUTH", "true")
    monkeypatch.setenv("HHIP_DISABLE_DISCOVERY", "1")
    monkeypatch.setattr(firebase, "verify_id_token", lambda token: _claims(token))
    return create_app(data_dir=tmp_path)


def _sign_in(c: TestClient, uid: str) -> str:
    session = c.post("/auth/google", json={"id_token": uid}).json()
    c.headers["Authorization"] = f"Bearer {session['access_token']}"
    return session["id"]


def _owner_columns():
    for table in Base.metadata.sorted_tables:
        for name in ("user_id", "owner_id"):
            if name in table.c:
                yield table, table.c[name]


def _rows_of(app, user_id: str) -> dict[str, int]:
    with app.state.db_factory() as session:
        counts = {f"{t.name}.{c.name}": session.scalar(select(func.count()).select_from(t).where(c == user_id)) for t, c in _owner_columns()}
    return {k: v for k, v in counts.items() if v}


def _fill(app, c: TestClient, user_id: str) -> None:
    """Something in every place an account keeps data."""
    project = c.post("/auth/me/projects", json={"name": "Rover", "description": "", "objectives": "", "contributors": "", "category": "robotics", "hardware": [], "teammates": []}).json()
    c.post(f"/auth/me/projects/{project['id']}/experiments", json={"title": "Lap", "objective": "", "hardware": [], "procedure": "", "observations": "", "results": "", "notes": ""})
    c.put("/auth/me/lab-sessions/s1", json={"id": "s1", "name": "Blink", "updatedAt": "2026-11-13T00:00:00Z", "nodes": [], "wires": []})
    c.put("/auth/me/consents", json={"usage": True, "crash_reports": True})
    data = b"void setup() {}\nvoid loop() {}\n"
    sha = hashlib.sha256(data).hexdigest()
    assert c.post("/auth/me/projects-sync/prj-rover/blobs", json=[{"sha256": sha, "base64": base64.b64encode(data).decode()}]).status_code == 200
    commit = c.put("/auth/me/projects-sync/prj-rover", json={"name": "Rover", "board": "arduino-uno", "device": "LAPTOP", "files": [{"path": "sketch/sketch.ino", "sha256": sha}]}, headers={"If-Match": "*"})
    assert commit.status_code == 200, commit.text
    with app.state.db_factory() as session:
        now = datetime.now(timezone.utc)
        session.add(CrashReport(install_id="inst-1", user_id=user_id, app_version="0.13.9", platform="linux", arch="x64", process="main", message="boom", stack="", occurred_at=now))
        session.add(ActivityPresence(subject=f"u:{user_id}"[:40], user_id=user_id, client="web", page="/", last_seen_at=now))
        session.add(ActivityDaily(subject=f"u:{user_id}"[:40], day=date.today(), user_id=user_id, client="web", seconds=60))
        session.commit()


def test_deleting_the_account_leaves_nothing_of_it(app):
    with TestClient(app) as ada, TestClient(app) as bob:
        ada_id = _sign_in(ada, "ada")
        bob_id = _sign_in(bob, "bob")
        _fill(app, ada, ada_id)
        _fill(app, bob, bob_id)
        before = _rows_of(app, ada_id)
        for table in ("synced_projects", "synced_files", "file_blobs", "project_revisions", "consents", "crash_reports"):
            assert any(k.startswith(table + ".") for k in before), (table, before)

        assert ada.delete("/auth/me").status_code == 204

        assert _rows_of(app, ada_id) == {}
        # Someone else's data is untouched.
        assert _rows_of(app, bob_id)
        assert bob.get("/auth/me/projects-sync").json()


def test_the_delete_answer_clears_both_sign_in_cookies(app):
    with TestClient(app) as c:
        c.post("/auth/google", json={"id_token": "ada"})
        response = c.delete("/auth/me", headers={"Origin": "http://localhost:3000"})
        assert response.status_code == 204
        cookies = response.headers.get_list("set-cookie")
        assert any(v.startswith("hhip_access=") for v in cookies), cookies
        assert any(v.startswith("hhip_refresh=") for v in cookies), cookies
