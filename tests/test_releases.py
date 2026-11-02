"""Desktop releases: the download page and the app's update check read them; only the release pipeline writes them."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.routes.releases import _version_key

TOKEN = "pipeline-secret-for-tests"
SHA = "A" * 86 + "=="


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HHIP_REQUIRE_AUTH", "false")
    monkeypatch.setenv("HHIP_DISABLE_DISCOVERY", "1")
    monkeypatch.setenv("KIUNGO_RELEASE_TOKEN", TOKEN)
    with TestClient(create_app(data_dir=tmp_path)) as c:
        yield c


def file(platform="windows", arch="x64", kind="nsis", version="0.5.0"):
    return {"platform": platform, "arch": arch, "kind": kind, "url": f"https://downloads.kiungo.test/{version}/Kiungo-{version}-{platform}-{arch}.{kind}", "sha512": SHA, "size": 120_000_000}


def publish(client, version, files=None, channel="stable", token=TOKEN, **extra):
    body = {"channel": channel, "version": version, "notes": f"Kiungo {version}", "files": files or [file(version=version)], **extra}
    return client.post("/releases", json=body, headers={"Authorization": f"Bearer {token}"})


def test_nothing_published_yet(client):
    response = client.get("/releases/latest")
    assert response.status_code == 404


def test_latest_is_the_highest_version_not_the_newest_row(client):
    assert publish(client, "0.10.0").status_code == 201
    assert publish(client, "0.9.0").status_code == 201
    body = client.get("/releases/latest", params={"platform": "windows", "arch": "x64"}).json()
    assert body["version"] == "0.10.0"
    assert body["files"] == [file(version="0.10.0")]


def test_only_installers_for_this_computer(client):
    publish(client, "0.5.0", files=[file(), file("macos", "arm64", "dmg"), file("linux", "x64", "appimage")])
    publish(client, "0.6.0", files=[file()])
    mac = client.get("/releases/latest", params={"platform": "macos", "arch": "arm64"})
    assert mac.json()["version"] == "0.5.0"
    assert [f["kind"] for f in mac.json()["files"]] == ["dmg"]
    assert mac.headers["cache-control"] == "public, max-age=300"
    assert len(client.get("/releases/latest").json()["files"]) == 1  # 0.6.0, every platform it has
    assert client.get("/releases/latest", params={"platform": "linux", "arch": "arm64"}).status_code == 404


def test_channels_are_separate_and_prereleases_sort_before_the_release(client):
    publish(client, "0.6.0-beta.2", channel="beta")
    publish(client, "0.6.0-beta.10", channel="beta")
    publish(client, "0.5.0")
    assert client.get("/releases/latest", params={"channel": "beta"}).json()["version"] == "0.6.0-beta.10"
    assert client.get("/releases/latest").json()["version"] == "0.5.0"
    assert _version_key("1.0.0-beta.1") < _version_key("1.0.0")
    assert _version_key("1.0.0-alpha") < _version_key("1.0.0-beta")


def test_scheduled_and_withdrawn_releases_are_not_offered(client):
    publish(client, "0.5.0")
    later = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    publish(client, "0.6.0", published_at=later)
    publish(client, "0.7.0")
    assert client.get("/releases/latest").json()["version"] == "0.7.0"
    withdrawn = client.post("/releases/stable/0.7.0/withdraw", headers={"Authorization": f"Bearer {TOKEN}"})
    assert withdrawn.json() == {"channel": "stable", "version": "0.7.0", "withdrawn": True}
    assert client.get("/releases/latest").json()["version"] == "0.5.0"


def test_minimum_version_is_returned(client):
    publish(client, "0.8.0", minimum_version="0.7.0")
    assert client.get("/releases/latest").json()["minimum_version"] == "0.7.0"


def test_only_the_pipeline_can_publish(client, monkeypatch):
    assert publish(client, "0.5.0", token="wrong").status_code == 401
    assert client.post("/releases", json={"version": "0.5.0", "files": [file()]}).status_code == 401
    assert client.post("/releases/stable/0.5.0/withdraw").status_code == 401
    monkeypatch.delenv("KIUNGO_RELEASE_TOKEN")
    assert publish(client, "0.5.0").status_code == 503


def test_a_release_cannot_be_changed(client):
    assert publish(client, "0.5.0").status_code == 201
    again = publish(client, "0.5.0")
    assert again.status_code == 409
    assert "publish a new version" in again.json()["detail"]


@pytest.mark.parametrize(
    "body",
    [
        {"version": "five", "files": [file()]},
        {"version": "0.5.0", "files": []},
        {"version": "0.5.0", "files": [{**file(), "url": "http://plain.test/k.exe"}]},
        {"version": "0.5.0", "files": [{**file(), "platform": "beos"}]},
        {"version": "0.5.0", "files": [file(), file()]},
        {"version": "0.5.0", "channel": "nightly", "files": [file()]},
    ],
)
def test_bad_releases_are_refused(client, body):
    response = client.post("/releases", json=body, headers={"Authorization": f"Bearer {TOKEN}"})
    assert response.status_code == 422, response.text


def test_publishing_works_with_sign_in_enforced(tmp_path, monkeypatch):
    # Production enforces sign-in on writes; the pipeline has a token, not a session or a website origin.
    monkeypatch.setenv("HHIP_REQUIRE_AUTH", "true")
    monkeypatch.setenv("HHIP_DISABLE_DISCOVERY", "1")
    monkeypatch.setenv("KIUNGO_RELEASE_TOKEN", TOKEN)
    with TestClient(create_app(data_dir=tmp_path)) as c:
        assert publish(c, "0.5.0").status_code == 201
        assert publish(c, "0.5.1", token="wrong").status_code == 401
        assert c.post("/releases/stable/0.5.0/withdraw", headers={"Authorization": f"Bearer {TOKEN}"}).status_code == 200
