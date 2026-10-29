"""Sign-in with Google and GitHub, linking, the profile, and the account's own data.

Firebase isn't reachable from tests, so ``auth.firebase.verify_id_token`` is
replaced with a fake that returns the claims a real token would carry.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from auth import firebase


def _claims(provider: str, *, uid: str, email: str, name: str, verified: bool = True, sub: str | None = None) -> dict:
    claim = {"google": "google.com", "github": "github.com"}[provider]
    return {
        "uid": uid,
        "sub": uid,
        "email": email,
        "email_verified": verified,
        "name": name,
        "picture": f"https://example.test/{uid}.png",
        "firebase": {"sign_in_provider": claim, "identities": {claim: [sub or f"{provider}-{uid}"]}},
    }


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("HHIP_REQUIRE_AUTH", "false")
    monkeypatch.setenv("HHIP_DISABLE_DISCOVERY", "1")
    tokens: dict[str, dict] = {}
    monkeypatch.setattr(firebase, "verify_id_token", lambda token: tokens[token])
    application = create_app(data_dir=tmp_path)
    application.state.fake_tokens = tokens
    return application


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


def sign_in(client, provider="google", token="tok-1", **overrides):
    claims = _claims(provider, uid=overrides.pop("uid", "uid-1"), email=overrides.pop("email", "ada@example.test"), name=overrides.pop("name", "Ada"), **overrides)
    client.app.state.fake_tokens[token] = claims
    response = client.post(f"/auth/{provider}", json={"id_token": token})
    assert response.status_code == 200, response.text
    return response.json()


def auth(session):
    return {"Authorization": f"Bearer {session['access_token']}"}


# ----- sign-in -----


def test_google_sign_in_returns_a_session_and_the_user(client):
    session = sign_in(client)
    assert session["token_type"] == "Bearer"
    assert session["refresh_token"]
    user = session["user"]
    assert user["email"] == "ada@example.test"
    assert user["display_name"] == "Ada"
    assert user["picture_url"].endswith("uid-1.png")
    assert user["auth_provider"] == "google"
    assert user["linked_providers"] == ["google"]
    assert user["profile_complete"] is False
    assert user["platform_role"] == "RESEARCHER"


def test_github_sign_in_works_and_rejects_a_google_token(client):
    session = sign_in(client, provider="github", token="gh-1", uid="uid-gh")
    assert session["user"]["auth_provider"] == "github"
    client.app.state.fake_tokens["wrong"] = _claims("google", uid="x", email="x@example.test", name="X")
    response = client.post("/auth/github", json={"id_token": "wrong"})
    assert response.status_code == 400
    assert "GitHub" in response.json()["detail"]


def test_signing_in_again_resumes_the_same_account(client):
    first = sign_in(client, token="a")
    second = sign_in(client, token="b")
    assert first["user"]["id"] == second["user"]["id"]


def test_unverified_email_never_merges_into_an_existing_account(client):
    sign_in(client, token="a")
    client.cookies.clear()
    client.app.state.fake_tokens["b"] = _claims("github", uid="other-uid", email="ada@example.test", name="Ada", verified=False)
    response = client.post("/auth/github", json={"id_token": "b"})
    assert response.status_code == 409
    assert "connect GitHub" in response.json()["detail"]


def test_verified_email_from_another_provider_joins_the_account(client):
    first = sign_in(client, token="a")
    second = sign_in(client, provider="github", token="b", uid="uid-1")  # same Firebase user, GitHub this time
    assert first["user"]["id"] == second["user"]["id"]
    assert second["user"]["linked_providers"] == ["google", "github"]


def test_sign_in_without_firebase_answers_503(client, monkeypatch):
    def unavailable(token):
        raise firebase.FirebaseUnavailable("Sign-in isn't set up on this server yet.")

    monkeypatch.setattr(firebase, "verify_id_token", unavailable)
    response = client.post("/auth/google", json={"id_token": "anything"})
    assert response.status_code == 503


def test_bad_token_answers_401(client, monkeypatch):
    def invalid(token):
        raise ValueError("bad")

    monkeypatch.setattr(firebase, "verify_id_token", invalid)
    assert client.post("/auth/google", json={"id_token": "anything"}).status_code == 401


# ----- me, refresh, logout -----


def test_me_refresh_and_logout(client):
    session = sign_in(client)
    me = client.get("/auth/me", headers=auth(session))
    assert me.status_code == 200
    assert me.json()["id"] == session["user"]["id"]

    refreshed = client.post("/auth/refresh", json={"refresh_token": session["refresh_token"]})
    assert refreshed.status_code == 200
    assert refreshed.json()["access_token"] != session["access_token"]
    # The old refresh token is spent.
    assert client.post("/auth/refresh", json={"refresh_token": session["refresh_token"]}).status_code == 401

    new = refreshed.json()
    assert client.post("/auth/logout", headers=auth(new)).status_code == 200
    assert client.get("/auth/me", headers=auth(new)).status_code == 401
    assert client.post("/auth/refresh", json={"refresh_token": new["refresh_token"]}).status_code == 401


def test_me_without_a_token_is_401(client):
    client.cookies.clear()
    assert client.get("/auth/me").status_code == 401


# ----- link provider -----


def test_link_github_to_a_google_account(client):
    session = sign_in(client)
    client.app.state.fake_tokens["gh"] = _claims("github", uid="uid-1", email="ada@example.test", name="Ada")
    response = client.post("/auth/link-provider", json={"id_token": "gh", "provider": "github"}, headers=auth(session))
    assert response.status_code == 200, response.text
    assert response.json()["linked_providers"] == ["google", "github"]


def test_linking_a_provider_owned_by_someone_else_is_409(client):
    other = sign_in(client, provider="github", token="gh-other", uid="uid-2", email="bob@example.test", name="Bob")
    mine = sign_in(client, token="g")
    client.app.state.fake_tokens["gh-again"] = _claims("github", uid="uid-2", email="bob@example.test", name="Bob")
    response = client.post("/auth/link-provider", json={"id_token": "gh-again", "provider": "github"}, headers=auth(mine))
    assert response.status_code == 409
    assert other["user"]["id"] != mine["user"]["id"]


# ----- profile -----


def test_patch_profile_and_validation(client):
    session = sign_in(client)
    saved = client.patch(
        "/auth/me",
        json={"display_name": "Ada L.", "role": "instructor", "organization": "Strathmore", "location": "Nairobi", "bio": "Teaches."},
        headers=auth(session),
    )
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["display_name"] == "Ada L."
    assert body["role"] == "instructor"
    assert body["profile_complete"] is True
    assert body["email"] == "ada@example.test"  # not editable

    assert client.patch("/auth/me", json={"role": "wizard"}, headers=auth(session)).status_code == 422
    assert client.patch("/auth/me", json={"role": "other"}, headers=auth(session)).status_code == 422
    ok = client.patch("/auth/me", json={"role": "other", "role_other": "Maker"}, headers=auth(session))
    assert ok.status_code == 200 and ok.json()["role_other"] == "Maker"
    cleared = client.patch("/auth/me", json={"bio": ""}, headers=auth(session))
    assert cleared.json()["bio"] is None
    assert client.patch("/auth/me", json={"display_name": "x" * 81}, headers=auth(session)).status_code == 422


def test_delete_account_removes_data_and_tokens(client):
    session = sign_in(client)
    client.post("/auth/me/projects", json={"name": "Rover"}, headers=auth(session))
    response = client.delete("/auth/me", headers=auth(session))
    assert response.status_code == 204
    assert client.get("/auth/me", headers=auth(session)).status_code == 401
    again = sign_in(client, token="again")
    assert again["user"]["id"] != session["user"]["id"]
    assert client.get("/auth/me/projects", headers=auth(again)).json() == []


def test_user_search_needs_auth_and_two_characters(client):
    sign_in(client, token="a", uid="u1", email="ada@example.test", name="Ada")
    session = sign_in(client, token="b", uid="u2", email="bob@example.test", name="Bob")
    client.cookies.clear()
    assert client.get("/auth/users/search?q=ad").status_code == 401
    assert client.get("/auth/users/search?q=a", headers=auth(session)).json() == []
    found = client.get("/auth/users/search?q=ad", headers=auth(session)).json()
    assert [u["display_name"] for u in found] == ["Ada"]
    assert set(found[0]) == {"id", "display_name", "email"}


# ----- projects and experiments -----


def test_projects_crud_scoped_to_the_owner(client):
    ada = sign_in(client, token="a", uid="u1", email="ada@example.test", name="Ada")
    bob = sign_in(client, token="b", uid="u2", email="bob@example.test", name="Bob")

    created = client.post(
        "/auth/me/projects",
        json={"name": "Rover", "category": "mobile_robot", "hardware": ["Arduino Uno", "HC-SR04"], "teammates": [{"id": bob["user"]["id"], "display_name": "Bob", "email": "bob@example.test"}]},
        headers=auth(ada),
    )
    assert created.status_code == 201, created.text
    project = created.json()
    assert project["owner_id"] == ada["user"]["id"]
    assert project["hardware"] == ["Arduino Uno", "HC-SR04"]
    assert project["teammates"][0]["display_name"] == "Bob"
    assert project["created_at"]

    assert [p["id"] for p in client.get("/auth/me/projects", headers=auth(ada)).json()] == [project["id"]]
    assert client.get("/auth/me/projects", headers=auth(bob)).json() == []
    assert client.get(f"/auth/me/projects/{project['id']}", headers=auth(bob)).status_code == 404

    updated = client.put(f"/auth/me/projects/{project['id']}", json={"name": "Rover 2", "category": "mobile_robot"}, headers=auth(ada))
    assert updated.status_code == 200 and updated.json()["name"] == "Rover 2"

    exp = client.post(f"/auth/me/projects/{project['id']}/experiments", json={"title": "Range test", "results": "2 cm to 3 m"}, headers=auth(ada))
    assert exp.status_code == 201
    record = exp.json()
    assert record["project_id"] == project["id"]
    assert client.get(f"/auth/me/projects/{project['id']}/experiments", headers=auth(ada)).json()[0]["title"] == "Range test"
    edited = client.put(f"/auth/me/projects/{project['id']}/experiments/{record['id']}", json={"title": "Range test 2"}, headers=auth(ada))
    assert edited.json()["title"] == "Range test 2"
    assert client.delete(f"/auth/me/projects/{project['id']}/experiments/{record['id']}", headers=auth(ada)).json() == {"deleted": True}

    assert client.delete(f"/auth/me/projects/{project['id']}", headers=auth(ada)).json() == {"deleted": True}
    assert client.get("/auth/me/projects", headers=auth(ada)).json() == []
    assert client.post("/auth/me/projects", json={"name": ""}, headers=auth(ada)).status_code == 422


# ----- learning progress and lab sessions -----


def test_learning_progress_round_trip(client):
    session = sign_in(client)
    assert client.get("/auth/me/learning-progress", headers=auth(session)).json() == {"completed": []}
    saved = client.put("/auth/me/learning-progress", json={"completed": ["m2", "m1", "m1", " "]}, headers=auth(session))
    assert saved.json() == {"completed": ["m1", "m2"]}
    assert client.get("/auth/me/learning-progress", headers=auth(session)).json() == {"completed": ["m1", "m2"]}


def test_lab_sessions_save_list_merge_and_delete(client):
    ada = sign_in(client, token="a", uid="u1", email="ada@example.test", name="Ada")
    bob = sign_in(client, token="b", uid="u2", email="bob@example.test", name="Bob")
    doc = {"id": "s1", "name": "Blink", "updatedAt": "2026-10-29T08:00:00.000Z", "nodes": [{"id": "n1"}], "wires": []}
    saved = client.put("/auth/me/lab-sessions/s1", json=doc, headers=auth(ada))
    assert saved.status_code == 200, saved.text
    assert saved.json() == doc
    assert client.get("/auth/me/lab-sessions", headers=auth(ada)).json() == [doc]
    assert client.get("/auth/me/lab-sessions", headers=auth(bob)).json() == []

    older = dict(doc, name="Old", updatedAt="2026-10-28T08:00:00.000Z")
    kept = client.put("/auth/me/lab-sessions/s1", json=older, headers=auth(ada))
    assert kept.json()["name"] == "Blink"  # the newer server copy wins

    newer = dict(doc, name="New", updatedAt="2026-10-30T08:00:00.000Z")
    assert client.put("/auth/me/lab-sessions/s1", json=newer, headers=auth(ada)).json()["name"] == "New"

    assert client.put("/auth/me/lab-sessions/s1", json=dict(doc, id="s2"), headers=auth(ada)).status_code == 422
    assert client.put("/auth/me/lab-sessions/s9", json=[], headers=auth(ada)).status_code == 422
    big = dict(doc, id="s3", log=["x" * 1000] * 800)
    assert client.put("/auth/me/lab-sessions/s3", json=big, headers=auth(ada)).status_code == 413

    assert client.delete("/auth/me/lab-sessions/s1", headers=auth(ada)).json() == {"deleted": True}
    assert client.get("/auth/me/lab-sessions", headers=auth(ada)).json() == []


def test_write_middleware_lets_github_sign_in_through(tmp_path, monkeypatch):
    monkeypatch.setenv("HHIP_REQUIRE_AUTH", "true")
    monkeypatch.setenv("HHIP_DISABLE_DISCOVERY", "1")
    monkeypatch.setattr(firebase, "verify_id_token", lambda token: _claims("github", uid="u", email="u@example.test", name="U"))
    with TestClient(create_app(data_dir=tmp_path)) as c:
        assert c.post("/auth/github", json={"id_token": "t"}, headers={"origin": "https://hhipsystemv0.web.app"}).status_code == 200
        c.cookies.clear()
        assert c.post("/auth/me/projects", json={"name": "x"}, headers={"origin": "https://hhipsystemv0.web.app"}).status_code == 401
