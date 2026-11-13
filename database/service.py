from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from api.db.enums import Role
from api.db.models import Organization, User

from .models import (
    AccessToken,
    CookieSession,
    DesktopAuthCode,
    Device,
    LabSessionRecord,
    LoginSession,
    OAuthAccount,
    RefreshToken,
    UserProfile,
    UserProject,
    UserProjectExperiment,
    WebSocketTicket,
)

PROVIDERS = ("google", "github")

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


class ProviderConflict(Exception):
    """The provider identity already belongs to another account."""


class EmailTaken(Exception):
    """An account with this email exists, and this sign-in can't be joined to it by email.

    Either this sign-in's email isn't verified, or the account's own email never was:
    an account made from an unverified email could belong to someone who doesn't own
    the address, so a verified sign-in is never merged into it (that would hand the
    real owner's sign-ins to them).
    """


class RefreshSpent(Exception):
    """The refresh token was already used (or revoked) by the time this request tried to use it."""


def _find_by_provider(session: Session, provider: str, provider_user_id: str) -> OAuthAccount | None:
    return session.scalar(
        select(OAuthAccount).where(
            OAuthAccount.provider == provider,
            OAuthAccount.provider_user_id == provider_user_id,
        )
    )


def _profile_for(session: Session, user: User) -> UserProfile:
    profile = session.scalar(select(UserProfile).where(UserProfile.user_id == user.id))
    if profile is None:
        profile = UserProfile(user_id=user.id)
        session.add(profile)
        session.flush()
    return profile


def _email_verified(session: Session, user: User) -> bool:
    """Whether a provider has ever confirmed that this account's owner owns its email."""
    profile = session.scalar(select(UserProfile).where(UserProfile.user_id == user.id))
    return bool(profile is not None and profile.email_verified)


def upsert_provider_user(
    session: Session,
    *,
    provider: str,
    email: str,
    email_verified: bool,
    name: str,
    picture: str | None,
    provider_user_id: str,
    firebase_uid: str | None,
) -> User:
    """Create or resume the account for a verified Firebase sign-in.

    Continuity, in order: the provider identity, the Firebase UID, then a
    verified email. An unverified email never merges into an existing account.
    """
    if provider not in PROVIDERS:
        raise ValueError(f"Unknown provider: {provider}")
    user = None
    linked = _find_by_provider(session, provider, provider_user_id)
    if linked is not None:
        user = session.get(User, linked.user_id)
    if user is None and firebase_uid:
        user = session.scalar(select(User).where(User.firebase_uid == firebase_uid))
    if user is None and email_verified:
        candidate = session.scalar(select(User).where(User.email == email))
        if candidate is not None and _email_verified(session, candidate):
            user = candidate
    if user is None:
        if session.scalar(select(User.id).where(User.email == email)) is not None:
            raise EmailTaken(email)
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
        if name and not user.display_name:
            user.display_name = name
        if picture and not user.photo_url:
            user.photo_url = picture
        if firebase_uid and not user.firebase_uid:
            user.firebase_uid = firebase_uid
    user.last_login_at = datetime.now(timezone.utc)

    profile = _profile_for(session, user)
    if picture and not profile.avatar_url:
        profile.avatar_url = picture
    if email_verified:
        profile.email_verified = True
    profile.auth_provider = provider

    if linked is None:
        session.add(
            OAuthAccount(
                user_id=user.id,
                provider=provider,
                provider_user_id=provider_user_id,
                email=email,
            )
        )
    return user


def link_provider(
    session: Session,
    user: User,
    *,
    provider: str,
    provider_user_id: str,
    email: str | None,
) -> None:
    """Attach a second sign-in method to an existing account."""
    existing = _find_by_provider(session, provider, provider_user_id)
    if existing is not None:
        if existing.user_id != user.id:
            raise ProviderConflict(f"That {provider} account is already connected to another Kiungo account.")
        return
    session.add(OAuthAccount(user_id=user.id, provider=provider, provider_user_id=provider_user_id, email=email))


def linked_providers(session: Session, user_id: str) -> list[str]:
    rows = session.scalars(select(OAuthAccount.provider).where(OAuthAccount.user_id == user_id)).all()
    return [p for p in PROVIDERS if p in rows]


def delete_user(session: Session, user: User) -> None:
    """Remove the person and everything stored under their account."""
    user_id = user.id
    for model in (UserProjectExperiment,):
        for row in session.scalars(
            select(model).join(UserProject, UserProject.id == model.project_id).where(UserProject.owner_id == user_id)
        ):
            session.delete(row)
    for model, col in (
        (UserProject, UserProject.owner_id),
        (LabSessionRecord, LabSessionRecord.owner_id),
        (OAuthAccount, OAuthAccount.user_id),
        (UserProfile, UserProfile.user_id),
        (RefreshToken, RefreshToken.user_id),
        (AccessToken, AccessToken.user_id),
        (DesktopAuthCode, DesktopAuthCode.user_id),
        (Device, Device.user_id),
        (CookieSession, CookieSession.user_id),
        (LoginSession, LoginSession.user_id),
        (WebSocketTicket, WebSocketTicket.user_id),
    ):
        for row in session.scalars(select(model).where(col == user_id)):
            session.delete(row)
    session.delete(user)


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


def spend_refresh(session: Session, row: RefreshToken) -> None:
    """Mark a refresh token used, atomically: only one request can ever spend it.

    Two requests that read the same live token both see ``revoked = false``; the
    conditional UPDATE lets exactly one of them flip it. The other gets RefreshSpent,
    which the routes treat as a replay.
    """
    result = session.execute(
        update(RefreshToken)
        .where(RefreshToken.id == row.id, RefreshToken.revoked.is_(False))
        .values(revoked=True)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        session.rollback()
        raise RefreshSpent()
    row.revoked = True


def rotate_refresh(
    session: Session,
    old: RefreshToken,
    *,
    access_jti: str,
    access_expires: datetime,
    refresh_raw: str,
    refresh_expires: datetime,
) -> None:
    """Spend ``old`` and issue its successor, for the same client and device."""
    spend_refresh(session, old)
    session.add(AccessToken(user_id=old.user_id, jti=access_jti, expires_at=access_expires, device_id=old.device_id))
    session.add(
        RefreshToken(
            user_id=old.user_id,
            token_hash=hash_token(refresh_raw),
            expires_at=refresh_expires,
            client=old.client,
            device_id=old.device_id,
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


def user_payload(user: User, session: Session | None = None) -> dict[str, Any]:
    """The user as the website reads it (docs/accounts-and-profile.md in jumetra-frontend)."""
    profile = None
    providers: list[str] = []
    if session is not None:
        profile = session.scalar(select(UserProfile).where(UserProfile.user_id == user.id))
        providers = linked_providers(session, user.id)
    self_role = profile.self_role if profile else None
    return {
        "id": user.id,
        "email": user.email,
        "email_verified": bool(profile.email_verified) if profile else False,
        "name": user.display_name,
        "display_name": user.display_name,
        "photo_url": user.photo_url,
        "picture_url": user.photo_url,
        "firebase_uid": user.firebase_uid,
        "auth_provider": (profile.auth_provider if profile else None) or (providers[0] if providers else None),
        "linked_providers": providers,
        "role": self_role,
        "role_other": profile.role_other if profile else None,
        "profile_complete": bool(self_role) and (self_role != "other" or bool(profile and profile.role_other)),
        "platform_role": user.role,
        "organization": profile.organization if profile else None,
        "location": profile.location if profile else None,
        "bio": profile.bio if profile else None,
    }
