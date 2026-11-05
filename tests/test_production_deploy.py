"""
What the Cloud Functions deploy (main.py) must keep serving for the website.

In November 2026 production was found running a cut-down "Kiungo Authentication
API" (21 paths: sign-in, account, firmware) instead of this app, so the Hybrid
page, the component library, desktop sign-in, sync and releases all got 404s.
These tests hold the deployable app to what the website needs.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import create_app

ROOT = Path(__file__).resolve().parent.parent
SITE = "https://kiungo-labs-technologies.vercel.app"

# Every route the cut-down production API served (its /openapi.json, 4 Nov 2026), so
# deploying this app in its place takes nothing away. Path parameters are compared by position.
SERVED_IN_PRODUCTION = """
GET /auth/config
POST /auth/google
POST /auth/github
POST /auth/link-provider
POST /auth/refresh
POST /auth/ws-ticket
GET /auth/me
PATCH /auth/me
GET /auth/me/projects
POST /auth/me/projects
GET /auth/users/search
GET /auth/me/projects/{}
PUT /auth/me/projects/{}
DELETE /auth/me/projects/{}
GET /auth/me/projects/{}/experiments
POST /auth/me/projects/{}/experiments
PUT /auth/me/projects/{}/experiments/{}
DELETE /auth/me/projects/{}/experiments/{}
GET /auth/me/learning-progress
PUT /auth/me/learning-progress
GET /auth/me/lab-sessions
PUT /auth/me/lab-sessions/{}
DELETE /auth/me/lab-sessions/{}
POST /auth/logout
GET /firmware/templates
GET /firmware/projects
POST /firmware/projects
GET /firmware/projects/{}
PUT /firmware/projects/{}/files
GET /health
""".split("\n")

# What the website's Hybrid page and component library read, signed out.
WEBSITE_PUBLIC_READS = ["/controllers", "/components/search"]


def _shape(path: str) -> str:
    import re

    return re.sub(r"\{[^}]+\}", "{}", path)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HHIP_REQUIRE_AUTH", "true")
    monkeypatch.setenv("HHIP_CORS_ORIGINS", SITE)
    app = create_app(data_dir=tmp_path)
    with TestClient(app) as test_client:
        yield test_client


def test_serves_everything_production_served(client):
    spec = client.get("/openapi.json").json()
    have = {f"{method.upper()} {_shape(path)}" for path, ops in spec["paths"].items() for method in ops}
    missing = [route for route in (r.strip() for r in SERVED_IN_PRODUCTION) if route and route not in have]
    assert missing == []


@pytest.mark.parametrize("path", WEBSITE_PUBLIC_READS)
def test_hybrid_page_reads_work_signed_out(client, path):
    response = client.get(path)
    assert response.status_code == 200
    assert isinstance(response.json(), list) and len(response.json()) > 0


def test_the_website_may_call_it(client):
    preflight = client.options(
        "/hybrid/create",
        headers={"Origin": SITE, "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type"},
    )
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == SITE
    assert preflight.headers["access-control-allow-credentials"] == "true"
    # Signed out, a write from the site is refused for the sign-in, not the origin.
    write = client.post("/hybrid/create", json={}, headers={"Origin": SITE})
    assert write.status_code == 401


def test_the_deploy_allows_the_website():
    """main.py, as Cloud Functions imports it: the production site is an allowed origin."""
    env = {k: v for k, v in os.environ.items() if k != "HHIP_CORS_ORIGINS"}
    out = subprocess.run(
        [sys.executable, "-c", "import os, json, main; print(json.dumps(os.environ['HHIP_CORS_ORIGINS'].split(',')))"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    origins = json.loads(out.stdout.strip().splitlines()[-1])
    assert SITE in origins
    assert all(o.startswith(("https://", "http://localhost", "http://127.0.0.1")) for o in origins)
