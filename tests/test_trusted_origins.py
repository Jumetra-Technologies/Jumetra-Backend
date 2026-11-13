"""Trusted origins, the session middleware and the admin password (audit 13 Nov 2026: API-005, API-007, N-4)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.services import admin_auth
from auth import firebase
from auth.tokens import ACCESS_COOKIE


def _claims(uid: str) -> dict:
    return {
        "uid": uid,
        "sub": uid,
        "email": f"{uid}@example.test",
        "email_verified": True,
        "name": uid,
        "firebase": {"sign_in_provider": "google.com", "identities": {"google.com": [f"g-{uid}"]}},
    }


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("HHIP_REQUIRE_AUTH", "true")
    monkeypatch.setenv("HHIP_DISABLE_DISCOVERY", "1")
    monkeypatch.delenv("HHIP_CORS_ORIGINS", raising=False)
    monkeypatch.delenv("HHIP_ALLOW_LAN_ORIGINS", raising=False)
    monkeypatch.setattr(firebase, "verify_id_token", lambda token: _claims(token))
    return create_app(data_dir=tmp_path)


SITE = "https://kiungo-labs-technologies.vercel.app"
PROJECT = {"name": "Rover", "description": "", "objectives": "", "contributors": "", "category": "robotics", "hardware": [], "teammates": []}


def browser(app) -> TestClient:
    """A browser signed in with cookies only (no bearer token), as cookie sessions work."""
    c = TestClient(app)
    c.__enter__()
    assert c.post("/auth/google", json={"id_token": "ada"}, headers={"Origin": SITE}).status_code == 200
    return c


@pytest.mark.parametrize("origin", ["https://attacker.web.app", "https://x.firebaseapp.com", "https://x.hosted.app", "https://x.run.app", "http://192.168.1.20:3000"])
def test_hosting_wildcards_are_not_trusted(app, origin):
    c = browser(app)
    try:
        preflight = c.options("/auth/me/projects", headers={"Origin": origin, "Access-Control-Request-Method": "POST"})
        assert preflight.headers.get("access-control-allow-origin") is None
        # The cookies alone don't make a write from that site.
        assert c.post("/auth/me/projects", json=PROJECT, headers={"Origin": origin}).status_code == 403
    finally:
        c.__exit__(None, None, None)


def test_the_listed_sites_and_local_dev_are_trusted(app):
    c = browser(app)
    try:
        for origin in (SITE, "http://localhost:3000", "http://127.0.0.1:3001"):
            preflight = c.options("/auth/me/projects", headers={"Origin": origin, "Access-Control-Request-Method": "POST"})
            assert preflight.headers.get("access-control-allow-origin") == origin
        assert c.post("/auth/me/projects", json=PROJECT, headers={"Origin": SITE}).status_code in (200, 201)
    finally:
        c.__exit__(None, None, None)


def test_lan_addresses_need_switching_on(tmp_path, monkeypatch):
    monkeypatch.setenv("HHIP_ALLOW_LAN_ORIGINS", "1")
    monkeypatch.setenv("HHIP_DISABLE_DISCOVERY", "1")
    with TestClient(create_app(data_dir=tmp_path)) as c:
        preflight = c.options("/health", headers={"Origin": "http://192.168.1.20:3000", "Access-Control-Request-Method": "GET"})
        assert preflight.headers.get("access-control-allow-origin") == "http://192.168.1.20:3000"


def test_a_forwarded_origin_header_is_not_believed(app):
    c = browser(app)
    try:
        r = c.post("/auth/me/projects", json=PROJECT, headers={"Origin": "https://evil.example", "X-Forwarded-Origin": SITE})
        assert r.status_code == 403
        beat = c.post("/telemetry/heartbeat", json={"visitor": "visitor-12345678"}, headers={"Origin": "https://evil.example", "X-Forwarded-Origin": SITE})
        assert beat.status_code == 403
    finally:
        c.__exit__(None, None, None)


def test_the_first_write_after_the_access_token_runs_out_works(app):
    c = browser(app)
    try:
        # The 15-minute access cookie has expired (here: replaced); the refresh cookie is good.
        c.cookies.set(ACCESS_COOKIE, "expired")
        r = c.post("/auth/me/projects", json=PROJECT, headers={"Origin": SITE})
        assert r.status_code in (200, 201), r.text
        assert ACCESS_COOKIE in r.headers.get("set-cookie", "")
        # And the session goes on with the rotated cookies.
        assert c.get("/auth/me").status_code == 200
    finally:
        c.__exit__(None, None, None)


def test_a_deployed_server_refuses_the_built_in_admin_password(app, monkeypatch):
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.delenv("HHIP_ADMIN_PASSWORD_HASH", raising=False)
    with TestClient(app) as c:
        r = c.post("/admin/session", json={"password": "anything"})
        assert r.status_code == 503 and "HHIP_ADMIN_PASSWORD_HASH" in r.json()["detail"]

    monkeypatch.setenv("HHIP_ADMIN_PASSWORD_HASH", admin_auth.hash_password("correct horse", n=1024))
    with TestClient(app) as c:
        assert c.post("/admin/session", json={"password": "wrong"}).status_code == 401
        assert c.post("/admin/session", json={"password": "correct horse"}).status_code == 200


def test_local_development_keeps_the_built_in_password(monkeypatch):
    for name in ("RENDER", "K_SERVICE", "HHIP_ENV", "HHIP_ADMIN_PASSWORD_HASH"):
        monkeypatch.delenv(name, raising=False)
    assert admin_auth.password_hash() == admin_auth.DEFAULT_HASH
