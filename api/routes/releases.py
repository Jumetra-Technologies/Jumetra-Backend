"""Desktop app releases (Phase Two sprint 5; download page and update checks).

    GET  /releases/latest?channel=stable&platform=windows&arch=x64   public
    POST /releases                                                   release pipeline
    POST /releases/{channel}/{version}/withdraw                      release pipeline

Reading is public: the website's download page and the app's update check
both use it, signed in or not. Writing takes the release pipeline's token
(KIUNGO_RELEASE_TOKEN), never a person's session. Installers live wherever the
pipeline uploads them; this only records where, and their checksums.
"""

from __future__ import annotations

import hmac
import os
import re
from datetime import datetime, timezone
from typing import Any, Literal, Optional

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from database.models import Release, ReleaseFile

router = APIRouter(prefix="/releases", tags=["releases"])

Channel = Literal["stable", "beta"]
Platform = Literal["windows", "linux", "macos"]
Arch = Literal["x64", "arm64"]
Kind = Literal["nsis", "dmg", "zip", "appimage", "deb", "rpm"]

SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?$")


def _version_key(version: str) -> tuple:
    """Semantic version order: 1.10.0 after 1.9.0, and 1.0.0-beta.2 before 1.0.0."""
    m = SEMVER.match(version)
    if not m:
        return (-1,)
    major, minor, patch, pre = m.groups()
    if not pre:
        return (int(major), int(minor), int(patch), 1, ())
    parts = tuple((0, int(p), "") if p.isdigit() else (1, 0, p) for p in pre.split("."))
    return (int(major), int(minor), int(patch), 0, parts)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


class ReleaseFileIn(BaseModel):
    platform: Platform
    arch: Arch
    kind: Kind
    url: str = Field(max_length=512)
    sha512: str = Field(min_length=86, max_length=128)
    size: int = Field(gt=0, lt=4 * 1024**3)

    @field_validator("url")
    @classmethod
    def _https(cls, v: str) -> str:
        if not v.startswith("https://"):
            raise ValueError("Installers are downloaded over https only.")
        return v


class ReleaseIn(BaseModel):
    channel: Channel = "stable"
    version: str = Field(max_length=32)
    notes: str = Field(default="", max_length=20_000)
    minimum_version: Optional[str] = Field(default=None, max_length=32)
    published_at: Optional[datetime] = None
    files: list[ReleaseFileIn] = Field(min_length=1, max_length=24)

    @field_validator("version", "minimum_version")
    @classmethod
    def _semver(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not SEMVER.match(v):
            raise ValueError("Use a semantic version, such as 0.5.0 or 0.6.0-beta.1.")
        return v


def _release_token(authorization: Optional[str]) -> None:
    expected = os.environ.get("KIUNGO_RELEASE_TOKEN", "")
    if not expected:
        raise HTTPException(status_code=503, detail="Publishing releases isn't set up on this server.")
    given = (authorization or "").removeprefix("Bearer ").strip()
    if not given or not hmac.compare_digest(given.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="Only the release pipeline can publish releases.")


def _payload(release: Release, files: list[ReleaseFile]) -> dict[str, Any]:
    return {
        "channel": release.channel,
        "version": release.version,
        "notes": release.notes,
        "minimum_version": release.minimum_version,
        "published_at": _aware(release.published_at).isoformat(),
        "files": [
            {"platform": f.platform, "arch": f.arch, "kind": f.kind, "url": f.url, "sha512": f.sha512, "size": f.size}
            for f in sorted(files, key=lambda f: (f.platform, f.arch, f.kind))
        ],
    }


@router.get("/latest")
def latest_release(
    request: Request,
    response: Response,
    channel: Channel = "stable",
    platform: Optional[Platform] = None,
    arch: Optional[Arch] = None,
) -> dict[str, Any]:
    """The newest release on a channel that has an installer for this platform and architecture."""
    now = _utcnow()
    with request.app.state.db_factory() as session:
        releases = session.execute(select(Release).where(Release.channel == channel, Release.withdrawn_at.is_(None))).scalars().all()
        for release in sorted(releases, key=lambda r: _version_key(r.version), reverse=True):
            if _aware(release.published_at) > now:
                continue
            files = session.execute(select(ReleaseFile).where(ReleaseFile.release_id == release.id)).scalars().all()
            files = [f for f in files if (platform is None or f.platform == platform) and (arch is None or f.arch == arch)]
            if not files:
                continue
            response.headers["Cache-Control"] = "public, max-age=300"
            return _payload(release, files)
    raise HTTPException(status_code=404, detail="There's no release on this channel for this computer yet.")


@router.post("", status_code=201)
def publish_release(body: ReleaseIn, request: Request, authorization: Optional[str] = Header(default=None)) -> dict[str, Any]:
    _release_token(authorization)
    targets = {(f.platform, f.arch, f.kind) for f in body.files}
    if len(targets) != len(body.files):
        raise HTTPException(status_code=422, detail="Each installer needs its own platform, architecture and kind.")
    with request.app.state.db_factory() as session:
        release = Release(
            channel=body.channel,
            version=body.version,
            notes=body.notes,
            minimum_version=body.minimum_version,
            published_at=body.published_at or _utcnow(),
        )
        session.add(release)
        try:
            session.flush()
        except IntegrityError:
            session.rollback()
            raise HTTPException(status_code=409, detail=f"{body.version} is already published on {body.channel}. Releases can't be changed: publish a new version.")
        files = [ReleaseFile(release_id=release.id, **f.model_dump()) for f in body.files]
        session.add_all(files)
        session.commit()
        return _payload(release, files)


@router.post("/{channel}/{version}/withdraw")
def withdraw_release(channel: Channel, version: str, request: Request, authorization: Optional[str] = Header(default=None)) -> dict[str, Any]:
    """Stop offering a release (a bad build). Apps that installed it update to the newest one left."""
    _release_token(authorization)
    with request.app.state.db_factory() as session:
        release = session.execute(select(Release).where(Release.channel == channel, Release.version == version)).scalar_one_or_none()
        if release is None:
            raise HTTPException(status_code=404, detail="No such release.")
        if release.withdrawn_at is None:
            release.withdrawn_at = _utcnow()
            session.commit()
        return {"channel": channel, "version": version, "withdrawn": True}
