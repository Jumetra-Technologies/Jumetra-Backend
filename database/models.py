from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from api.db.base import Base


def _uuid() -> str:
    return uuid.uuid4().hex


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UserProfile(Base):
    """What the person says about themselves. Separate from the platform role on ``users``."""

    __tablename__ = "user_profiles"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    auth_provider: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    self_role: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    role_other: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    organization: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    location: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    bio: Mapped[Optional[str]] = mapped_column(String(280), nullable=True)
    learning_progress: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class OAuthAccount(Base):
    __tablename__ = "oauth_accounts"
    __table_args__ = (UniqueConstraint("provider", "provider_user_id", name="uq_oauth_provider_user"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class RefreshToken(Base):
    """One refresh token. ``client`` is ``web`` or ``desktop``; desktop tokens belong to a device."""

    __tablename__ = "refresh_tokens"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    client: Mapped[str] = mapped_column(String(16), default="web", nullable=False, server_default="web")
    device_id: Mapped[Optional[str]] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), nullable=True, index=True)


class LoginSession(Base):
    __tablename__ = "login_sessions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)


class CookieSession(Base):
    __tablename__ = "cookie_sessions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    login_session_id: Mapped[Optional[str]] = mapped_column(ForeignKey("login_sessions.id"), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class AccessToken(Base):
    __tablename__ = "access_tokens"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    jti: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    device_id: Mapped[Optional[str]] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), nullable=True, index=True)


class WebSocketTicket(Base):
    __tablename__ = "websocket_tickets"

    jti: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class UserProject(Base):
    """A robotics project a person keeps under their account (the website's Projects page)."""

    __tablename__ = "user_projects"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    objectives: Mapped[str] = mapped_column(Text, default="", nullable=False)
    contributors: Mapped[str] = mapped_column(Text, default="", nullable=False)
    category: Mapped[str] = mapped_column(String(64), default="other", nullable=False)
    hardware: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    teammates: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class UserProjectExperiment(Base):
    """One experiment journal entry inside a user project."""

    __tablename__ = "user_project_experiments"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("user_projects.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    objective: Mapped[str] = mapped_column(Text, default="", nullable=False)
    hardware: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    procedure: Mapped[str] = mapped_column(Text, default="", nullable=False)
    observations: Mapped[str] = mapped_column(Text, default="", nullable=False)
    results: Mapped[str] = mapped_column(Text, default="", nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class LabSessionRecord(Base):
    """One Engineering Lab session, stored whole as the JSON document the lab saves."""

    __tablename__ = "lab_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    document: Mapped[dict] = mapped_column(JSON, nullable=False)
    client_updated_at: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class Device(Base):
    """A desktop installation that signed in. Revoking it ends its sessions."""

    __tablename__ = "devices"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    platform: Mapped[str] = mapped_column(String(16), nullable=False)  # windows | linux | macos
    app_version: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class DesktopAuthCode(Base):
    """One desktop sign-in attempt: created by the app, approved on the website, exchanged once."""

    __tablename__ = "desktop_auth_codes"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)  # pending | approved | exchanged | denied | expired
    code_challenge: Mapped[str] = mapped_column(String(128), nullable=False)
    code_challenge_method: Mapped[str] = mapped_column(String(8), default="S256", nullable=False)
    code_hash: Mapped[Optional[str]] = mapped_column(String(64), unique=True, nullable=True)  # the one-time code, hashed, set on approval
    redirect_uri: Mapped[str] = mapped_column(String(256), nullable=False)
    device_name: Mapped[str] = mapped_column(String(120), nullable=False)
    device_platform: Mapped[str] = mapped_column(String(16), nullable=False)
    app_version: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    user_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    device_id: Mapped[Optional[str]] = mapped_column(ForeignKey("devices.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    exchanged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class Release(Base):
    """A published desktop app version on a channel. Written by the release pipeline, read by the app and the download page."""

    __tablename__ = "releases"
    __table_args__ = (UniqueConstraint("channel", "version", name="uq_releases_channel_version"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    channel: Mapped[str] = mapped_column(String(16), nullable=False, index=True)  # stable | beta
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # Older versions must update before they keep working (a security fix, a broken file format).
    minimum_version: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    withdrawn_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ReleaseFile(Base):
    """One installer of a release: a platform, an architecture, and where to download it."""

    __tablename__ = "release_files"
    __table_args__ = (UniqueConstraint("release_id", "platform", "arch", "kind", name="uq_release_files_target"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    release_id: Mapped[str] = mapped_column(ForeignKey("releases.id", ondelete="CASCADE"), nullable=False, index=True)
    platform: Mapped[str] = mapped_column(String(16), nullable=False)  # windows | linux | macos
    arch: Mapped[str] = mapped_column(String(16), nullable=False)  # x64 | arm64
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # nsis | dmg | zip | appimage | deb | rpm
    url: Mapped[str] = mapped_column(String(512), nullable=False)
    sha512: Mapped[str] = mapped_column(String(128), nullable=False)  # base64, as electron-updater writes it
    size: Mapped[int] = mapped_column(nullable=False)
