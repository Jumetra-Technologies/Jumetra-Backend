"""Phase One objects belong to the person who made them (audit 13 Nov 2026: ENG-002, ENG-004, ENG-006).

Runs with sign-in required, as production does: two accounts, A and B.
"""

from __future__ import annotations

import secrets

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from api.main import create_app
from auth import firebase


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
    monkeypatch.setenv("HHIP_FIRMWARE_DRY_RUN", "1")
    monkeypatch.setattr(firebase, "verify_id_token", lambda token: _claims(token))
    return create_app(data_dir=tmp_path)


def _signed_in(app, uid: str) -> TestClient:
    c = TestClient(app, cookies={})
    c.__enter__()
    token = c.post("/auth/google", json={"id_token": uid}).json()["access_token"]
    c.cookies.clear()
    c.headers["Authorization"] = f"Bearer {token}"
    return c


@pytest.fixture
def people(app):
    a, b = _signed_in(app, "alice"), _signed_in(app, "bob")
    anon = TestClient(app, cookies={})
    anon.__enter__()
    yield a, b, anon
    for c in (a, b, anon):
        c.__exit__(None, None, None)


# ----- firmware projects -----


def test_firmware_projects_are_private(people):
    a, b, anon = people
    project = a.post("/firmware/projects", json={"name": "Alice's rover"}).json()
    pid = project["project_id"]
    a.put(f"/firmware/projects/{pid}/files", json={"path": "src/main.ino", "content": "// alice's secret"})

    # Signed out: no list, no project (it used to return every user's files).
    assert anon.get("/firmware/projects").status_code == 401
    assert anon.get(f"/firmware/projects/{pid}").status_code == 401

    # Bob sees none of it and can't touch it.
    assert b.get("/firmware/projects").json()["projects"] == []
    assert b.get(f"/firmware/projects/{pid}").status_code == 404
    assert b.put(f"/firmware/projects/{pid}/files", json={"path": "src/main.ino", "content": "x"}).status_code == 404
    assert b.post("/firmware/build", json={"project_id": pid}).status_code == 404
    assert b.post("/firmware/build/jobs", json={"project_id": pid}).status_code == 404
    assert b.post("/firmware/upload", json={"project_id": pid}).status_code == 404

    # Alice still has everything.
    mine = a.get("/firmware/projects").json()
    assert [p["project_id"] for p in mine["projects"]] == [pid] and mine["count"] == 1
    files = a.get(f"/firmware/projects/{pid}").json()["files"]
    assert any("alice's secret" in f.get("content", "") for f in files)
    assert a.post("/firmware/build", json={"project_id": pid}).status_code == 200


def test_firmware_templates_stay_open(people):
    _, _, anon = people
    assert anon.get("/firmware/templates").status_code == 200
    assert anon.get("/firmware/toolchains").status_code == 200


def test_firmware_owners_survive_a_restart(tmp_path, monkeypatch):
    monkeypatch.setenv("HHIP_REQUIRE_AUTH", "true")
    monkeypatch.setenv("HHIP_DISABLE_DISCOVERY", "1")
    monkeypatch.setenv("HHIP_FIRMWARE_DRY_RUN", "1")
    monkeypatch.setattr(firebase, "verify_id_token", lambda token: _claims(token))
    first = create_app(data_dir=tmp_path)
    a = _signed_in(first, "alice")
    pid = a.post("/firmware/projects", json={"name": "kept"}).json()["project_id"]
    a.__exit__(None, None, None)

    second = create_app(data_dir=tmp_path)
    a2, b2 = _signed_in(second, "alice"), _signed_in(second, "bob")
    try:
        assert a2.get(f"/firmware/projects/{pid}").status_code == 200
        assert b2.get(f"/firmware/projects/{pid}").status_code == 404
    finally:
        a2.__exit__(None, None, None)
        b2.__exit__(None, None, None)


# ----- engineering workspaces -----


def test_workspaces_are_private(people):
    a, b, anon = people
    ws = a.post("/engineering/workspace", json={"name": "bench"}).json()["workspace_id"]
    assert anon.get("/engineering/workspace").status_code == 401
    assert b.get("/engineering/workspace").json() == []
    assert b.get(f"/engineering/workspace/{ws}").status_code == 404
    assert b.post(f"/engineering/workspace/{ws}/step", json={"delta_ms": 100}).status_code == 404
    assert [w["workspace_id"] for w in a.get("/engineering/workspace").json()] == [ws]
    assert b.post(f"/engineering/workspace/{ws}/connect").status_code == 404
    assert a.post(f"/engineering/workspace/{ws}/connect").status_code == 200
    assert a.post(f"/engineering/workspace/{ws}/step", json={"delta_ms": 100}).status_code == 200
    assert anon.get("/engineering/workspace/catalog").status_code == 200


def test_a_workspace_stream_needs_its_owner(app, people):
    a, b, _ = people
    ws = a.post("/engineering/workspace", json={"name": "bench"}).json()["workspace_id"]

    def connect(client, path):
        ticket = client.post("/auth/ws-ticket").json()["ticket"]
        return client.websocket_connect(f"{path}?ticket={ticket}", headers={"Origin": "http://localhost:3000"})

    for path in (f"/engineering/workspace/ws/{ws}", f"/ws/workspace/{ws}"):
        with connect(a, path) as socket:
            assert socket.receive_json()["type"] == "workspace_state"
        with pytest.raises(WebSocketDisconnect):
            with connect(b, path) as socket:
                socket.receive_json()


# ----- limits on simulated time (ENG-004) -----


@pytest.mark.parametrize("delta", [0, -100, 60_001, 100_000_000])
def test_a_step_simulates_at_most_a_minute_forward(people, delta):
    a, _, _ = people
    ws = a.post("/engineering/workspace", json={"name": "bench"}).json()["workspace_id"]
    assert a.post(f"/engineering/workspace/{ws}/step", json={"delta_ms": delta}).status_code == 422
    assert a.post("/hybrid/x/advance", json={"delta_ms": delta}).status_code in (404, 422)
    assert a.post("/laboratory/x/simulation/advance", json={"delta_ms": delta}).status_code in (404, 422)


# ----- Hybrid devices (ENG-006) -----


def test_a_server_never_opens_a_device_the_request_names(people):
    a, _, anon = people
    assert anon.post("/hybrid/devices/connect", json={"port": "/dev/ttyACM0"}).status_code in (401, 403)
    for target in ({"port": "socket://10.0.0.1:22"}, {"port": "/dev/ttyACM0"}, {"endpoint": "rfc2217://example.test:2217"}):
        assert a.post("/hybrid/devices/connect", json=target).status_code == 501


def test_a_local_install_only_opens_serial_ports(people, monkeypatch):
    a, _, _ = people
    monkeypatch.delenv("HHIP_DISABLE_DISCOVERY")
    for target in ({"port": "socket://10.0.0.1:22"}, {"endpoint": "rfc2217://example.test:2217"}, {"port": "loop://"}, {"port": "../etc/passwd"}):
        assert a.post("/hybrid/devices/connect", json=target).status_code == 400, target


# ----- Hybrid experiments and laboratories -----


def test_hybrid_experiments_and_laboratories_are_private(people):
    a, b, anon = people
    controllers = a.get("/controllers").json()
    controller = controllers[0]["controller_id"]
    exp = a.post("/hybrid/create", json={"name": "e", "controller_id": controller})
    assert exp.status_code == 200, exp.text
    exp_id = exp.json().get("experiment_id") or exp.json().get("id")
    assert anon.get("/hybrid/").status_code == 401
    assert b.get("/hybrid/").json() == []
    assert b.get(f"/hybrid/{exp_id}").status_code == 404
    assert b.post(f"/hybrid/{exp_id}/stop").status_code == 404
    assert a.get(f"/hybrid/{exp_id}").status_code == 200
    assert len(a.get("/hybrid/").json()) == 1

    lab = a.post("/laboratory/create", json={"name": "l", "controller_id": controller})
    assert lab.status_code == 200, lab.text
    lab_id = lab.json().get("laboratory_id") or lab.json().get("id")
    assert b.get(f"/laboratory/{lab_id}").status_code == 404
    assert anon.get(f"/laboratory/{lab_id}").status_code == 401
    assert a.get(f"/laboratory/{lab_id}").status_code == 200


def test_unknown_owner_ids_are_not_found(people):
    a, _, _ = people
    assert a.get(f"/firmware/projects/{secrets.token_hex(4)}").status_code == 404
