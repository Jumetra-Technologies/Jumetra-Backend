"""The desktop sign-in flow (jumetra-frontend #62): PKCE codes, approval on the website, exchange, refresh, logout, devices."""

from __future__ import annotations

import base64
import hashlib
import secrets

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from auth import firebase
from database.models import AccessToken, DesktopAuthCode, Device, RefreshToken
from sqlalchemy import select


def _claims(uid="uid-1", email="ada@example.test", name="Ada"):
    return {"uid": uid, "sub": uid, "email": email, "email_verified": True, "name": name, "firebase": {"sign_in_provider": "google.com", "identities": {"google.com": [f"g-{uid}"]}}}


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("HHIP_REQUIRE_AUTH", "false")
    monkeypatch.setenv("HHIP_DISABLE_DISCOVERY", "1")
    monkeypatch.setenv("KIUNGO_WEBSITE_URL", "https://kiungo.test")
    monkeypatch.setattr(firebase, "verify_id_token", lambda token: _claims())
    return create_app(data_dir=tmp_path)


@pytest.fixture
def web(app):
    """A browser signed in on the website."""
    with TestClient(app) as c:
        session = c.post("/auth/google", json={"id_token": "t"}).json()
        c.headers["Authorization"] = f"Bearer {session['access_token']}"
        yield c


@pytest.fixture
def desktop(app):
    """The desktop app: no cookies, no bearer."""
    with TestClient(app, cookies={}) as c:
        yield c


def pkce():
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


DEVICE = {"name": "Brad's ThinkPad", "platform": "linux", "app_version": "0.2.0"}


def start(desktop, challenge=None):
    if challenge is None:
        _, challenge = pkce()
    response = desktop.post("/auth/desktop/codes", json={"code_challenge": challenge, "device": DEVICE})
    assert response.status_code == 201, response.text
    return response.json()


def test_the_whole_flow(desktop, web):
    verifier, challenge = pkce()
    started = start(desktop, challenge)
    assert started["authorize_url"] == f"https://kiungo.test/desktop/sign-in?code_id={started['code_id']}"
    assert started["expires_in"] == 600
    assert desktop.get(f"/auth/desktop/codes/{started['code_id']}").json() == {"status": "pending"}

    details = web.get(f"/auth/desktop/codes/{started['code_id']}/details").json()
    assert details["device"]["name"] == "Brad's ThinkPad" and details["status"] == "pending"

    approved = web.post(f"/auth/desktop/codes/{started['code_id']}/approve").json()
    assert approved["status"] == "approved"
    assert approved["redirect_url"].startswith("kiungo://signin?code=")
    code = approved["redirect_url"].split("code=")[1].split("&")[0]

    tokens = desktop.post("/auth/desktop/token", json={"code": code, "code_verifier": verifier})
    assert tokens.status_code == 200, tokens.text
    body = tokens.json()
    assert body["token_type"] == "Bearer" and body["expires_in"] == 900
    assert body["device"]["name"] == "Brad's ThinkPad" and body["device"]["platform"] == "linux"
    assert body["user"]["email"] == "ada@example.test"

    # The desktop access token works like any other.
    me = desktop.get("/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200 and me.json()["id"] == body["user"]["id"]

    # A code is single-use.
    assert desktop.post("/auth/desktop/token", json={"code": code, "code_verifier": verifier}).status_code == 400

    # Refresh rotates; the old refresh token is spent.
    rotated = desktop.post("/auth/desktop/refresh", json={"refresh_token": body["refresh_token"]})
    assert rotated.status_code == 200
    assert rotated.json()["refresh_token"] != body["refresh_token"]
    assert rotated.json()["device"]["id"] == body["device"]["id"]

    # Replaying the spent token ends the device's sessions.
    replay = desktop.post("/auth/desktop/refresh", json={"refresh_token": body["refresh_token"]})
    assert replay.status_code == 401 and "used somewhere else" in replay.json()["detail"]
    assert desktop.post("/auth/desktop/refresh", json={"refresh_token": rotated.json()["refresh_token"]}).status_code == 401
    assert desktop.get("/auth/me", headers={"Authorization": f"Bearer {rotated.json()['access_token']}"}).status_code == 401


def test_polling_gets_the_code_once(desktop, web):
    verifier, challenge = pkce()
    started = start(desktop, challenge)
    web.post(f"/auth/desktop/codes/{started['code_id']}/approve")
    polled = desktop.get(f"/auth/desktop/codes/{started['code_id']}").json()
    assert polled["status"] == "approved" and polled["code"]
    assert "code" not in desktop.get(f"/auth/desktop/codes/{started['code_id']}").json()
    assert desktop.post("/auth/desktop/token", json={"code": polled["code"], "code_verifier": verifier}).status_code == 200
    assert desktop.get(f"/auth/desktop/codes/{started['code_id']}").json() == {"status": "exchanged"}


def test_wrong_verifier_burns_the_code(desktop, web):
    _, challenge = pkce()
    other_verifier, _ = pkce()
    started = start(desktop, challenge)
    code = web.post(f"/auth/desktop/codes/{started['code_id']}/approve").json()["redirect_url"].split("code=")[1].split("&")[0]
    assert desktop.post("/auth/desktop/token", json={"code": code, "code_verifier": other_verifier}).status_code == 400
    assert desktop.get(f"/auth/desktop/codes/{started['code_id']}").json() == {"status": "denied"}


def test_approval_needs_a_signed_in_person_and_happens_once(desktop, web):
    started = start(desktop)
    assert desktop.post(f"/auth/desktop/codes/{started['code_id']}/approve").status_code == 401
    assert web.post(f"/auth/desktop/codes/{started['code_id']}/approve").status_code == 200
    assert web.post(f"/auth/desktop/codes/{started['code_id']}/approve").status_code == 409
    assert web.post("/auth/desktop/codes/nope/approve").status_code == 404


def test_deny(desktop, web):
    started = start(desktop)
    assert web.post(f"/auth/desktop/codes/{started['code_id']}/deny").json() == {"status": "denied"}
    assert desktop.get(f"/auth/desktop/codes/{started['code_id']}").json() == {"status": "denied"}


def test_expired_code_cannot_be_approved(app, desktop, web):
    started = start(desktop)
    from datetime import datetime, timedelta, timezone

    with app.state.db_factory() as session:
        row = session.get(DesktopAuthCode, started["code_id"])
        row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        session.commit()
    assert web.post(f"/auth/desktop/codes/{started['code_id']}/approve").status_code == 409
    assert desktop.get(f"/auth/desktop/codes/{started['code_id']}").json() == {"status": "expired"}


def test_bad_requests(desktop):
    _, challenge = pkce()
    assert desktop.post("/auth/desktop/codes", json={"code_challenge": "short", "device": DEVICE}).status_code == 422
    assert desktop.post("/auth/desktop/codes", json={"code_challenge": challenge, "device": dict(DEVICE, platform="amiga")}).status_code == 422
    assert desktop.post("/auth/desktop/codes", json={"code_challenge": challenge, "device": DEVICE, "redirect_uri": "https://evil.test/x"}).status_code == 422
    assert desktop.post("/auth/desktop/codes", json={"code_challenge": challenge, "device": DEVICE, "redirect_uri": "http://127.0.0.1:43123/callback"}).status_code == 201
    assert desktop.post("/auth/desktop/token", json={"code": "nope", "code_verifier": "x" * 43}).status_code == 400
    assert desktop.post("/auth/desktop/refresh", json={"refresh_token": "nope"}).status_code == 401
    assert desktop.get("/auth/desktop/codes/nope").status_code == 404


def test_logout_and_device_list_and_revoke(app, desktop, web):
    verifier, challenge = pkce()
    started = start(desktop, challenge)
    code = web.post(f"/auth/desktop/codes/{started['code_id']}/approve").json()["redirect_url"].split("code=")[1].split("&")[0]
    first = desktop.post("/auth/desktop/token", json={"code": code, "code_verifier": verifier}).json()

    devices = web.get("/auth/me/devices").json()
    assert [d["name"] for d in devices] == ["Brad's ThinkPad"] and devices[0]["revoked"] is False

    assert desktop.post("/auth/desktop/logout", json={"refresh_token": first["refresh_token"]}).json() == {"status": "ok"}
    assert desktop.post("/auth/desktop/refresh", json={"refresh_token": first["refresh_token"]}).status_code == 401
    assert web.get("/auth/me/devices").json()[0]["revoked"] is True

    # A second installation, revoked from the website.
    verifier2, challenge2 = pkce()
    started2 = start(desktop, challenge2)
    code2 = web.post(f"/auth/desktop/codes/{started2['code_id']}/approve").json()["redirect_url"].split("code=")[1].split("&")[0]
    second = desktop.post("/auth/desktop/token", json={"code": code2, "code_verifier": verifier2}).json()
    assert web.delete(f"/auth/me/devices/{second['device']['id']}").json() == {"revoked": True}
    assert desktop.get("/auth/me", headers={"Authorization": f"Bearer {second['access_token']}"}).status_code == 401
    assert web.delete("/auth/me/devices/nope").status_code == 404

    # The web session is untouched by desktop revocations.
    assert web.get("/auth/me").status_code == 200
    with app.state.db_factory() as session:
        assert session.scalar(select(RefreshToken).where(RefreshToken.client == "web", RefreshToken.revoked.is_(False))) is not None
        assert all(r.revoked for r in session.scalars(select(AccessToken).where(AccessToken.device_id.is_not(None))))
        assert all(d.revoked_at for d in session.scalars(select(Device)))


def test_deleting_the_account_removes_devices(app, desktop, web):
    verifier, challenge = pkce()
    started = start(desktop, challenge)
    code = web.post(f"/auth/desktop/codes/{started['code_id']}/approve").json()["redirect_url"].split("code=")[1].split("&")[0]
    tokens = desktop.post("/auth/desktop/token", json={"code": code, "code_verifier": verifier}).json()
    assert web.delete("/auth/me").status_code == 204
    assert desktop.post("/auth/desktop/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code == 401
    with app.state.db_factory() as session:
        assert session.scalar(select(Device)) is None
