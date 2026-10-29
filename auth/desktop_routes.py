"""Desktop sign-in (jumetra-frontend #62; Phase Two DSK-01 to DSK-03).

The desktop app never sees a Firebase popup. It signs in through the website
and comes back with a code, PKCE-protected (RFC 7636):

    1. App:      POST /auth/desktop/codes { code_challenge, device }  -> code_id, authorize_url
    2. App:      opens authorize_url in the browser
    3. Website:  the person signs in as usual, then
                 POST /auth/desktop/codes/{code_id}/approve  (bearer) -> redirect_url
                 and the browser opens  kiungo://signin?code=...&code_id=...
    4. App:      POST /auth/desktop/token { code, code_verifier }     -> tokens + device
    5. App:      POST /auth/desktop/refresh { refresh_token }         -> rotated tokens
                 POST /auth/desktop/logout  { refresh_token }         -> device revoked

If the kiungo:// handoff doesn't fire (some Linux desktops), the app polls
GET /auth/desktop/codes/{code_id} instead: once approved it carries the code.
The code is useless without the verifier the app kept, so polling by code_id
gives nothing away.

A device is one installation. Its sessions end when the person removes it
(DELETE /auth/me/devices/{id}) or when a spent refresh token is replayed.
"""

from __future__ import annotations

import base64
import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from api.db.models import User
from database.models import AccessToken, DesktopAuthCode, Device, RefreshToken
from database.service import hash_token, user_payload

from .routes import current_user_id
from .tokens import ACCESS_TTL, REFRESH_TTL, issue_access, issue_refresh

router = APIRouter(prefix="/auth/desktop", tags=["desktop sign-in"])
my_devices_router = APIRouter(prefix="/auth/me/devices", tags=["desktop sign-in"])

CODE_TTL = timedelta(minutes=10)
POLL_INTERVAL_SECONDS = 3
DEFAULT_REDIRECT = "kiungo://signin"
ALLOWED_REDIRECTS = ("kiungo://signin", "http://127.0.0.1", "http://localhost")
Platform = Literal["windows", "linux", "macos"]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _factory(request: Request) -> sessionmaker[Session]:
    return request.app.state.db_factory


def _secret(request: Request) -> str:
    return request.app.state.session_secret


def website_url() -> str:
    """Where the sign-in page lives. The website's own origin in production."""
    return os.environ.get("KIUNGO_WEBSITE_URL", "https://jumetra-frontendv0.vercel.app").rstrip("/")


class DeviceInfo(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    platform: Platform
    app_version: str = Field(default="", max_length=32)


class CodeRequest(BaseModel):
    code_challenge: str = Field(min_length=43, max_length=128)
    code_challenge_method: Literal["S256"] = "S256"
    device: DeviceInfo
    redirect_uri: str = Field(default=DEFAULT_REDIRECT, max_length=256)

    @field_validator("redirect_uri")
    @classmethod
    def _redirect(cls, value: str) -> str:
        if not any(value == allowed or value.startswith(allowed + ":") or value.startswith(allowed + "/") for allowed in ALLOWED_REDIRECTS):
            raise ValueError("The app can only return to kiungo://signin or a local loopback address.")
        return value


class TokenRequest(BaseModel):
    code: str = Field(min_length=1, max_length=128)
    code_verifier: str = Field(min_length=43, max_length=128)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1, max_length=256)


def _device_payload(device: Device) -> dict[str, Any]:
    return {
        "id": device.id,
        "name": device.name,
        "platform": device.platform,
        "app_version": device.app_version,
        "created_at": device.created_at.isoformat(),
        "last_seen_at": device.last_seen_at.isoformat(),
        "revoked": device.revoked_at is not None,
    }


def _expire_if_due(row: DesktopAuthCode) -> None:
    if row.status in ("pending", "approved") and _aware(row.expires_at) < _utcnow():
        row.status = "expired"


def _issue_device_tokens(request: Request, session: Session, user: User, device: Device) -> dict[str, Any]:
    access, jti, access_exp = issue_access(user.id, _secret(request), client="desktop", device_id=device.id)
    refresh, refresh_exp = issue_refresh()
    session.add(AccessToken(user_id=user.id, jti=jti, expires_at=access_exp, device_id=device.id))
    session.add(RefreshToken(user_id=user.id, token_hash=hash_token(refresh), expires_at=refresh_exp, client="desktop", device_id=device.id))
    device.last_seen_at = _utcnow()
    session.commit()
    return {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "Bearer",
        "expires_in": int(ACCESS_TTL.total_seconds()),
        "refresh_expires_in": int(REFRESH_TTL.total_seconds()),
        "device": _device_payload(device),
        "user": user_payload(user, session),
    }


def _revoke_device(session: Session, device: Device) -> None:
    now = _utcnow()
    if device.revoked_at is None:
        device.revoked_at = now
    for model in (RefreshToken, AccessToken):
        for row in session.scalars(select(model).where(model.device_id == device.id, model.revoked.is_(False))):
            row.revoked = True


# ----- the app's side -----


@router.post("/codes", status_code=201)
def create_code(body: CodeRequest, request: Request) -> dict[str, Any]:
    with _factory(request)() as session:
        row = DesktopAuthCode(
            code_challenge=body.code_challenge,
            code_challenge_method=body.code_challenge_method,
            redirect_uri=body.redirect_uri,
            device_name=body.device.name,
            device_platform=body.device.platform,
            app_version=body.device.app_version,
            expires_at=_utcnow() + CODE_TTL,
        )
        session.add(row)
        session.commit()
        code_id = row.id
    return {
        "code_id": code_id,
        "authorize_url": f"{website_url()}/desktop/sign-in?{urlencode({'code_id': code_id})}",
        "expires_in": int(CODE_TTL.total_seconds()),
        "poll_interval": POLL_INTERVAL_SECONDS,
    }


@router.get("/codes/{code_id}")
def code_status(code_id: str, request: Request) -> dict[str, Any]:
    with _factory(request)() as session:
        row = session.get(DesktopAuthCode, code_id)
        if row is None:
            raise HTTPException(status_code=404, detail="That sign-in attempt doesn't exist.")
        _expire_if_due(row)
        session.commit()
        answer: dict[str, Any] = {"status": row.status}
        if row.status == "approved" and row.code_hash:
            answer["code"] = _pending_codes(request).pop(code_id, None)
            if answer["code"] is None:
                # The code was already handed over through the redirect; polling can't get it twice.
                answer.pop("code")
        return answer


def _pending_codes(request: Request) -> dict[str, str]:
    """Plain codes waiting to be collected by a poll, kept only in memory and only until collected."""
    store = getattr(request.app.state, "desktop_pending_codes", None)
    if store is None:
        store = {}
        request.app.state.desktop_pending_codes = store
    return store


@router.post("/token")
def exchange_code(body: TokenRequest, request: Request) -> dict[str, Any]:
    digest = base64.urlsafe_b64encode(hashlib.sha256(body.code_verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
    with _factory(request)() as session:
        row = session.scalar(select(DesktopAuthCode).where(DesktopAuthCode.code_hash == hash_token(body.code)))
        if row is None:
            raise HTTPException(status_code=400, detail="That sign-in code isn't valid. Start the sign-in again from the app.")
        _expire_if_due(row)
        if row.status != "approved":
            session.commit()
            raise HTTPException(status_code=400, detail="That sign-in code was already used or has expired. Start the sign-in again from the app.")
        if not secrets.compare_digest(digest, row.code_challenge):
            # Wrong verifier: somebody else has the code. Burn it.
            row.status = "denied"
            session.commit()
            raise HTTPException(status_code=400, detail="That sign-in code doesn't belong to this app. Start the sign-in again.")
        user = session.get(User, row.user_id) if row.user_id else None
        if user is None:
            raise HTTPException(status_code=400, detail="That sign-in is no longer valid.")
        device = Device(user_id=user.id, name=row.device_name, platform=row.device_platform, app_version=row.app_version)
        session.add(device)
        session.flush()
        row.status = "exchanged"
        row.exchanged_at = _utcnow()
        row.device_id = device.id
        _pending_codes(request).pop(row.id, None)
        return _issue_device_tokens(request, session, user, device)


@router.post("/refresh")
def refresh_desktop(body: RefreshRequest, request: Request) -> dict[str, Any]:
    with _factory(request)() as session:
        row = session.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_token(body.refresh_token)))
        if row is None or row.client != "desktop" or row.device_id is None:
            raise HTTPException(status_code=401, detail="Sign in again.")
        device = session.get(Device, row.device_id)
        if device is None:
            raise HTTPException(status_code=401, detail="Sign in again.")
        if row.revoked:
            # A spent token came back: the token was copied. End every session of this device.
            _revoke_device(session, device)
            session.commit()
            raise HTTPException(status_code=401, detail="This sign-in was used somewhere else, so it has been ended. Sign in again.")
        if device.revoked_at is not None or _aware(row.expires_at) < _utcnow():
            raise HTTPException(status_code=401, detail="Sign in again.")
        user = session.get(User, row.user_id)
        if user is None:
            raise HTTPException(status_code=401, detail="Sign in again.")
        row.revoked = True
        return _issue_device_tokens(request, session, user, device)


@router.post("/logout")
def logout_desktop(body: RefreshRequest, request: Request) -> dict[str, str]:
    with _factory(request)() as session:
        row = session.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_token(body.refresh_token)))
        if row is not None and row.device_id:
            device = session.get(Device, row.device_id)
            if device is not None:
                _revoke_device(session, device)
            session.commit()
    return {"status": "ok"}


# ----- the website's side -----


def _owned_pending(session: Session, code_id: str) -> DesktopAuthCode:
    row = session.get(DesktopAuthCode, code_id)
    if row is None:
        raise HTTPException(status_code=404, detail="That sign-in attempt doesn't exist. Start again from the app.")
    _expire_if_due(row)
    if row.status != "pending":
        session.commit()
        raise HTTPException(status_code=409, detail="That sign-in attempt has already been answered or has expired. Start again from the app.")
    return row


@router.get("/codes/{code_id}/details")
def code_details(code_id: str, request: Request, _: str = Depends(current_user_id)) -> dict[str, Any]:
    """What the website shows before asking "Sign in to Kiungo on this computer?"."""
    with _factory(request)() as session:
        row = session.get(DesktopAuthCode, code_id)
        if row is None:
            raise HTTPException(status_code=404, detail="That sign-in attempt doesn't exist. Start again from the app.")
        _expire_if_due(row)
        session.commit()
        return {
            "code_id": row.id,
            "status": row.status,
            "device": {"name": row.device_name, "platform": row.device_platform, "app_version": row.app_version},
            "expires_at": _aware(row.expires_at).isoformat(),
        }


@router.post("/codes/{code_id}/approve")
def approve_code(code_id: str, request: Request, user_id: str = Depends(current_user_id)) -> dict[str, Any]:
    code = secrets.token_urlsafe(32)
    with _factory(request)() as session:
        row = _owned_pending(session, code_id)
        row.status = "approved"
        row.user_id = user_id
        row.approved_at = _utcnow()
        row.code_hash = hash_token(code)
        session.commit()
        _pending_codes(request)[row.id] = code
        redirect = row.redirect_uri
    return {"status": "approved", "redirect_url": f"{redirect}?{urlencode({'code': code, 'code_id': code_id})}"}


@router.post("/codes/{code_id}/deny")
def deny_code(code_id: str, request: Request, _: str = Depends(current_user_id)) -> dict[str, str]:
    with _factory(request)() as session:
        row = _owned_pending(session, code_id)
        row.status = "denied"
        session.commit()
    return {"status": "denied"}


# ----- devices (Sprint 3: list and revoke) -----


@my_devices_router.get("")
def list_devices(request: Request, user_id: str = Depends(current_user_id)) -> list[dict[str, Any]]:
    with _factory(request)() as session:
        rows = session.scalars(select(Device).where(Device.user_id == user_id).order_by(Device.last_seen_at.desc())).all()
        return [_device_payload(d) for d in rows]


@my_devices_router.delete("/{device_id}")
def revoke_device(device_id: str, request: Request, user_id: str = Depends(current_user_id)) -> dict[str, bool]:
    with _factory(request)() as session:
        device = session.get(Device, device_id)
        if device is None or device.user_id != user_id:
            raise HTTPException(status_code=404, detail="That device isn't on your account.")
        _revoke_device(session, device)
        session.commit()
    return {"revoked": True}
