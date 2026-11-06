"""Usage heartbeats and the admin portal (POST /telemetry/heartbeat, /admin/*)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.services import activity, admin_auth
from auth import firebase
from database.models import ActivityDaily, ActivityPageDaily, ActivityPresence, AdminSignInAttempt, UserProject

ORIGIN = {"Origin": "http://localhost:3000"}
PASSWORD = "Kiungo1.!"
T0 = datetime(2026, 11, 6, 9, 0, tzinfo=timezone.utc)


def _claims(uid: str, email: str, name: str) -> dict:
    return {
        "uid": uid,
        "sub": uid,
        "email": email,
        "email_verified": True,
        "name": name,
        "picture": None,
        "firebase": {"sign_in_provider": "google.com", "identities": {"google.com": [f"g-{uid}"]}},
    }


def _make_app(tmp_path, monkeypatch, *, require_auth: str = "false"):
    monkeypatch.setenv("HHIP_REQUIRE_AUTH", require_auth)
    monkeypatch.setenv("HHIP_DISABLE_DISCOVERY", "1")
    monkeypatch.delenv("HHIP_ADMIN_PASSWORD_HASH", raising=False)
    tokens: dict[str, dict] = {}
    monkeypatch.setattr(firebase, "verify_id_token", lambda token: tokens[token])
    application = create_app(data_dir=tmp_path)
    application.state.fake_tokens = tokens
    return application


@pytest.fixture
def app(tmp_path, monkeypatch):
    return _make_app(tmp_path, monkeypatch)


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


def sign_in(client: TestClient, uid: str = "uid-1", email: str = "ada@example.test", name: str = "Ada") -> dict:
    client.app.state.fake_tokens[uid] = _claims(uid, email, name)
    response = client.post("/auth/google", json={"id_token": uid})
    assert response.status_code == 200, response.text
    client.cookies.clear()  # tests choose how each request identifies itself
    return response.json()


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def admin_token(client: TestClient) -> str:
    response = client.post("/admin/session", json={"password": PASSWORD})
    assert response.status_code == 200, response.text
    return response.json()["token"]


# ----- pages -----


@pytest.mark.parametrize(
    ("raw", "page"),
    [
        ("/", "/"),
        ("/projects/3f2c9a1e-4b5d-4e6f-8a9b-0c1d2e3f4a5b?tab=records#x", "/projects/:id"),
        ("https://kiungo.example/Lab/7a8b9c0d1e2f3a4b", "/lab/:id"),
        ("/learning-center/arduino-basics", "/learning-center/arduino-basics"),
        ("/users/42/edit", "/users/:id/edit"),
        ("/a/b/c/d/e/f/g/h", "/a/b/c/d/e/f"),
        ("/search/<script>", "/search/:id"),
        ("/desktop/project", "/desktop/project"),
        ("", "/"),
    ],
)
def test_pages_are_grouped_without_ids(raw, page):
    assert activity.normalize_page(raw) == page


# ----- crediting time -----


def _beat(**kw) -> activity.Beat:
    base = {"client": "web", "page": "/lab", "event": "beat", "user_id": None, "visitor_key": "v1"}
    base.update(kw)
    return activity.Beat(**base)


def test_time_is_the_gap_between_heartbeats_capped_and_on_the_previous_page(app):
    with TestClient(app):
        with app.state.db_factory() as s:
            activity.record(s, _beat(event="view", page="/lab"), T0)
            activity.record(s, _beat(), T0 + timedelta(seconds=30))  # +30 on /lab
            activity.record(s, _beat(event="view", page="/projects"), T0 + timedelta(seconds=60))  # +30 on /lab, then a view of /projects
            assert activity.record(s, _beat(page="/projects"), T0 + timedelta(seconds=65)) is False  # too soon: ignored
            activity.record(s, _beat(page="/projects"), T0 + timedelta(seconds=200))  # 140 s gap: capped at 75, on /projects
            activity.record(s, _beat(page="/projects"), T0 + timedelta(seconds=600))  # 400 s of nothing: a new visit, no credit
            day = s.get(ActivityDaily, ("v:v1", T0.date(), "web"))
            assert day.seconds == 30 + 30 + 75
            lab = s.get(ActivityPageDaily, (T0.date(), "web", "/lab"))
            projects = s.get(ActivityPageDaily, (T0.date(), "web", "/projects"))
            assert (lab.views, lab.seconds) == (1, 60)
            assert (projects.views, projects.seconds) == (1, 75)
            presence = s.get(ActivityPresence, ("v:v1", "web"))
            assert presence.visit_started_at.replace(tzinfo=timezone.utc) == T0 + timedelta(seconds=600)


def test_leaving_credits_the_last_stretch_and_goes_offline(app):
    with TestClient(app):
        with app.state.db_factory() as s:
            activity.record(s, _beat(event="view"), T0)
            activity.record(s, _beat(event="leave"), T0 + timedelta(seconds=20))
            assert s.get(ActivityDaily, ("v:v1", T0.date(), "web")).seconds == 20
            data = activity.overview(s, days=1, now=T0 + timedelta(seconds=30))
            assert data["totals"]["online_visitors"] == 0
            # Coming back starts a new visit and credits nothing for the time away.
            activity.record(s, _beat(), T0 + timedelta(seconds=60))
            assert s.get(ActivityDaily, ("v:v1", T0.date(), "web")).seconds == 20
            assert activity.overview(s, days=1, now=T0 + timedelta(seconds=70))["totals"]["online_visitors"] == 1


def test_old_rows_are_deleted(app):
    with TestClient(app):
        with app.state.db_factory() as s:
            old = T0 - timedelta(days=activity.RETAIN_DAYS + 3)
            activity.record(s, _beat(event="view"), old)
            activity.record(s, _beat(), old + timedelta(seconds=30))
            activity.record(s, _beat(visitor_key="v2", event="view"), T0)
            activity.prune(s, T0)
            assert s.query(ActivityDaily).count() == 0
            assert {p.page for p in s.query(ActivityPageDaily)} == {"/lab"}
            assert [p.subject for p in s.query(ActivityPresence)] == ["v:v2"]


# ----- the heartbeat route -----


def test_a_signed_out_visitor_counts_from_the_website_only(client):
    ok = client.post("/telemetry/heartbeat", json={"visitor": "visitor-abc-123", "page": "/", "event": "view"}, headers=ORIGIN)
    assert ok.status_code == 204
    elsewhere = client.post("/telemetry/heartbeat", json={"visitor": "visitor-abc-123"}, headers={"Origin": "https://evil.example"})
    assert elsewhere.status_code == 403
    with client.app.state.db_factory() as s:
        rows = list(s.query(ActivityPresence))
        assert len(rows) == 1 and rows[0].user_id is None
        assert "visitor-abc-123" not in rows[0].subject  # stored hashed


def test_sendbeacon_text_body_and_bad_bodies(client):
    beacon = client.post("/telemetry/heartbeat", content='{"visitor":"visitor-abc-123","event":"leave","page":"/lab"}', headers={**ORIGIN, "Content-Type": "text/plain;charset=UTF-8"})
    assert beacon.status_code == 204
    assert client.post("/telemetry/heartbeat", content="not json", headers=ORIGIN).status_code == 422
    assert client.post("/telemetry/heartbeat", json={"client": "phone"}, headers=ORIGIN).status_code == 422
    assert client.post("/telemetry/heartbeat", content="x" * 5000, headers=ORIGIN).status_code == 413


def test_signed_in_heartbeats_count_for_the_account_on_web_and_desktop(client):
    me = sign_in(client)
    for event in ("view", "beat"):
        assert client.post("/telemetry/heartbeat", json={"page": "/lab", "event": event, "visitor": "visitor-abc-123"}, headers=bearer(me["access_token"])).status_code == 204
    assert client.post("/telemetry/heartbeat", json={"client": "desktop", "page": "/desktop/home", "app_version": "0.12.2"}, headers=bearer(me["access_token"])).status_code == 204
    # The desktop app without a token is nobody to credit.
    assert client.post("/telemetry/heartbeat", json={"client": "desktop", "page": "/desktop/home"}, headers=ORIGIN).status_code == 204
    with client.app.state.db_factory() as s:
        subjects = {(p.subject, p.client, p.user_id) for p in s.query(ActivityPresence)}
        uid = me["user"]["id"]
        assert subjects == {(f"u:{uid}", "web", uid), (f"u:{uid}", "desktop", uid)}


def test_the_websites_refresh_cookie_identifies_without_rotating(client):
    me = sign_in(client)
    client.cookies.set("hhip_refresh", me["refresh_token"])
    assert client.post("/telemetry/heartbeat", json={"page": "/", "event": "view"}, headers=ORIGIN).status_code == 204
    with client.app.state.db_factory() as s:
        assert s.query(ActivityPresence).one().user_id == me["user"]["id"]
    # The same refresh token still works afterwards: the heartbeat didn't use it up.
    assert client.post("/auth/refresh", json={"refresh_token": me["refresh_token"]}).status_code == 200


def test_heartbeats_and_admin_sign_in_pass_the_write_check(tmp_path, monkeypatch):
    application = _make_app(tmp_path, monkeypatch, require_auth="true")
    with TestClient(application) as c:
        assert c.post("/telemetry/heartbeat", json={"visitor": "visitor-abc-123", "event": "view"}, headers=ORIGIN).status_code == 204
        assert c.post("/admin/session", json={"password": PASSWORD}, headers=ORIGIN).status_code == 200


# ----- admin sign-in -----


def test_the_password_is_checked_on_the_server(client):
    assert client.post("/admin/session", json={"password": "kiungo1.!"}).status_code == 401
    assert client.post("/admin/session", json={"password": ""}).status_code == 422
    token = admin_token(client)
    response = client.get("/admin/overview", headers=bearer(token))
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"


def test_the_overview_needs_an_admin_token_not_an_account_token(client):
    me = sign_in(client)
    assert client.get("/admin/overview").status_code == 401
    assert client.get("/admin/overview", headers=bearer(me["access_token"])).status_code == 401
    assert client.get("/admin/overview", headers=bearer("not-a-token")).status_code == 401
    # And the admin token opens nothing on the account side.
    assert client.get("/auth/me", headers=bearer(admin_token(client))).status_code == 401


def test_wrong_passwords_lock_out_that_address(client):
    for _ in range(admin_auth.MAX_FAILURES_PER_ADDRESS):
        assert client.post("/admin/session", json={"password": "guess"}).status_code == 401
    locked = client.post("/admin/session", json={"password": PASSWORD})
    assert locked.status_code == 429
    assert int(locked.headers["retry-after"]) > 0
    assert "Try again in" in locked.json()["detail"]
    with client.app.state.db_factory() as s:
        assert s.query(AdminSignInAttempt).count() == admin_auth.MAX_FAILURES_PER_ADDRESS  # the locked-out try isn't checked or counted
        # Fifteen minutes later it opens again.
        later = datetime.now(timezone.utc) + timedelta(minutes=admin_auth.LOCKOUT_MINUTES, seconds=5)
        assert admin_auth.retry_after(s, "anything-else", later) == 0


def test_signing_out_ends_the_token_at_once(client):
    token = admin_token(client)
    assert client.delete("/admin/session", headers=bearer(token)).status_code == 204
    assert client.get("/admin/overview", headers=bearer(token)).status_code == 401


def test_tokens_expire(app):
    with TestClient(app):
        with app.state.db_factory() as s:
            token, _, _ = admin_auth.sign_in(s, password=PASSWORD, ip_hash="x", secret=app.state.session_secret, now=T0)
            assert admin_auth.session_for(s, token, app.state.session_secret, now=T0 + timedelta(minutes=29)) is not None
            assert admin_auth.session_for(s, token, app.state.session_secret, now=T0 + timedelta(minutes=31)) is None


def test_the_password_can_be_changed_with_an_environment_variable(client, monkeypatch):
    monkeypatch.setenv("HHIP_ADMIN_PASSWORD_HASH", admin_auth.hash_password("something new"))
    assert client.post("/admin/session", json={"password": PASSWORD}).status_code == 401
    assert client.post("/admin/session", json={"password": "something new"}).status_code == 200


def test_the_default_hash_is_the_password_set_on_6_november():
    assert admin_auth.check_password(PASSWORD, admin_auth.DEFAULT_HASH)
    assert not admin_auth.check_password("Kiungo1.", admin_auth.DEFAULT_HASH)


# ----- the overview -----


def test_the_overview_counts_accounts_projects_time_pages_and_who_is_online(client):
    ada = sign_in(client, "uid-1", "ada@example.test", "Ada")
    bo = sign_in(client, "uid-2", "bo@example.test", "Bo")
    client.post("/auth/me/projects", json={"name": "Rover", "category": "robotics", "hardware": [], "description": "", "objectives": ""}, headers=bearer(ada["access_token"]))
    with client.app.state.db_factory() as s:
        assert s.query(UserProject).count() == 1
        now = datetime.now(timezone.utc)
        a, b = ada["user"]["id"], bo["user"]["id"]
        # Ada: 2 minutes on the web today, still here. Bo: 5 minutes on desktop yesterday, gone.
        activity.record(s, _beat(user_id=a, visitor_key=None, event="view", page="/lab"), now - timedelta(seconds=120))
        for k in (1, 2, 3, 4):
            activity.record(s, _beat(user_id=a, visitor_key=None, page="/lab"), now - timedelta(seconds=120 - 30 * k))
        y = now - timedelta(days=1)
        activity.record(s, _beat(user_id=b, visitor_key=None, client="desktop", event="view", page="/desktop/project"), y)
        for k in range(1, 6):
            activity.record(s, _beat(user_id=b, visitor_key=None, client="desktop", page="/desktop/project"), y + timedelta(seconds=60 * k))
        activity.record(s, _beat(event="view", page="/"), now)  # a visitor, signed out, right now

    data = client.get("/admin/overview?days=7", headers=bearer(admin_token(client))).json()
    t = data["totals"]
    assert (t["accounts"], t["projects"], t["online_accounts"], t["online_visitors"]) == (2, 1, 1, 1)
    assert t["seconds_range"] == 120 + 300
    by_name = {acc["name"]: acc for acc in data["accounts"]}
    assert by_name["Ada"]["online"] is True and by_name["Bo"]["online"] is False
    assert (by_name["Ada"]["seconds_web"], by_name["Bo"]["seconds_desktop"]) == (120, 300)
    assert by_name["Ada"]["projects"] == 1
    assert [acc["name"] for acc in data["accounts"]] == ["Bo", "Ada"]  # most time first
    assert data["online"][0]["name"] == "Ada" and data["online"][0]["page"] == "/lab"
    assert {p["page"] for p in data["pages"]} == {"/lab", "/desktop/project", "/"}
    assert data["clients"] == {"web": 120, "desktop": 300}
    assert len(data["daily"]) == 7 and data["daily"][-1]["new_accounts"] == 2
    assert data["admin_sign_ins"][0]["ok"] is True
