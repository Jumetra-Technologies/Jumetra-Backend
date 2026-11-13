"""Project sync (Phase Two sprint 11, DSK-14). Design: docs/sync-api.md.

    GET    /auth/me/projects-sync                         the account's synced projects
    GET    /auth/me/projects-sync/{id}                    the current tree, ETag "r{revision}"
    POST   /auth/me/projects-sync/{id}/blobs/missing      which of these hashes the server lacks
    POST   /auth/me/projects-sync/{id}/blobs              upload file contents
    GET    /auth/me/projects-sync/{id}/blobs/{sha256}     one file's content
    PUT    /auth/me/projects-sync/{id}                    commit a new tree, If-Match "r{revision}" or "*"
    DELETE /auth/me/projects-sync/{id}                    soft delete, If-Match
    POST   /auth/me/projects-sync/{id}/restore            undo a delete within 30 days

The revision is the server's clock, never the computer's: a commit names the
revision it started from and is refused with 409 (and the server's tree) if
the server has moved on. Nothing is overwritten without the client seeing it.

Blobs are kept per owner, so knowing a file's hash never gives access to
someone else's file.
"""

from __future__ import annotations

import base64
import hashlib
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, func, select, update

from auth.routes import current_user_id
from database.models import FileBlob, ProjectRevision, SyncedFile, SyncedProject

router = APIRouter(prefix="/auth/me/projects-sync", tags=["project sync"])

MAX_FILE = 2 * 1024 * 1024
MAX_PROJECT = 20 * 1024 * 1024
MAX_FILES = 300
QUOTA = 200 * 1024 * 1024
KEEP_REVISIONS = 20
DELETED_KEPT = timedelta(days=30)
# A blob nothing references yet is kept this long: it may be one a device uploaded (or was told
# it already has) a moment ago and is about to commit. Listing projects used to delete it,
# so the commit failed with 422 (audit API-008).
BLOB_GRACE = timedelta(hours=1)

PROJECT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
NAME = r"[A-Za-z0-9_][A-Za-z0-9 _.()+-]{0,99}"
# What a project folder syncs: its files at the top, the sketch's files, and records. Never .kiungo/ (local undo history).
SYNCED_PATH = re.compile(rf"^(kiungo\.json|circuit\.json|world\.json|sketch/{NAME}|records/{NAME}(/{NAME})?)$")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _check_id(project_id: str) -> str:
    if not PROJECT_ID.match(project_id):
        raise HTTPException(status_code=422, detail="That isn't a project id.")
    return project_id


class FileRef(BaseModel):
    path: str = Field(max_length=255)
    sha256: str

    @field_validator("path")
    @classmethod
    def _path(cls, v: str) -> str:
        if ".." in v or not SYNCED_PATH.match(v):
            raise ValueError(f"{v} isn't a file a project syncs.")
        return v

    @field_validator("sha256")
    @classmethod
    def _sha(cls, v: str) -> str:
        if not SHA256.match(v):
            raise ValueError("Use a lowercase hex SHA-256.")
        return v


class CommitIn(BaseModel):
    name: str = Field(default="", max_length=200)
    board: str = Field(default="", max_length=64)
    device: str = Field(default="", max_length=120)
    files: list[FileRef] = Field(max_length=MAX_FILES)

    @field_validator("files")
    @classmethod
    def _unique(cls, v: list[FileRef]) -> list[FileRef]:
        if len({f.path for f in v}) != len(v):
            raise ValueError("Each path once.")
        return v


class BlobIn(BaseModel):
    sha256: str
    base64: str = Field(max_length=(MAX_FILE * 4) // 3 + 8)

    @field_validator("sha256")
    @classmethod
    def _sha(cls, v: str) -> str:
        if not SHA256.match(v):
            raise ValueError("Use a lowercase hex SHA-256.")
        return v


class HashesIn(BaseModel):
    hashes: list[str] = Field(max_length=MAX_FILES)


def _tree(session, owner_id: str, project: SyncedProject) -> dict[str, Any]:
    files = session.execute(select(SyncedFile).where(SyncedFile.owner_id == owner_id, SyncedFile.project_id == project.id).order_by(SyncedFile.path)).scalars().all()
    return {
        "id": project.id,
        "name": project.name,
        "board": project.board,
        "revision": project.revision,
        "deleted": project.deleted_at is not None,
        "updated_at": _aware(project.updated_at).isoformat() if project.updated_at else None,
        "files": [{"path": f.path, "sha256": f.sha256, "size": f.size_bytes} for f in files],
    }


def _etag(revision: int) -> str:
    return f'"r{revision}"'


def _match(if_match: Optional[str]) -> Optional[int]:
    """The revision the client started from; None for "*" (create). 412 when it's missing or malformed."""
    if not if_match:
        raise HTTPException(status_code=412, detail='Send If-Match: "r{revision}" (or * to create), so a newer copy is never overwritten.')
    value = if_match.strip()
    if value == "*":
        return None
    m = re.fullmatch(r'(?:W/)?"r(\d+)"', value)
    if not m:
        raise HTTPException(status_code=412, detail='If-Match is "r{revision}", as the ETag gave it.')
    return int(m.group(1))


def _conflict(session, owner_id: str, project: SyncedProject) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": "The project changed on the server since this copy last synced.", "tree": _tree(session, owner_id, project)}, headers={"ETag": _etag(project.revision)})


def _purge_deleted(session, owner_id: str) -> None:
    old = session.execute(select(SyncedProject).where(SyncedProject.owner_id == owner_id, SyncedProject.deleted_at.is_not(None))).scalars().all()
    for project in old:
        if _aware(project.deleted_at) < _utcnow() - DELETED_KEPT:
            session.execute(delete(SyncedFile).where(SyncedFile.owner_id == owner_id, SyncedFile.project_id == project.id))
            session.execute(delete(ProjectRevision).where(ProjectRevision.owner_id == owner_id, ProjectRevision.project_id == project.id))
            session.delete(project)
    _collect_blobs(session, owner_id)


def _collect_blobs(session, owner_id: str) -> None:
    """Drop blobs that no current file and no kept revision uses, once they're older than BLOB_GRACE."""
    used = set(session.execute(select(SyncedFile.sha256).where(SyncedFile.owner_id == owner_id)).scalars().all())
    for files in session.execute(select(ProjectRevision.files).where(ProjectRevision.owner_id == owner_id)).scalars().all():
        used.update(f["sha256"] for f in files)
    cutoff = _utcnow() - BLOB_GRACE
    stored = session.execute(select(FileBlob.sha256, FileBlob.created_at).where(FileBlob.owner_id == owner_id)).all()
    unused = [h for h, created in stored if h not in used and (created is None or _aware(created) < cutoff)]
    if unused:
        session.execute(delete(FileBlob).where(FileBlob.owner_id == owner_id, FileBlob.sha256.in_(unused)))


def _keep_fresh(session, owner_id: str, hashes: set[str]) -> None:
    """A device was just told the server has these blobs: keep them through the grace period."""
    if hashes:
        session.execute(update(FileBlob).where(FileBlob.owner_id == owner_id, FileBlob.sha256.in_(sorted(hashes))).values(created_at=_utcnow()))


def _project(session, owner_id: str, project_id: str) -> Optional[SyncedProject]:
    return session.get(SyncedProject, {"id": project_id, "owner_id": owner_id})


@router.get("")
def list_projects(request: Request, user_id: str = Depends(current_user_id)) -> dict[str, Any]:
    with request.app.state.db_factory() as session:
        _purge_deleted(session, user_id)
        session.commit()
        projects = session.execute(select(SyncedProject).where(SyncedProject.owner_id == user_id).order_by(SyncedProject.updated_at.desc())).scalars().all()
        used = sum(p.size_bytes for p in projects)
        return {
            "projects": [
                {
                    "id": p.id,
                    "name": p.name,
                    "board": p.board,
                    "revision": p.revision,
                    "size_bytes": p.size_bytes,
                    "updated_at": _aware(p.updated_at).isoformat() if p.updated_at else None,
                    "deleted": p.deleted_at is not None,
                }
                for p in projects
            ],
            "used_bytes": used,
            "quota_bytes": QUOTA,
        }


@router.get("/{project_id}")
def get_project(project_id: str, request: Request, response: Response, user_id: str = Depends(current_user_id)) -> dict[str, Any]:
    _check_id(project_id)
    with request.app.state.db_factory() as session:
        project = _project(session, user_id, project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="This project isn't on your account.")
        response.headers["ETag"] = _etag(project.revision)
        return _tree(session, user_id, project)


@router.post("/{project_id}/blobs/missing")
def missing_blobs(project_id: str, body: HashesIn, request: Request, user_id: str = Depends(current_user_id)) -> dict[str, Any]:
    _check_id(project_id)
    wanted = {h for h in body.hashes if SHA256.match(h)}
    with request.app.state.db_factory() as session:
        have = set(session.execute(select(FileBlob.sha256).where(FileBlob.owner_id == user_id, FileBlob.sha256.in_(wanted))).scalars().all()) if wanted else set()
        _keep_fresh(session, user_id, have)
        session.commit()
        return {"missing": sorted(wanted - have)}


@router.post("/{project_id}/blobs")
def upload_blobs(project_id: str, body: list[BlobIn], request: Request, user_id: str = Depends(current_user_id)) -> dict[str, Any]:
    _check_id(project_id)
    if len(body) > 50:
        raise HTTPException(status_code=413, detail="Send at most 50 files at a time.")
    decoded: dict[str, bytes] = {}
    for blob in body:
        try:
            content = base64.b64decode(blob.base64, validate=True)
        except Exception:
            raise HTTPException(status_code=422, detail=f"{blob.sha256} isn't valid base64.")
        if len(content) > MAX_FILE:
            raise HTTPException(status_code=413, detail=f"Files sync up to {MAX_FILE // (1024 * 1024)} MB each.")
        if hashlib.sha256(content).hexdigest() != blob.sha256:
            raise HTTPException(status_code=422, detail=f"The content doesn't match {blob.sha256}.")
        decoded[blob.sha256] = content
    with request.app.state.db_factory() as session:
        have = set(session.execute(select(FileBlob.sha256).where(FileBlob.owner_id == user_id, FileBlob.sha256.in_(list(decoded)))).scalars().all()) if decoded else set()
        new = {h: c for h, c in decoded.items() if h not in have}
        stored = session.execute(select(func.coalesce(func.sum(FileBlob.size_bytes), 0)).where(FileBlob.owner_id == user_id)).scalar_one()
        # Room for a commit's new files on top of what's kept, with some slack for revisions.
        if stored + sum(len(c) for c in new.values()) > QUOTA + MAX_PROJECT:
            raise HTTPException(status_code=413, detail="Your account's sync space is full. Delete projects you no longer need from it.")
        session.add_all(FileBlob(owner_id=user_id, sha256=h, content=c, size_bytes=len(c)) for h, c in new.items())
        _keep_fresh(session, user_id, have)
        session.commit()
        return {"stored": sorted(new), "existing": sorted(have)}


@router.get("/{project_id}/blobs/{sha256}")
def get_blob(project_id: str, sha256: str, request: Request, user_id: str = Depends(current_user_id)) -> Response:
    _check_id(project_id)
    if not SHA256.match(sha256):
        raise HTTPException(status_code=422, detail="Use a lowercase hex SHA-256.")
    with request.app.state.db_factory() as session:
        blob = session.get(FileBlob, {"owner_id": user_id, "sha256": sha256})
        if blob is None:
            raise HTTPException(status_code=404, detail="No such file on your account.")
        # Content never changes for a hash: cache it for good, but only in this person's own client.
        return Response(content=blob.content, media_type="application/octet-stream", headers={"Cache-Control": "private, max-age=31536000, immutable"})


@router.put("/{project_id}")
def commit_project(project_id: str, body: CommitIn, request: Request, response: Response, if_match: Optional[str] = Header(default=None), user_id: str = Depends(current_user_id)) -> Any:
    _check_id(project_id)
    base = _match(if_match)
    with request.app.state.db_factory() as session:
        project = _project(session, user_id, project_id)
        if project is not None and (base is None or base != project.revision):
            return _conflict(session, user_id, project)
        if project is None and base not in (None, 0):
            raise HTTPException(status_code=404, detail="This project isn't on your account any more. Sync it again to put it back.")

        hashes = {f.sha256 for f in body.files}
        blobs = {b.sha256: b.size_bytes for b in session.execute(select(FileBlob).where(FileBlob.owner_id == user_id, FileBlob.sha256.in_(hashes))).scalars().all()} if hashes else {}
        missing = sorted(hashes - set(blobs))
        if missing:
            return JSONResponse(status_code=422, content={"detail": "Upload these files first.", "missing": missing})
        size = sum(blobs[f.sha256] for f in body.files)
        if size > MAX_PROJECT:
            raise HTTPException(status_code=413, detail=f"A project syncs up to {MAX_PROJECT // (1024 * 1024)} MB.")
        others = session.execute(select(func.coalesce(func.sum(SyncedProject.size_bytes), 0)).where(SyncedProject.owner_id == user_id, SyncedProject.id != project_id)).scalar_one()
        if others + size > QUOTA:
            raise HTTPException(status_code=413, detail="Your account's sync space is full. Delete projects you no longer need from it.")

        if project is None:
            project = SyncedProject(id=project_id, owner_id=user_id, revision=0, size_bytes=0)
            session.add(project)
        revision = project.revision + 1
        current = {f.path: f for f in session.execute(select(SyncedFile).where(SyncedFile.owner_id == user_id, SyncedFile.project_id == project_id)).scalars().all()}
        wanted = {f.path: f.sha256 for f in body.files}
        for path, row in current.items():
            if path not in wanted:
                session.delete(row)
        for path, sha in wanted.items():
            row = current.get(path)
            if row is None:
                session.add(SyncedFile(project_id=project_id, owner_id=user_id, path=path, sha256=sha, size_bytes=blobs[sha], revision=revision))
            elif row.sha256 != sha:
                row.sha256, row.size_bytes, row.revision = sha, blobs[sha], revision
        project.revision = revision
        project.size_bytes = size
        project.name = body.name or project.name
        project.board = body.board or project.board
        project.deleted_at = None
        project.updated_at = _utcnow()
        session.add(ProjectRevision(project_id=project_id, owner_id=user_id, revision=revision, device=body.device, files=[{"path": p, "sha256": h} for p, h in sorted(wanted.items())]))
        session.flush()
        session.execute(delete(ProjectRevision).where(ProjectRevision.owner_id == user_id, ProjectRevision.project_id == project_id, ProjectRevision.revision <= revision - KEEP_REVISIONS))
        _collect_blobs(session, user_id)
        session.commit()
        response.headers["ETag"] = _etag(revision)
        return {"revision": revision}


@router.delete("/{project_id}")
def delete_project(project_id: str, request: Request, if_match: Optional[str] = Header(default=None), user_id: str = Depends(current_user_id)) -> Any:
    _check_id(project_id)
    base = _match(if_match)
    with request.app.state.db_factory() as session:
        project = _project(session, user_id, project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="This project isn't on your account.")
        if base is not None and base != project.revision:
            return _conflict(session, user_id, project)
        if project.deleted_at is None:
            project.deleted_at = _utcnow()
            session.commit()
        return {"id": project_id, "deleted": True, "restorable_until": (_aware(project.deleted_at) + DELETED_KEPT).isoformat()}


@router.post("/{project_id}/restore")
def restore_project(project_id: str, request: Request, user_id: str = Depends(current_user_id)) -> dict[str, Any]:
    _check_id(project_id)
    with request.app.state.db_factory() as session:
        project = _project(session, user_id, project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="This project isn't on your account any more.")
        project.deleted_at = None
        session.commit()
        return _tree(session, user_id, project)
