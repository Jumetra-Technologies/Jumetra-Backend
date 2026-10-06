from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import inspect, select, text, update
from sqlalchemy.orm import Session, sessionmaker

from api.db.base import Base
from api.db.enums import Role
from api.db.models import Organization, User

from .models import (
    AccessToken,
    CookieSession,
    LoginSession,
    OAuthAccount,
    RefreshToken,
    UserProfile,
    WebSocketTicket,
)

_USER_COLUMNS = {
    "firebase_uid": "ALTER TABLE users ADD COLUMN firebase_uid VARCHAR(128)",
    "photo_url": "ALTER TABLE users ADD COLUMN photo_url VARCHAR(512)",
    "last_login_at": "ALTER TABLE users ADD COLUMN last_login_at DATETIME",
}


def ensure_identity_schema(factory: sessionmaker[Session]) -> None:
    engine = factory.kw["bind"]
    inspector = inspect(engine)
    if "users" in inspector.get_table_names():
        existing = {col["name"] for col in inspector.get_columns("users")}
        with engine.begin() as conn:
            for name, ddl in _USER_COLUMNS.items():
                if name not in existing:
                    conn.execute(text(ddl))
    Base.metadata.create_all(engine)


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def default_organization(session: Session) -> Organization:
    org = session.scalar(select(Organization).limit(1))
    if org:
        return org
    org = Organization(name="HHIP", slug="hhip")
    session.add(org)
    session.flush()
    return org


def upsert_google_user(
    session: Session,
    *,
    email: str,
    name: str,
    picture: str | None,
    google_sub: str,
    firebase_uid: str | None,
) -> User:
    user = None
    if firebase_uid:
        user = session.scalar(select(User).where(User.firebase_uid == firebase_uid))
    if user is None:
        user = session.scalar(select(User).where(User.email == email))
    if user is None:
        org = default_organization(session)
        user = User(
            email=email,
            display_name=name or email.split("@")[0],
            role=Role.RESEARCHER.value,
            organization_id=org.id,
            firebase_uid=firebase_uid,
            photo_url=picture,
        )
        session.add(user)
        session.flush()
    else:
        user.display_name = name or user.display_name
        if picture:
            user.photo_url = picture
        if firebase_uid and not user.firebase_uid:
            user.firebase_uid = firebase_uid
    user.last_login_at = datetime.now(timezone.utc)

    profile = session.scalar(select(UserProfile).where(UserProfile.user_id == user.id))
    if profile is None:
        session.add(UserProfile(user_id=user.id, avatar_url=picture))
    elif picture:
        profile.avatar_url = picture

    oauth = session.scalar(
        select(OAuthAccount).where(
            OAuthAccount.provider == "google",
            OAuthAccount.provider_user_id == google_sub,
        )
    )
    if oauth is None:
        session.add(
            OAuthAccount(
                user_id=user.id,
                provider="google",
                provider_user_id=google_sub,
                email=email,
            )
        )
    return user


def create_login_records(
    session: Session,
    user: User,
    *,
    access_jti: str,
    access_expires: datetime,
    refresh_raw: str,
    refresh_expires: datetime,
    cookie_expires: datetime,
    user_agent: str | None,
    ip_address: str | None,
) -> tuple[LoginSession, CookieSession]:
    login = LoginSession(user_id=user.id, user_agent=user_agent, ip_address=ip_address)
    session.add(login)
    session.flush()
    cookie = CookieSession(
        user_id=user.id,
        login_session_id=login.id,
        expires_at=cookie_expires,
    )
    session.add(cookie)
    session.add(
        AccessToken(user_id=user.id, jti=access_jti, expires_at=access_expires)
    )
    session.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_token(refresh_raw),
            expires_at=refresh_expires,
        )
    )
    return login, cookie


def _aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def get_valid_access(session: Session, jti: str, user_id: str) -> bool:
    if not jti:
        return False
    row = session.scalar(select(AccessToken).where(AccessToken.jti == jti))
    if row is None or row.revoked or row.user_id != user_id:
        return False
    return _aware(row.expires_at) >= datetime.now(timezone.utc)


def consume_websocket_ticket(
    session: Session,
    *,
    jti: str,
    user_id: str,
) -> bool:
    now = datetime.now(timezone.utc)
    result = session.execute(
        update(WebSocketTicket)
        .where(
            WebSocketTicket.jti == jti,
            WebSocketTicket.user_id == user_id,
            WebSocketTicket.consumed_at.is_(None),
            WebSocketTicket.expires_at >= now,
        )
        .values(consumed_at=now)
    )
    session.commit()
    return result.rowcount == 1


def get_valid_refresh(session: Session, raw: str) -> RefreshToken | None:
    row = session.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw)))
    if row is None or row.revoked:
        return None
    if _aware(row.expires_at) < datetime.now(timezone.utc):
        return None
    return row


def rotate_refresh(
    session: Session,
    old: RefreshToken,
    *,
    access_jti: str,
    access_expires: datetime,
    refresh_raw: str,
    refresh_expires: datetime,
) -> None:
    old.revoked = True
    session.add(AccessToken(user_id=old.user_id, jti=access_jti, expires_at=access_expires))
    session.add(
        RefreshToken(
            user_id=old.user_id,
            token_hash=hash_token(refresh_raw),
            expires_at=refresh_expires,
        )
    )


def revoke_user_sessions(session: Session, user_id: str) -> None:
    now = datetime.now(timezone.utc)
    for row in session.scalars(select(RefreshToken).where(RefreshToken.user_id == user_id, RefreshToken.revoked.is_(False))):
        row.revoked = True
    for row in session.scalars(select(CookieSession).where(CookieSession.user_id == user_id, CookieSession.revoked.is_(False))):
        row.revoked = True
    for row in session.scalars(select(AccessToken).where(AccessToken.user_id == user_id, AccessToken.revoked.is_(False))):
        row.revoked = True
    for row in session.scalars(select(LoginSession).where(LoginSession.user_id == user_id, LoginSession.ended_at.is_(None))):
        row.ended_at = now


def user_payload(user: User) -> dict[str, Any]:
    return {
        "id": user.id,
        "email": user.email,
        "name": user.display_name,
        "photo_url": user.photo_url,
        "role": user.role,
        "firebase_uid": user.firebase_uid,
    }
