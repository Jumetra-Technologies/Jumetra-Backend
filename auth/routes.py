from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from firebase_admin import auth as firebase_auth
from pydantic import BaseModel
from sqlalchemy.orm import Session, sessionmaker

from api.db.models import User
from database.models import WebSocketTicket
from database.service import (
    create_login_records,
    get_valid_access,
    get_valid_refresh,
    revoke_user_sessions,
    rotate_refresh,
    upsert_google_user,
    user_payload,
)

from .firebase import firebase_web_config, sync_firebase_user
from .tokens import (
    ACCESS_COOKIE,
    REFRESH_COOKIE,
    bearer_token,
    clear_auth_cookies,
    decode_access,
    issue_access,
    issue_refresh,
    issue_websocket_ticket,
    set_auth_cookies,
)

router = APIRouter(prefix="/auth", tags=["auth"])


class GoogleLoginBody(BaseModel):
    id_token: str


class RefreshBody(BaseModel):
    refresh_token: str | None = None


def _factory(request: Request) -> sessionmaker[Session]:
    return request.app.state.db_factory


def _secret(request: Request) -> str:
    return request.app.state.session_secret


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


def _session_payload(user: User, access: str, refresh: str) -> dict[str, Any]:
    payload = user_payload(user)
    payload["access_token"] = access
    payload["refresh_token"] = refresh
    payload["token_type"] = "Bearer"
    return payload


def verify_google_token(token: str) -> dict[str, Any]:
    try:
        decoded = firebase_auth.verify_id_token(token)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid Firebase token") from exc
    provider = (decoded.get("firebase") or {}).get("sign_in_provider")
    if provider != "google.com":
        raise HTTPException(status_code=400, detail="Google sign-in only")
    if not decoded.get("email"):
        raise HTTPException(status_code=400, detail="Google account has no email")
    return decoded


def _claims_to_identity(claims: dict[str, Any]) -> tuple[str, str, str | None, str]:
    email = str(claims["email"])
    name = claims.get("name") or claims.get("display_name") or email.split("@")[0]
    picture = claims.get("picture")
    sub = str(claims.get("sub") or claims.get("uid") or "")
    if not sub:
        raise HTTPException(status_code=400, detail="Google token missing subject")
    return email, name, picture, sub


def _write_session(request: Request, response: Response, session: Session, user: User) -> dict[str, Any]:
    access, jti, access_exp = issue_access(user.id, _secret(request))
    refresh, refresh_exp = issue_refresh()
    create_login_records(
        session,
        user,
        access_jti=jti,
        access_expires=access_exp,
        refresh_raw=refresh,
        refresh_expires=refresh_exp,
        cookie_expires=refresh_exp,
        user_agent=request.headers.get("user-agent"),
        ip_address=_client_ip(request),
    )
    session.commit()
    set_auth_cookies(response, access, refresh)
    return _session_payload(user, access, refresh)


def _read_refresh(request: Request, body: RefreshBody | None = None) -> str | None:
    if body and body.refresh_token:
        return body.refresh_token.strip() or None
    header = request.headers.get("x-refresh-token")
    if header:
        return header.strip() or None
    return request.cookies.get(REFRESH_COOKIE)


def _authenticate_access(request: Request, session: Session, access: str) -> dict[str, Any] | None:
    try:
        payload = decode_access(access, _secret(request))
    except Exception:
        return None
    if not get_valid_access(session, payload.get("jti", ""), payload["sub"]):
        return None
    user = session.get(User, payload["sub"])
    if user is None:
        return None
    return user_payload(user)


def _rotate_session(
    request: Request,
    response: Response,
    session: Session,
    refresh_raw: str,
) -> dict[str, Any]:
    row = get_valid_refresh(session, refresh_raw)
    if row is None:
        clear_auth_cookies(response)
        raise HTTPException(status_code=401, detail="Session expired")
    user = session.get(User, row.user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    new_access, jti, access_exp = issue_access(user.id, _secret(request))
    new_refresh, refresh_exp = issue_refresh()
    rotate_refresh(
        session,
        row,
        access_jti=jti,
        access_expires=access_exp,
        refresh_raw=new_refresh,
        refresh_expires=refresh_exp,
    )
    session.commit()
    set_auth_cookies(response, new_access, new_refresh)
    return _session_payload(user, new_access, new_refresh)


def current_user(request: Request, response: Response) -> dict[str, Any]:
    factory = _factory(request)
    access = bearer_token(request) or request.cookies.get(ACCESS_COOKIE)
    refresh = _read_refresh(request)
    with factory() as session:
        if access:
            user = _authenticate_access(request, session, access)
            if user is not None:
                return user
        if not refresh:
            raise HTTPException(status_code=401, detail="Not authenticated")
        session_payload = _rotate_session(request, response, session, refresh)
        return {
            "id": session_payload["id"],
            "email": session_payload["email"],
            "name": session_payload["name"],
            "photo_url": session_payload.get("photo_url"),
            "role": session_payload.get("role"),
            "firebase_uid": session_payload.get("firebase_uid"),
        }


@router.get("/config")
def auth_config() -> dict[str, str]:
    return firebase_web_config()


@router.post("/google")
def google_login(body: GoogleLoginBody, request: Request, response: Response) -> dict[str, Any]:
    claims = verify_google_token(body.id_token)
    email, name, picture, sub = _claims_to_identity(claims)
    firebase_uid = str(claims.get("uid") or "")
    if not firebase_uid:
        firebase_uid = sync_firebase_user(email, name, picture)
    with _factory(request)() as session:
        user = upsert_google_user(
            session,
            email=email,
            name=name,
            picture=picture,
            google_sub=sub,
            firebase_uid=firebase_uid,
        )
        return _write_session(request, response, session, user)


@router.post("/refresh")
def refresh_session(
    request: Request,
    response: Response,
    body: RefreshBody | None = None,
) -> dict[str, Any]:
    refresh = _read_refresh(request, body)
    if not refresh:
        raise HTTPException(status_code=401, detail="Not authenticated")
    with _factory(request)() as session:
        return _rotate_session(request, response, session, refresh)


@router.post("/ws-ticket")
def create_websocket_ticket(
    request: Request,
    response: Response,
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    ticket, jti, expires = issue_websocket_ticket(user["id"], _secret(request))
    with _factory(request)() as session:
        session.add(WebSocketTicket(jti=jti, user_id=user["id"], expires_at=expires))
        session.commit()
    return {"ticket": ticket, "expires_in": 30}


@router.get("/me")
def me(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    return user


@router.post("/logout")
def logout(request: Request, response: Response, body: RefreshBody | None = None) -> dict[str, str]:
    access = bearer_token(request) or request.cookies.get(ACCESS_COOKIE)
    refresh = _read_refresh(request, body)
    with _factory(request)() as session:
        user_id = None
        if access:
            try:
                user_id = decode_access(access, _secret(request)).get("sub")
            except Exception:
                pass
        if user_id is None and refresh:
            row = get_valid_refresh(session, refresh)
            if row:
                user_id = row.user_id
        if user_id:
            revoke_user_sessions(session, user_id)
            session.commit()
    clear_auth_cookies(response)
    return {"status": "ok"}
