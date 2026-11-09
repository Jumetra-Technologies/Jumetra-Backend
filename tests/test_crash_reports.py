"""Crash reports only with consent: the answer is kept per account, reports are refused against a no, and nothing is kept past 90 days."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from api.main import create_app
from auth import firebase
from database.models import CrashReport


def _claims(uid="uid-1"):
    return {"uid": uid, "sub": uid, "email": f"{uid}@example.test", "email_verified": True, "name": "Ada", "firebase": {"sign_in_provider": "google.com", "identities": {"google.com": [f"g-{uid}"]}}}


@pytest.fixture
def app(tmp_path, monkeypatch):
    # Production settings: writes need a session and, for cookies, a website origin.
    monkeypatch.setenv("HHIP_REQUIRE_AUTH", "true")
    monkeypatch.setenv("HHIP_DISABLE_DISCOVERY", "1")
    monkeypatch.setattr(firebase, "verify_id_token", lambda token: _claims())
    return create_app(data_dir=tmp_path)


@pytest.fixture
def desktop(app):
    """The desktop app: a bearer token, no cookies, no Origin header."""
    with TestClient(app) as c:
        session = c.post("/auth/google", json={"id_token": "t"}).json()
        c.cookies.clear()
        c.headers["Authorization"] = f"Bearer {session['access_token']}"
        yield c


@pytest.fixture
def anonymous(app):
    with TestClient(app, cookies={}) as c:
        yield c


def report(**over):
    return {
        "consent": True,
        "install_id": "inst-4f9a2c7e",
        "app_version": "0.6.0",
        "platform": "windows",
        "arch": "x64",
        "process": "renderer",
        "message": "TypeError: Cannot read properties of undefined (reading 'nodes')",
        "stack": "at LabCanvas (index.js:1:2)",
        "occurred_at": "2026-11-02T10:00:00Z",
        **over,
    }


def test_not_asked_yet_then_yes_then_no(desktop):
    assert desktop.get("/auth/me/consents").json() == {"crash_reports": None, "usage": None, "decided_at": None, "decided_in": None}
    yes = desktop.put("/auth/me/consents", json={"crash_reports": True, "decided_in": "desktop 0.6.0"})
    assert yes.status_code == 200, yes.text
    assert yes.json()["crash_reports"] is True
    assert desktop.get("/auth/me/consents").json()["decided_in"] == "desktop 0.6.0"
    assert desktop.put("/auth/me/consents", json={"crash_reports": False}).json()["crash_reports"] is False


def test_signed_out_reports_are_accepted_with_consent(anonymous, app):
    response = anonymous.post("/crash-reports", json=report())
    assert response.status_code == 202, response.text
    with app.state.db_factory() as session:
        saved = session.execute(select(CrashReport)).scalars().one()
        assert saved.user_id is None
        assert saved.install_id == "inst-4f9a2c7e"


def test_a_report_without_consent_is_refused(anonymous):
    assert anonymous.post("/crash-reports", json=report(consent=False)).status_code == 422
    body = report()
    del body["consent"]
    assert anonymous.post("/crash-reports", json=body).status_code == 422


def test_an_account_that_said_no_gets_nothing_sent_and_loses_what_was(desktop, app):
    desktop.put("/auth/me/consents", json={"crash_reports": True})
    assert desktop.post("/crash-reports", json=report()).status_code == 202
    desktop.put("/auth/me/consents", json={"crash_reports": False})
    assert desktop.post("/crash-reports", json=report()).status_code == 403
    with app.state.db_factory() as session:
        assert session.execute(select(CrashReport)).scalars().all() == []


def test_reports_older_than_90_days_are_removed(anonymous, app):
    anonymous.post("/crash-reports", json=report())
    with app.state.db_factory() as session:
        old = session.execute(select(CrashReport)).scalars().one()
        old.received_at = datetime.now(timezone.utc) - timedelta(days=91)
        session.commit()
    anonymous.post("/crash-reports", json=report(message="Another"))
    with app.state.db_factory() as session:
        assert [r.message for r in session.execute(select(CrashReport)).scalars()] == ["Another"]


@pytest.mark.parametrize(
    "over",
    [
        {"install_id": "../etc"},
        {"platform": "beos"},
        {"message": ""},
        {"message": "x" * 2001},
        {"stack": "x" * 32_001},
    ],
)
def test_bad_reports_are_refused(anonymous, over):
    assert anonymous.post("/crash-reports", json=report(**over)).status_code == 422


def test_cookie_writes_still_need_a_website_origin(app):
    # The bearer exemption doesn't weaken the CSRF check for browsers.
    with TestClient(app) as c:
        c.post("/auth/google", json={"id_token": "t"})
        assert c.put("/auth/me/consents", json={"crash_reports": True}).status_code == 403
        assert c.put("/auth/me/consents", json={"crash_reports": True}, headers={"Origin": "https://evil.example"}).status_code == 403


def test_a_bearer_write_still_needs_a_valid_session(anonymous):
    assert anonymous.put("/auth/me/consents", json={"crash_reports": True}, headers={"Authorization": "Bearer nonsense"}).status_code == 401
