"""Sign-in and the signed-in person's own record.

Contract: docs/accounts-and-profile.md in jumetra-frontend. Every route below
answers errors as FastAPI's ``{"detail": "..."}``.

    GET    /auth/config          Firebase web config for the sign-in popup
    POST   /auth/google          Firebase ID token -> Kiungo session
    POST   /auth/github          Firebase ID token -> Kiungo session
    POST   /auth/link-provider   attach a second sign-in method
    POST   /auth/refresh         rotate the refresh token
    POST   /auth/logout          revoke every session of the account
    POST   /auth/ws-ticket       a 30 s ticket for a WebSocket
    GET    /auth/me              the person, with profile fields
    PATCH  /auth/me              edit the profile
    DELETE /auth/me              delete the account and its data (204)
    GET    /auth/users/search    find teammates by name or email

The account's projects, lab sessions and learning progress are in
``auth/account_routes.py``.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, sessionmaker

from api.db.models import User
from database.models import UserProfile, WebSocketTicket
from database.service import (
    EmailTaken,
    ProviderConflict,
    create_login_records,
    delete_user,
    get_valid_access,
    get_valid_refresh,
    link_provider,
    revoke_user_sessions,
    rotate_refresh,
    upsert_provider_user,
    user_payload,
)

from . import firebase
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

Provider = Literal["google", "github"]
SELF_ROLES = ("student", "researcher", "technician", "instructor", "club_lead", "school_admin", "hobbyist", "other")


class TokenBody(BaseModel):
    id_token: str = Field(min_length=1)


class LinkBody(TokenBody):
    provider: Provider


class RefreshBody(BaseModel):
    refresh_token: str | None = None


class ProfilePatch(BaseModel):
    """Any subset of the editable fields. ``null`` or ``""`` clears a field."""

    display_name: str | None = None
    role: str | None = None
    role_other: str | None = None
    organization: str | None = None
    location: str | None = None
    bio: str | None = None

    @field_validator("display_name")
    @classmethod
    def _display_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Display name can't be empty.")
        if len(value) > 80:
            raise ValueError("Display name must be 80 characters or fewer.")
        return value

    @field_validator("role")
    @classmethod
    def _role(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        if value not in SELF_ROLES:
            raise ValueError("Choose a role from the list.")
        return value

    @field_validator("role_other", "organization", "location", "bio")
    @classmethod
    def _trimmed(cls, value: str | None, info) -> str | None:
        limits = {"role_other": 80, "organization": 120, "location": 80, "bio": 280}
        if value is None:
            return None
        value = value.strip()
        if not value:
            return None
        limit = limits[info.field_name]
        if len(value) > limit:
            raise ValueError(f"{info.field_name.replace('_', ' ').capitalize()} must be {limit} characters or fewer.")
        return value


# ----- helpers -----


def _factory(request: Request) -> sessionmaker[Session]:
    return request.app.state.db_factory


def _secret(request: Request) -> str:
    return request.app.state.session_secret


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


def _session_payload(session: Session, user: User, access: str, refresh: str) -> dict[str, Any]:
    payload = user_payload(user, session)
    payload["access_token"] = access
    payload["refresh_token"] = refresh
    payload["token_type"] = "Bearer"
    payload["user"] = user_payload(user, session)
    return payload


def verify_provider_token(token: str, provider: Provider) -> dict[str, Any]:
    """A verified Firebase token that signed in with ``provider``."""
    try:
        claims = firebase.verify_id_token(token)
    except firebase.FirebaseUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # firebase_admin raises several classes
        raise HTTPException(status_code=401, detail="That sign-in token isn't valid. Try signing in again.") from exc
    signed_in = (claims.get("firebase") or {}).get("sign_in_provider")
    if signed_in != firebase.provider_claim(provider):
        label = "GitHub" if provider == "github" else "Google"
        raise HTTPException(status_code=400, detail=f"That token didn't come from {label} sign-in.")
    if not claims.get("email"):
        label = "GitHub" if provider == "github" else "Google"
        raise HTTPException(status_code=400, detail=f"Your {label} account has no email address we can use.")
    return claims


def _identity(claims: dict[str, Any], provider: Provider) -> dict[str, Any]:
    identities = ((claims.get("firebase") or {}).get("identities") or {}).get(firebase.provider_claim(provider)) or []
    provider_user_id = str(identities[0]) if identities else str(claims.get("sub") or claims.get("uid") or "")
    if not provider_user_id:
        raise HTTPException(status_code=400, detail="That sign-in token has no account identifier.")
    email = str(claims["email"])
    return {
        "email": email,
        "email_verified": bool(claims.get("email_verified")),
        "name": claims.get("name") or claims.get("display_name") or email.split("@")[0],
        "picture": claims.get("picture"),
        "provider_user_id": provider_user_id,
        "firebase_uid": str(claims.get("uid") or claims.get("sub") or "") or None,
    }


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
    return _session_payload(session, user, access, refresh)


def _read_refresh(request: Request, body: RefreshBody | None = None) -> str | None:
    if body and body.refresh_token:
        return body.refresh_token.strip() or None
    header = request.headers.get("x-refresh-token")
    if header:
        return header.strip() or None
    return request.cookies.get(REFRESH_COOKIE)


def _user_from_access(request: Request, session: Session, access: str) -> User | None:
    try:
        payload = decode_access(access, _secret(request))
    except Exception:
        return None
    if payload.get("typ") not in (None, "access"):
        return None
    if not get_valid_access(session, payload.get("jti", ""), payload["sub"]):
        return None
    return session.get(User, payload["sub"])


def _rotate_session(request: Request, response: Response, session: Session, refresh_raw: str) -> dict[str, Any]:
    row = get_valid_refresh(session, refresh_raw)
    if row is None:
        clear_auth_cookies(response)
        raise HTTPException(status_code=401, detail="Your session has expired. Sign in again.")
    user = session.get(User, row.user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Not signed in.")
    new_access, jti, access_exp = issue_access(user.id, _secret(request))
    new_refresh, refresh_exp = issue_refresh()
    rotate_refresh(session, row, access_jti=jti, access_expires=access_exp, refresh_raw=new_refresh, refresh_expires=refresh_exp)
    session.commit()
    set_auth_cookies(response, new_access, new_refresh)
    return _session_payload(session, user, new_access, new_refresh)


def current_user_id(request: Request, response: Response) -> str:
    """The signed-in person's id, from the bearer token, the access cookie or a refresh."""
    factory = _factory(request)
    access = bearer_token(request) or request.cookies.get(ACCESS_COOKIE)
    refresh = _read_refresh(request)
    with factory() as session:
        if access:
            user = _user_from_access(request, session, access)
            if user is not None:
                return user.id
        if not refresh:
            raise HTTPException(status_code=401, detail="Not signed in.")
        return _rotate_session(request, response, session, refresh)["id"]


def current_user(request: Request, response: Response) -> dict[str, Any]:
    """The signed-in person as the website reads them. Used by the middleware too."""
    user_id = current_user_id(request, response)
    with _factory(request)() as session:
        user = session.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=401, detail="Not signed in.")
        return user_payload(user, session)


# ----- routes -----


@router.get("/config")
def auth_config() -> dict[str, str]:
    try:
        return firebase.firebase_web_config()
    except firebase.FirebaseUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _sign_in(provider: Provider, body: TokenBody, request: Request, response: Response) -> dict[str, Any]:
    claims = verify_provider_token(body.id_token, provider)
    identity = _identity(claims, provider)
    with _factory(request)() as session:
        try:
            user = upsert_provider_user(session, provider=provider, **identity)
        except EmailTaken as exc:
            label = "GitHub" if provider == "github" else "Google"
            raise HTTPException(
                status_code=409,
                detail=f"An account already uses {exc}. Sign in the way you did before, then connect {label} from your profile.",
            ) from exc
        return _write_session(request, response, session, user)


@router.post("/google")
def google_login(body: TokenBody, request: Request, response: Response) -> dict[str, Any]:
    return _sign_in("google", body, request, response)


@router.post("/github")
def github_login(body: TokenBody, request: Request, response: Response) -> dict[str, Any]:
    return _sign_in("github", body, request, response)


@router.post("/link-provider")
def link_provider_route(
    body: LinkBody,
    request: Request,
    response: Response,
    user_id: str = Depends(current_user_id),
) -> dict[str, Any]:
    claims = verify_provider_token(body.id_token, body.provider)
    identity = _identity(claims, body.provider)
    with _factory(request)() as session:
        user = session.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=401, detail="Not signed in.")
        if user.firebase_uid and identity["firebase_uid"] and user.firebase_uid != identity["firebase_uid"]:
            raise HTTPException(status_code=409, detail="That sign-in belongs to a different account. Sign in with it instead.")
        try:
            link_provider(
                session,
                user,
                provider=body.provider,
                provider_user_id=identity["provider_user_id"],
                email=identity["email"],
            )
        except ProviderConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if not user.firebase_uid and identity["firebase_uid"]:
            user.firebase_uid = identity["firebase_uid"]
        session.commit()
        return user_payload(user, session)


@router.post("/refresh")
def refresh_session(request: Request, response: Response, body: RefreshBody | None = None) -> dict[str, Any]:
    refresh = _read_refresh(request, body)
    if not refresh:
        raise HTTPException(status_code=401, detail="Not signed in.")
    with _factory(request)() as session:
        return _rotate_session(request, response, session, refresh)


@router.post("/ws-ticket")
def create_websocket_ticket(request: Request, response: Response, user_id: str = Depends(current_user_id)) -> dict[str, Any]:
    ticket, jti, expires = issue_websocket_ticket(user_id, _secret(request))
    with _factory(request)() as session:
        session.add(WebSocketTicket(jti=jti, user_id=user_id, expires_at=expires))
        session.commit()
    return {"ticket": ticket, "expires_in": 30}


@router.get("/me")
def me(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    return user


@router.patch("/me")
def patch_me(body: ProfilePatch, request: Request, user_id: str = Depends(current_user_id)) -> dict[str, Any]:
    sent = body.model_dump(exclude_unset=True)
    with _factory(request)() as session:
        user = session.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=401, detail="Not signed in.")
        profile = session.scalar(select(UserProfile).where(UserProfile.user_id == user.id))
        if profile is None:
            profile = UserProfile(user_id=user.id)
            session.add(profile)
        if "display_name" in sent and sent["display_name"]:
            user.display_name = sent["display_name"]
        if "role" in sent:
            profile.self_role = sent["role"]
        if "role_other" in sent:
            profile.role_other = sent["role_other"]
        if profile.self_role == "other" and not profile.role_other:
            raise HTTPException(status_code=422, detail="Say what your role is when you pick Other.")
        if profile.self_role != "other":
            profile.role_other = None
        for name in ("organization", "location", "bio"):
            if name in sent:
                setattr(profile, name, sent[name])
        session.commit()
        return user_payload(user, session)


@router.delete("/me", status_code=204)
def delete_me(request: Request, response: Response, user_id: str = Depends(current_user_id)) -> Response:
    with _factory(request)() as session:
        user = session.get(User, user_id)
        if user is not None:
            delete_user(session, user)
            session.commit()
    clear_auth_cookies(response)
    return Response(status_code=204, headers=dict(response.headers))


@router.get("/users/search")
def search_users(
    request: Request,
    q: str = Query(default="", max_length=120),
    _: str = Depends(current_user_id),
) -> list[dict[str, str]]:
    """Teammates for a project: people who have signed in, whose name or email starts with ``q``."""
    needle = q.strip().lower()
    if len(needle) < 2:
        return []
    with _factory(request)() as session:
        rows = session.scalars(
            select(User)
            .where(User.last_login_at.is_not(None))
            .where(or_(func.lower(User.display_name).like(f"{needle}%"), func.lower(User.email).like(f"{needle}%")))
            .order_by(User.display_name)
            .limit(10)
        ).all()
        return [{"id": u.id, "display_name": u.display_name, "email": u.email} for u in rows]


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
