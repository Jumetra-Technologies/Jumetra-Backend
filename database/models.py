from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, LargeBinary, String, Text, UniqueConstraint
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


class Consent(Base):
    """What a signed-in person has agreed to share. No row means they haven't been asked."""

    __tablename__ = "consents"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    crash_reports: Mapped[bool] = mapped_column(Boolean, nullable=False)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    # Where they decided: "desktop 0.6.0", "website".
    decided_in: Mapped[str] = mapped_column(String(40), default="", nullable=False)


class CrashReport(Base):
    """One crash, sent only with consent. Kept 90 days. No sketch, project or file contents."""

    __tablename__ = "crash_reports"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    # A random id per installation, so repeats from one computer can be grouped. Not linked to an account unless signed in.
    install_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    app_version: Mapped[str] = mapped_column(String(32), nullable=False)
    platform: Mapped[str] = mapped_column(String(16), nullable=False)
    arch: Mapped[str] = mapped_column(String(16), nullable=False)
    process: Mapped[str] = mapped_column(String(16), nullable=False)  # main | renderer | gpu | utility
    message: Mapped[str] = mapped_column(String(2000), nullable=False)
    stack: Mapped[str] = mapped_column(Text, default="", nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False, index=True)


class SyncedProject(Base):
    """A desktop project's copy on the account (DSK-14). The folder on disk is the working copy; this is a backup and a way across."""

    __tablename__ = "synced_projects"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # the id in kiungo.json
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    board: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    # The server's clock: +1 on every accepted change. Clients send it back in If-Match.
    revision: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class SyncedFile(Base):
    """One file of a synced project's current tree."""

    __tablename__ = "synced_files"

    project_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    path: Mapped[str] = mapped_column(String(255), primary_key=True)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    # The project revision that last changed this file.
    revision: Mapped[int] = mapped_column(Integer, nullable=False)


class FileBlob(Base):
    """A file's content, by its SHA-256. Kept per owner, so a hash never gives access to someone else's file."""

    __tablename__ = "file_blobs"

    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    sha256: Mapped[str] = mapped_column(String(64), primary_key=True)
    content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ProjectRevision(Base):
    """The whole tree at one revision, the last 20 per project, so an earlier version can be restored."""

    __tablename__ = "project_revisions"

    project_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, primary_key=True)
    device: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    files: Mapped[list] = mapped_column(JSON, nullable=False)  # [{path, sha256}]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

# ----- Usage, for the admin portal -----
#
# Who is online, how long each account spends in Kiungo, and which pages get
# used, from the website and the desktop app (POST /telemetry/heartbeat).
# Only totals per day are kept, never a log of what someone did. A visitor who
# isn't signed in is a keyed hash of a random id their browser made, so these
# rows never name them. Rows go after 400 days (api/services/activity.py).


class ActivityPresence(Base):
    """Where a person or visitor is right now, on one client. Online means seen in the last two minutes."""

    __tablename__ = "activity_presence"

    subject: Mapped[str] = mapped_column(String(40), primary_key=True)  # u:<user id> | v:<hashed visitor id>
    client: Mapped[str] = mapped_column(String(8), primary_key=True)  # web | desktop
    user_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    page: Mapped[str] = mapped_column(String(96), default="/", nullable=False)
    app_version: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    visit_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)
    left: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class ActivityDaily(Base):
    """Seconds one person or visitor spent in Kiungo on one day (UTC), per client."""

    __tablename__ = "activity_daily"

    subject: Mapped[str] = mapped_column(String(40), primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True, index=True)
    client: Mapped[str] = mapped_column(String(8), primary_key=True)
    user_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class ActivityPageDaily(Base):
    """Views of, and seconds spent on, one page on one day (UTC), per client. Ids in paths are replaced with :id."""

    __tablename__ = "activity_pages"

    day: Mapped[date] = mapped_column(Date, primary_key=True, index=True)
    client: Mapped[str] = mapped_column(String(8), primary_key=True)
    page: Mapped[str] = mapped_column(String(96), primary_key=True)
    views: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class AdminSession(Base):
    """One admin portal sign-in. Its token names this row, so signing out ends it at once."""

    __tablename__ = "admin_sessions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ip_hash: Mapped[str] = mapped_column(String(16), default="", nullable=False)


class AdminSignInAttempt(Base):
    """Each try at the admin password, right or wrong: what the lockout counts and the portal lists."""

    __tablename__ = "admin_sign_in_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)
    ip_hash: Mapped[str] = mapped_column(String(16), default="", nullable=False, index=True)
    ok: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
