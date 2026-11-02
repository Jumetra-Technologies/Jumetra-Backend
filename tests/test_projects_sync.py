"""Project sync (DSK-14): revisions from the server's clock, If-Match on every write, 409 with the server's tree, per-owner blobs and quotas."""

from __future__ import annotations

import base64
import hashlib
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.routes import projects_sync
from auth import firebase


def _claims(uid):
    return {"uid": uid, "sub": uid, "email": f"{uid}@example.test", "email_verified": True, "name": uid, "firebase": {"sign_in_provider": "google.com", "identities": {"google.com": [f"g-{uid}"]}}}


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("HHIP_REQUIRE_AUTH", "true")
    monkeypatch.setenv("HHIP_DISABLE_DISCOVERY", "1")
    monkeypatch.setattr(firebase, "verify_id_token", lambda token: _claims(token))
    return create_app(data_dir=tmp_path)


def _sign_in(c, uid):
    session = c.post("/auth/google", json={"id_token": uid}).json()
    c.cookies.clear()
    c.headers["Authorization"] = f"Bearer {session['access_token']}"
    return c


@pytest.fixture
def ada(app):
    with TestClient(app) as c:
        yield _sign_in(c, "ada")


@pytest.fixture
def bob(app, ada):
    with TestClient(app) as c:
        yield _sign_in(c, "bob")


def blob(text: str) -> dict:
    data = text.encode()
    return {"sha256": hashlib.sha256(data).hexdigest(), "base64": base64.b64encode(data).decode()}


BASE = "/auth/me/projects-sync"


def push(c, pid, files: dict[str, str], match: str, **extra):
    blobs = [blob(t) for t in files.values()]
    assert c.post(f"{BASE}/{pid}/blobs", json=blobs).status_code == 200
    body = {"name": "Rover", "board": "arduino-uno", "device": "BRAD-THINKPAD", "files": [{"path": p, "sha256": b["sha256"]} for p, b in zip(files, blobs)], **extra}
    return c.put(f"{BASE}/{pid}", json=body, headers={"If-Match": match})


FILES = {"kiungo.json": '{"name":"Rover"}', "circuit.json": '{"nodes":[]}', "sketch/sketch.ino": "void setup() {}\nvoid loop() {}\n"}


def test_create_read_and_fetch_files_back(ada):
    r = push(ada, "prj-rover", FILES, "*")
    assert r.status_code == 200 and r.json() == {"revision": 1}
    assert r.headers["ETag"] == '"r1"'
    tree = ada.get(f"{BASE}/prj-rover")
    assert tree.headers["ETag"] == '"r1"'
    body = tree.json()
    assert body["revision"] == 1 and body["name"] == "Rover" and body["board"] == "arduino-uno"
    assert [f["path"] for f in body["files"]] == ["circuit.json", "kiungo.json", "sketch/sketch.ino"]
    sketch = next(f for f in body["files"] if f["path"] == "sketch/sketch.ino")
    got = ada.get(f"{BASE}/prj-rover/blobs/{sketch['sha256']}")
    assert got.content == FILES["sketch/sketch.ino"].encode()
    assert "immutable" in got.headers["Cache-Control"] and "private" in got.headers["Cache-Control"]
    listed = ada.get(BASE).json()
    assert listed["projects"][0]["id"] == "prj-rover" and listed["used_bytes"] == sum(len(t) for t in FILES.values())


def test_every_write_names_the_revision_it_started_from(ada):
    push(ada, "prj-rover", FILES, "*")
    # No If-Match: refused, so a newer copy is never overwritten by accident.
    assert ada.put(f"{BASE}/prj-rover", json={"files": []}).status_code == 412
    # Creating over an existing project is a conflict, not an overwrite.
    r = push(ada, "prj-rover", FILES, "*")
    assert r.status_code == 409 and r.json()["tree"]["revision"] == 1
    # The right revision goes through and only changed files move on.
    changed = {**FILES, "sketch/sketch.ino": "void setup() { pinMode(13, OUTPUT); }\nvoid loop() {}\n"}
    assert push(ada, "prj-rover", changed, '"r1"').json() == {"revision": 2}
    files = {f["path"]: f for f in ada.get(f"{BASE}/prj-rover").json()["files"]}
    assert files["sketch/sketch.ino"]["sha256"] == hashlib.sha256(changed["sketch/sketch.ino"].encode()).hexdigest()


def test_two_computers_the_second_one_gets_409_and_the_servers_tree(ada):
    push(ada, "prj-rover", FILES, "*")
    laptop = push(ada, "prj-rover", {**FILES, "circuit.json": '{"nodes":[1]}'}, '"r1"')
    assert laptop.json() == {"revision": 2}
    # The desktop PC still thinks it's at r1.
    pc = push(ada, "prj-rover", {**FILES, "sketch/sketch.ino": "// mine\n"}, '"r1"')
    assert pc.status_code == 409
    assert pc.headers["ETag"] == '"r2"'
    tree = pc.json()["tree"]
    assert tree["revision"] == 2
    assert {f["path"] for f in tree["files"]} == set(FILES)


def test_a_commit_needs_its_files_uploaded_first(ada):
    missing = hashlib.sha256(b"never sent").hexdigest()
    r = ada.put(f"{BASE}/prj-x", json={"files": [{"path": "kiungo.json", "sha256": missing}]}, headers={"If-Match": "*"})
    assert r.status_code == 422 and r.json()["missing"] == [missing]
    assert ada.post(f"{BASE}/prj-x/blobs/missing", json={"hashes": [missing]}).json() == {"missing": [missing]}


def test_uploads_are_checked_against_their_hash(ada):
    bad = {"sha256": hashlib.sha256(b"a").hexdigest(), "base64": base64.b64encode(b"b").decode()}
    assert ada.post(f"{BASE}/prj-x/blobs", json=[bad]).status_code == 422


@pytest.mark.parametrize("path", [".kiungo/history.json", "../etc/passwd", "sketch/../kiungo.json", "/kiungo.json", "sketch\\\\a.ino", "secrets.txt", "sketch/a/b/c.ino"])
def test_only_the_projects_own_files_sync(ada, path):
    b = blob("x")
    ada.post(f"{BASE}/prj-x/blobs", json=[b])
    r = ada.put(f"{BASE}/prj-x", json={"files": [{"path": path, "sha256": b["sha256"]}]}, headers={"If-Match": "*"})
    assert r.status_code == 422


def test_knowing_a_hash_gives_no_access_to_someone_elses_file(ada, bob):
    push(ada, "prj-rover", FILES, "*")
    secret = hashlib.sha256(FILES["sketch/sketch.ino"].encode()).hexdigest()
    assert bob.get(f"{BASE}/prj-rover").status_code == 404
    assert bob.get(f"{BASE}/prj-rover/blobs/{secret}").status_code == 404
    # Bob can't commit Ada's content by naming its hash.
    r = bob.put(f"{BASE}/prj-mine", json={"files": [{"path": "sketch/sketch.ino", "sha256": secret}]}, headers={"If-Match": "*"})
    assert r.status_code == 422
    # The same project id on two accounts is two projects.
    assert push(bob, "prj-rover", {"kiungo.json": "{}"}, "*").json() == {"revision": 1}


def test_limits_per_file_per_project_and_per_account(ada, monkeypatch):
    monkeypatch.setattr(projects_sync, "MAX_FILE", 10)
    assert ada.post(f"{BASE}/prj-x/blobs", json=[blob("x" * 11)]).status_code == 413
    monkeypatch.setattr(projects_sync, "MAX_FILE", 2 * 1024 * 1024)
    monkeypatch.setattr(projects_sync, "MAX_PROJECT", 20)
    assert push(ada, "prj-x", {"kiungo.json": "x" * 15, "circuit.json": "y" * 15}, "*").status_code == 413
    monkeypatch.setattr(projects_sync, "MAX_PROJECT", 100)
    monkeypatch.setattr(projects_sync, "QUOTA", 40)
    assert push(ada, "prj-a", {"kiungo.json": "a" * 30}, "*").status_code == 200
    assert push(ada, "prj-b", {"kiungo.json": "b" * 30}, "*").status_code == 413


def test_old_revisions_are_kept_twenty_deep_and_unused_blobs_go(app, ada):
    push(ada, "prj-rover", FILES, "*")
    for i in range(1, 25):
        assert push(ada, "prj-rover", {**FILES, "sketch/sketch.ino": f"// v{i}\n"}, f'"r{i}"').status_code == 200
    from database.models import FileBlob, ProjectRevision
    from sqlalchemy import select

    with app.state.db_factory() as session:
        revisions = session.execute(select(ProjectRevision.revision)).scalars().all()
        assert sorted(revisions) == list(range(6, 26))
        sketches = {hashlib.sha256(f"// v{i}\n".encode()).hexdigest() for i in range(1, 25)}
        stored = set(session.execute(select(FileBlob.sha256)).scalars().all())
        # v1 to v4 fell out with their revisions; v5 onwards are kept.
        assert hashlib.sha256(b"// v1\n").hexdigest() not in stored
        assert hashlib.sha256(b"// v24\n").hexdigest() in stored
        assert len(sketches & stored) == 20


def test_delete_is_soft_restorable_and_purged_after_30_days(app, ada, monkeypatch):
    push(ada, "prj-rover", FILES, "*")
    assert ada.delete(f"{BASE}/prj-rover").status_code == 412
    assert ada.delete(f"{BASE}/prj-rover", headers={"If-Match": '"r9"'}).status_code == 409
    r = ada.delete(f"{BASE}/prj-rover", headers={"If-Match": '"r1"'})
    assert r.status_code == 200 and r.json()["deleted"] is True
    assert ada.get(BASE).json()["projects"][0]["deleted"] is True
    assert ada.post(f"{BASE}/prj-rover/restore").json()["deleted"] is False
    ada.delete(f"{BASE}/prj-rover", headers={"If-Match": '"r1"'})
    later = projects_sync._utcnow() + timedelta(days=31)
    monkeypatch.setattr(projects_sync, "_utcnow", lambda: later)
    assert ada.get(BASE).json()["projects"] == []
    assert ada.get(f"{BASE}/prj-rover").status_code == 404


def test_signed_out_is_refused(app):
    with TestClient(app) as c:
        assert c.get(BASE).status_code == 401
        assert c.put(f"{BASE}/prj-x", json={"files": []}, headers={"If-Match": "*"}).status_code in (401, 403)
