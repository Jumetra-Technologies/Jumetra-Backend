"""Account security fixes from the 13 Nov 2026 audit (claude/kiungo-audit-2026-11-13.md).

API-001  a verified sign-in never joins an account made from an unverified email
API-003  a refresh token can be spent once, even by two requests at the same moment
API-004  a desktop refresh token can't be rotated through the website's /auth/refresh
API-010  signing out ends this session only, unless asked to end them all; never cross-site
API-011  user search treats % and _ as text
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from api.main import create_app
from auth import firebase
from database.models import RefreshToken
from database.service import RefreshSpent, hash_token, spend_refresh


def _claims(provider: str, *, uid: str, email: str, name: str = "Ada", verified: bool = True) -> dict:
    claim = {"google": "google.com", "github": "github.com"}[provider]
    return {
        "uid": uid,
        "sub": uid,
        "email": email,
        "email_verified": verified,
        "name": name,
        "firebase": {"sign_in_provider": claim, "identities": {claim: [f"{provider}-{uid}"]}},
    }


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("HHIP_REQUIRE_AUTH", "false")
    monkeypatch.setenv("HHIP_DISABLE_DISCOVERY", "1")
    monkeypatch.setenv("KIUNGO_WEBSITE_URL", "https://kiungo.test")
    tokens: dict[str, dict] = {}
    monkeypatch.setattr(firebase, "verify_id_token", lambda token: tokens[token])
    application = create_app(data_dir=tmp_path)
    application.state.fake_tokens = tokens
    return application


def sign_in(client: TestClient, provider: str, *, uid: str, email: str, verified: bool = True):
    token = f"{provider}-{uid}-{secrets.token_hex(4)}"
    client.app.state.fake_tokens[token] = _claims(provider, uid=uid, email=email, verified=verified)
    return client.post(f"/auth/{provider}", json={"id_token": token})


def bearer(session: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {session['access_token']}"}


# ----- API-001: pre-account takeover -----


def test_a_verified_sign_in_does_not_join_an_account_made_from_an_unverified_email(app):
    with TestClient(app) as attacker, TestClient(app) as victim:
        # The attacker signs in with GitHub using the victim's address, which GitHub never verified.
        squat = sign_in(attacker, "github", uid="attacker", email="victim@example.test", verified=False)
        assert squat.status_code == 200
        squatter = squat.json()

        # The real owner signs in with Google, which verified the address: not merged into the squat.
        real = sign_in(victim, "google", uid="victim", email="victim@example.test", verified=True)
        assert real.status_code == 409
        assert "already uses" in real.json()["detail"]

        # So nothing the owner does lands in the attacker's account.
        projects = attacker.get("/auth/me/projects", headers=bearer(squatter)).json()
        assert projects == []


def test_a_verified_sign_in_still_finds_an_account_whose_email_was_verified(app):
    with TestClient(app) as c:
        first = sign_in(c, "google", uid="g-1", email="ada@example.test", verified=True).json()
        again = sign_in(c, "github", uid="gh-1", email="ada@example.test", verified=True).json()
        assert again["id"] == first["id"]


# ----- API-003: one spend per refresh token -----


def test_two_requests_holding_the_same_refresh_token_can_spend_it_once(app):
    with TestClient(app) as c:
        refresh = sign_in(c, "google", uid="u", email="u@example.test").json()["refresh_token"]
    factory = app.state.db_factory
    with factory() as first, factory() as second:
        # Both requests read the live row before either writes, as two concurrent refreshes do.
        row_a = first.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_token(refresh)))
        row_b = second.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_token(refresh)))
        assert row_a.revoked is False and row_b.revoked is False
        spend_refresh(first, row_a)
        first.commit()
        with pytest.raises(RefreshSpent):
            spend_refresh(second, row_b)


def test_a_web_refresh_token_works_once(app):
    with TestClient(app) as c:
        refresh = sign_in(c, "google", uid="u", email="u@example.test").json()["refresh_token"]
        c.cookies.clear()
        assert c.post("/auth/refresh", json={"refresh_token": refresh}).status_code == 200
        c.cookies.clear()
        assert c.post("/auth/refresh", json={"refresh_token": refresh}).status_code == 401


# ----- API-004: desktop tokens stay desktop tokens -----


def _desktop_tokens(app) -> dict:
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    with TestClient(app) as web, TestClient(app, cookies={}) as desktop:
        session = sign_in(web, "google", uid="d", email="d@example.test").json()
        web.headers["Authorization"] = f"Bearer {session['access_token']}"
        started = desktop.post("/auth/desktop/codes", json={"code_challenge": challenge, "device": {"name": "Laptop", "platform": "linux", "app_version": "0.13.9"}}).json()
        code = web.post(f"/auth/desktop/codes/{started['code_id']}/approve").json()["redirect_url"].split("code=")[1].split("&")[0]
        tokens = desktop.post("/auth/desktop/token", json={"code": code, "code_verifier": verifier}).json()
        tokens["web_access"] = session["access_token"]
        return tokens


def test_a_desktop_refresh_token_is_refused_by_the_website_refresh(app):
    tokens = _desktop_tokens(app)
    with TestClient(app, cookies={}) as c:
        assert c.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code == 401
        assert c.post("/auth/refresh", headers={"X-Refresh-Token": tokens["refresh_token"]}).status_code == 401
        # Still a good desktop token: the refusal didn't spend it.
        rotated = c.post("/auth/desktop/refresh", json={"refresh_token": tokens["refresh_token"]})
        assert rotated.status_code == 200
        with app.state.db_factory() as session:
            row = session.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_token(rotated.json()["refresh_token"])))
            assert row.client == "desktop" and row.device_id == tokens["device"]["id"]


def test_a_desktop_token_spent_by_another_request_ends_the_device(app):
    tokens = _desktop_tokens(app)
    factory = app.state.db_factory
    with factory() as other:
        row = other.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_token(tokens["refresh_token"])))
        spend_refresh(other, row)
        other.commit()
    with TestClient(app, cookies={}) as c:
        replay = c.post("/auth/desktop/refresh", json={"refresh_token": tokens["refresh_token"]})
        assert replay.status_code == 401
        assert c.get("/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}).status_code == 401


# ----- API-010: sign-out -----


def test_signing_out_ends_this_session_and_leaves_the_others(app):
    tokens = _desktop_tokens(app)
    with TestClient(app) as laptop_browser, TestClient(app) as phone_browser:
        here = sign_in(laptop_browser, "google", uid="d", email="d@example.test").json()
        there = sign_in(phone_browser, "google", uid="d", email="d@example.test").json()
        assert laptop_browser.post("/auth/logout", headers=bearer(here), json={"refresh_token": here["refresh_token"]}).status_code == 200

        assert laptop_browser.get("/auth/me", headers=bearer(here)).status_code == 401
        laptop_browser.cookies.clear()
        assert laptop_browser.post("/auth/refresh", json={"refresh_token": here["refresh_token"]}).status_code == 401
        # The other browser and the desktop app are still signed in.
        assert phone_browser.get("/auth/me", headers=bearer(there)).status_code == 200
        assert phone_browser.get("/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}).status_code == 200


def test_signing_out_everywhere_ends_every_session(app):
    tokens = _desktop_tokens(app)
    with TestClient(app) as c:
        here = sign_in(c, "google", uid="d", email="d@example.test").json()
        assert c.post("/auth/logout?everywhere=true", headers=bearer(here)).status_code == 200
        assert c.get("/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}).status_code == 401
        assert c.get("/auth/me", headers={"Authorization": f"Bearer {tokens['web_access']}"}).status_code == 401


def test_another_website_cannot_sign_people_out_with_their_cookies(app):
    with TestClient(app) as c:
        here = sign_in(c, "google", uid="d", email="d@example.test").json()
        refused = c.post("/auth/logout", headers={"Origin": "https://evil.example"})
        assert refused.status_code == 403
        assert c.get("/auth/me", headers=bearer(here)).status_code == 200
        assert c.post("/auth/logout", headers={"Origin": "http://localhost:3000"}).status_code == 200


# ----- API-011: user search -----


def test_user_search_treats_wildcards_as_text(app):
    with TestClient(app) as c:
        me = sign_in(c, "google", uid="a", email="ada@example.test").json()
        sign_in(c, "google", uid="b", email="bob@example.test")
        sign_in(c, "google", uid="c", email="cy_ra@example.test")
        assert c.get("/auth/users/search", params={"q": "%%"}, headers=bearer(me)).json() == []
        assert c.get("/auth/users/search", params={"q": "__"}, headers=bearer(me)).json() == []
        assert [u["email"] for u in c.get("/auth/users/search", params={"q": "cy_"}, headers=bearer(me)).json()] == ["cy_ra@example.test"]
        assert [u["email"] for u in c.get("/auth/users/search", params={"q": "bo"}, headers=bearer(me)).json()] == ["bob@example.test"]


def test_expired_rows_are_not_spendable(app):
    with TestClient(app) as c:
        refresh = sign_in(c, "google", uid="u", email="u@example.test").json()["refresh_token"]
    with app.state.db_factory() as session:
        row = session.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_token(refresh)))
        row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        session.commit()
    with TestClient(app, cookies={}) as c:
        assert c.post("/auth/refresh", json={"refresh_token": refresh}).status_code == 401
