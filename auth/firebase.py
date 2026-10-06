from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

import firebase_admin
from firebase_admin import auth as firebase_auth
from firebase_admin import credentials
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import service_account

_CREDENTIAL_NAME = "hhipsystemv0-firebase-adminsdk-fbsvc-ea612cea5c.json"
_PRODUCTION_CREDENTIAL_NAME = "firebase-adminsdk.json"
_MANAGE_SCOPES = (
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/firebase",
)
_web_config: dict[str, str] | None = None


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _workspace_root() -> Path:
    return Path(__file__).resolve().parents[3]


def load_auth_env() -> None:
    for path in (
        _backend_root() / "credentials" / "auth.env",
        _workspace_root() / ".env" / "auth.env",
    ):
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, _, value = stripped.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
        return


def credential_path() -> Path:
    for env_name in ("FIREBASE_CREDENTIALS", "GOOGLE_APPLICATION_CREDENTIALS"):
        env = os.environ.get(env_name)
        if env:
            path = Path(env)
            if path.is_file():
                return path
    candidates = (
        _backend_root() / "credentials" / _PRODUCTION_CREDENTIAL_NAME,
        _backend_root() / "credentials" / _CREDENTIAL_NAME,
        _workspace_root() / ".env" / _CREDENTIAL_NAME,
    )
    for path in candidates:
        if path.is_file():
            return path
    return candidates[0]


def init_firebase() -> None:
    load_auth_env()
    try:
        firebase_admin.get_app()
        return
    except ValueError:
        pass
    path = credential_path()
    if not path.is_file():
        raise FileNotFoundError(f"Firebase admin credentials not found: {path}")
    firebase_admin.initialize_app(credentials.Certificate(str(path)))


def _env_web_config() -> dict[str, str] | None:
    api_key = os.environ.get("FIREBASE_API_KEY")
    project_id = os.environ.get("FIREBASE_PROJECT_ID")
    if not api_key or not project_id:
        return None
    return {
        "apiKey": api_key,
        "authDomain": os.environ.get("FIREBASE_AUTH_DOMAIN") or f"{project_id}.firebaseapp.com",
        "projectId": project_id,
        "appId": os.environ.get("FIREBASE_APP_ID") or "",
    }


def _fetch_web_config() -> dict[str, str]:
    path = credential_path()
    info = json.loads(path.read_text(encoding="utf-8"))
    project_id = info["project_id"]
    creds = service_account.Credentials.from_service_account_file(str(path), scopes=_MANAGE_SCOPES)
    creds.refresh(GoogleRequest())
    headers = {"Authorization": f"Bearer {creds.token}"}
    list_url = f"https://firebase.googleapis.com/v1beta1/projects/{project_id}/webApps"
    with urlopen(Request(list_url, headers=headers), timeout=20) as res:
        apps = json.loads(res.read().decode("utf-8")).get("apps") or []
    if not apps:
        raise RuntimeError("No Firebase web apps on this project")
    app_id = apps[0]["appId"]
    cfg_url = (
        f"https://firebase.googleapis.com/v1beta1/projects/{project_id}/webApps/"
        f"{quote(app_id, safe='')}/config"
    )
    with urlopen(Request(cfg_url, headers=headers), timeout=20) as res:
        raw = json.loads(res.read().decode("utf-8"))
    return {
        "apiKey": raw["apiKey"],
        "authDomain": raw["authDomain"],
        "projectId": raw["projectId"],
        "appId": raw["appId"],
    }


def firebase_web_config() -> dict[str, str]:
    global _web_config
    if _web_config is not None:
        return _web_config
    load_auth_env()
    _web_config = _env_web_config() or _fetch_web_config()
    return _web_config


def sync_firebase_user(email: str, name: str, picture: str | None) -> str:
    try:
        record = firebase_auth.get_user_by_email(email)
        updates: dict[str, str] = {}
        if name and record.display_name != name:
            updates["display_name"] = name
        if picture and record.photo_url != picture:
            updates["photo_url"] = picture
        if updates:
            record = firebase_auth.update_user(record.uid, **updates)
        return record.uid
    except firebase_auth.UserNotFoundError:
        record = firebase_auth.create_user(
            email=email,
            display_name=name or None,
            photo_url=picture or None,
            email_verified=True,
        )
        return record.uid
