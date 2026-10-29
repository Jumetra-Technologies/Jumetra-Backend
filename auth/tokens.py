from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
from fastapi import Response

ACCESS_COOKIE = "hhip_access"
REFRESH_COOKIE = "hhip_refresh"
ACCESS_TTL = timedelta(minutes=15)
REFRESH_TTL = timedelta(days=30)
WEBSOCKET_TICKET_TTL = timedelta(seconds=30)


def session_secret(data_dir: Path) -> str:
    env = os.environ.get("SESSION_SECRET")
    if env:
        return env
    path = Path(data_dir) / ".session_secret"
    if path.is_file():
        return path.read_text(encoding="utf-8").strip()
    value = secrets.token_urlsafe(48)
    path.write_text(value, encoding="utf-8")
    return value


def issue_access(user_id: str, secret: str) -> tuple[str, str, datetime]:
    jti = secrets.token_hex(16)
    expires = datetime.now(timezone.utc) + ACCESS_TTL
    token = jwt.encode(
        {"sub": user_id, "jti": jti, "exp": expires, "typ": "access"},
        secret,
        algorithm="HS256",
    )
    return token, jti, expires


def issue_refresh() -> tuple[str, datetime]:
    return secrets.token_urlsafe(48), datetime.now(timezone.utc) + REFRESH_TTL


def decode_access(token: str, secret: str) -> dict:
    return jwt.decode(token, secret, algorithms=["HS256"])


def bearer_token(request) -> str | None:
    header = request.headers.get("authorization") or request.headers.get("Authorization")
    if not header:
        return None
    scheme, _, value = header.partition(" ")
    if scheme.lower() != "bearer" or not value.strip():
        return None
    return value.strip()


def issue_websocket_ticket(user_id: str, secret: str) -> tuple[str, str, datetime]:
    jti = secrets.token_hex(16)
    expires = datetime.now(timezone.utc) + WEBSOCKET_TICKET_TTL
    ticket = jwt.encode(
        {"sub": user_id, "jti": jti, "exp": expires, "typ": "websocket"},
        secret,
        algorithm="HS256",
    )
    return ticket, jti, expires


def decode_websocket_ticket(ticket: str, secret: str) -> dict:
    payload = jwt.decode(ticket, secret, algorithms=["HS256"])
    if payload.get("typ") != "websocket":
        raise jwt.InvalidTokenError("Invalid websocket ticket")
    return payload


def cookie_secure() -> bool:
    return os.environ.get("COOKIE_SECURE", "").lower() in {"1", "true", "yes"}


def cookie_samesite() -> str:
    env = os.environ.get("COOKIE_SAMESITE")
    if env:
        return env.lower()
    return "none" if cookie_secure() else "lax"


def set_auth_cookies(response: Response, access: str, refresh: str) -> None:
    secure = cookie_secure()
    samesite = cookie_samesite()
    response.set_cookie(
        ACCESS_COOKIE,
        access,
        max_age=int(ACCESS_TTL.total_seconds()),
        httponly=True,
        samesite=samesite,
        secure=secure,
        path="/",
    )
    response.set_cookie(
        REFRESH_COOKIE,
        refresh,
        max_age=int(REFRESH_TTL.total_seconds()),
        httponly=True,
        samesite=samesite,
        secure=secure,
        path="/",
    )


def clear_auth_cookies(response: Response) -> None:
    secure = cookie_secure()
    samesite = cookie_samesite()
    response.delete_cookie(ACCESS_COOKIE, path="/", samesite=samesite, secure=secure)
    response.delete_cookie(REFRESH_COOKIE, path="/", samesite=samesite, secure=secure)
