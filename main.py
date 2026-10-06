"""Cloud Functions (2nd gen) entry — serves the FastAPI app on Google Cloud."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent
_CREDENTIALS = _ROOT / "credentials" / "firebase-adminsdk.json"
_SESSION_FILE = _ROOT / "credentials" / "session.secret"

os.environ.setdefault("FIREBASE_CREDENTIALS", str(_CREDENTIALS))
os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", str(_CREDENTIALS))
os.environ.setdefault(
    "HHIP_CORS_ORIGINS",
    ",".join(
        [
            "https://hhipsystemv0.web.app",
            "https://hhipsystemv0.firebaseapp.com",
            "https://hhipsystemv0--hhipsystemv0.europe-west4.hosted.app",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ]
    ),
)
os.environ.setdefault("COOKIE_SECURE", "true")
os.environ.setdefault("COOKIE_SAMESITE", "none")
os.environ.setdefault("HHIP_FIRMWARE_DRY_RUN", "1")
os.environ.setdefault("HHIP_DATA_DIR", "/tmp/hhip-data")
os.environ.setdefault("HHIP_DISABLE_DISCOVERY", "1")
if _SESSION_FILE.is_file():
    os.environ.setdefault("SESSION_SECRET", _SESSION_FILE.read_text(encoding="utf-8").strip())

from firebase_functions import https_fn, options
from firebase_functions.options import set_global_options

set_global_options(
    region="europe-west4",
    max_instances=10,
    memory=options.MemoryOption.GB_1,
)

_client: Any = None
_HOP_BY_HOP = {
    "connection",
    "content-encoding",
    "content-length",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}


def _get_client():
    global _client
    if _client is not None:
        return _client
    from starlette.testclient import TestClient
    from api.main import app as fastapi_app

    # Lazy init so Firebase deploy discovery does not time out during import.
    cm = TestClient(fastapi_app, raise_server_exceptions=False)
    _client = cm.__enter__()
    return _client


@https_fn.on_request(
    invoker="public",
    timeout_sec=3600,
    memory=options.MemoryOption.GB_1,
    cpu=1,
    concurrency=8,
)
def api(req: https_fn.Request) -> https_fn.Response:
    client = _get_client()
    path = req.path or "/"
    query = req.query_string
    if isinstance(query, bytes):
        query = query.decode("utf-8", errors="ignore")
    url = path + (f"?{query}" if query else "")

    headers = {key: value for key, value in req.headers.items() if key.lower() != "host"}
    body = req.get_data() or b""

    upstream = client.request(
        method=req.method,
        url=url,
        headers=headers,
        content=body,
    )
    response_headers = {
        key: value
        for key, value in upstream.headers.items()
        if key.lower() not in _HOP_BY_HOP
    }
    return https_fn.Response(
        response=upstream.content,
        status=upstream.status_code,
        headers=response_headers,
    )
