from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import jwt
import requests
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from sqlalchemy import select

from api.db.init_db import get_database_url
from api.db.models import Organization, User

router = APIRouter(prefix="/auth", tags=["auth"])
security = HTTPBearer(auto_error=False)


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise HTTPException(status_code=500, detail=f"{name} is not configured")
    return value


def _get_db_factory(request: Request):
    return request.app.state.db_factory


def _token_for_user(user: User) -> str:
    secret = os.environ.get("JWT_SECRET_KEY")
    if not secret:
        raise RuntimeError("JWT_SECRET_KEY is not configured")

    payload = {
        "sub": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "exp": datetime.now(timezone.utc) + timedelta(hours=12),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def _ensure_org(session: Any) -> Organization:
    org = session.scalar(select(Organization).limit(1))
    if org is not None:
        return org

    org = Organization(name="HHIP Research Lab", slug="hhip-lab")
    session.add(org)
    session.flush()
    return org


@router.get("/google/login")
def google_login() -> RedirectResponse:
    client_id = _required_env("GOOGLE_CLIENT_ID")
    redirect_uri = _required_env("GOOGLE_REDIRECT_URI")

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "consent",
    }
    query = urlencode(params)
    url = f"https://accounts.google.com/o/oauth2/v2/auth?{query}"
    return RedirectResponse(url=url, status_code=302)


@router.get("/google/callback")
def google_callback(request: Request, code: str | None = None) -> dict[str, Any]:
    if not code:
        raise HTTPException(status_code=400, detail="Missing Google auth code")

    client_id = _required_env("GOOGLE_CLIENT_ID")
    client_secret = _required_env("GOOGLE_CLIENT_SECRET")
    redirect_uri = _required_env("GOOGLE_REDIRECT_URI")

    token_response = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
        timeout=30,
    )
    if token_response.status_code != 200:
        raise HTTPException(status_code=401, detail="Google token exchange failed")

    token_data = token_response.json()
    token = token_data.get("id_token")
    if not token:
        raise HTTPException(status_code=401, detail="Google returned no id_token")

    try:
        payload = id_token.verify_oauth2_token(
            token,
            google_requests.Request(),
            client_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Invalid Google token") from exc

    db_factory = request.app.state.db_factory
    with db_factory() as session:
        org = _ensure_org(session)
        existing = session.scalar(select(User).where(User.google_sub == payload["sub"]))
        if existing is None:
            existing = session.scalar(select(User).where(User.email == payload["email"]))

        if existing is None:
            existing = User(
                email=payload["email"],
                display_name=payload.get("name") or payload["email"],
                google_sub=payload["sub"],
                picture_url=payload.get("picture"),
                organization_id=org.id,
            )
            session.add(existing)
            session.flush()
        else:
            existing.display_name = payload.get("name") or existing.display_name
            existing.picture_url = payload.get("picture") or existing.picture_url
            existing.google_sub = payload["sub"] if not existing.google_sub else existing.google_sub
            session.flush()

        session.commit()
        access_token = _token_for_user(existing)
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user": {
                "id": existing.id,
                "email": existing.email,
                "display_name": existing.display_name,
                "google_sub": existing.google_sub,
                "picture_url": existing.picture_url,
            },
        }


@router.get("/me")
def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict[str, Any]:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Authentication required")

    token = credentials.credentials
    secret = os.environ.get("JWT_SECRET_KEY")
    if not secret:
        raise HTTPException(status_code=500, detail="JWT not configured")

    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc

    db_factory = request.app.state.db_factory
    with db_factory() as session:
        user = session.get(User, payload.get("sub"))
        if user is None:
            raise HTTPException(status_code=401, detail="User not found")
        return {
            "id": user.id,
            "email": user.email,
            "display_name": user.display_name,
            "google_sub": user.google_sub,
            "picture_url": user.picture_url,
        }
