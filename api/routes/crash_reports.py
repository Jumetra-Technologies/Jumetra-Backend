"""Crash reports, only with consent (Phase Two sprint 6; DSK-81 in sprint 12).

    GET  /auth/me/consents          what the signed-in person agreed to share
    PUT  /auth/me/consents          record their answer
    POST /crash-reports             one crash, sent by the desktop app

The desktop app asks once, keeps the answer on the computer, and sends a
report only when the answer is yes. A signed-in person's answer is also kept
here, so it follows them to another computer; when it's no, reports carrying
their session are refused even if a device sends one. Reports carry the app's
own error and stack, never sketches, projects or file contents, and are kept
90 days.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete

from auth.routes import _user_from_access, current_user_id
from auth.tokens import bearer_token
from database.models import Consent, CrashReport

router = APIRouter(tags=["crash reports"])

RETENTION = timedelta(days=90)
MAX_STACK = 32_000


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ConsentIn(BaseModel):
    crash_reports: bool
    decided_in: str = Field(default="", max_length=40)


@router.get("/auth/me/consents")
def get_consents(request: Request, user_id: str = Depends(current_user_id)) -> dict[str, Any]:
    with request.app.state.db_factory() as session:
        consent = session.get(Consent, user_id)
        if consent is None:
            return {"crash_reports": None, "decided_at": None, "decided_in": None}
        return {"crash_reports": consent.crash_reports, "decided_at": consent.decided_at.isoformat(), "decided_in": consent.decided_in}


@router.put("/auth/me/consents")
def put_consents(body: ConsentIn, request: Request, user_id: str = Depends(current_user_id)) -> dict[str, Any]:
    with request.app.state.db_factory() as session:
        consent = session.get(Consent, user_id)
        if consent is None:
            consent = Consent(user_id=user_id, crash_reports=body.crash_reports, decided_in=body.decided_in, decided_at=_utcnow())
            session.add(consent)
        else:
            consent.crash_reports = body.crash_reports
            consent.decided_in = body.decided_in
            consent.decided_at = _utcnow()
        if not body.crash_reports:
            # Saying no also removes what was sent under their account.
            session.execute(delete(CrashReport).where(CrashReport.user_id == user_id))
        session.commit()
        return {"crash_reports": consent.crash_reports, "decided_at": consent.decided_at.isoformat(), "decided_in": consent.decided_in}


class CrashReportIn(BaseModel):
    # The app sends a report only when the person said yes; the field makes that explicit.
    consent: Literal[True]
    install_id: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    app_version: str = Field(max_length=32)
    platform: Literal["windows", "linux", "macos"]
    arch: Literal["x64", "arm64", "ia32"]
    process: Literal["main", "renderer", "gpu", "utility"]
    message: str = Field(min_length=1, max_length=2000)
    stack: str = Field(default="", max_length=MAX_STACK)
    occurred_at: datetime

    @field_validator("occurred_at")
    @classmethod
    def _aware(cls, v: datetime) -> datetime:
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


def _optional_user(request: Request) -> Optional[str]:
    """The sender's account if the report carries a valid bearer token; reports work signed out too."""
    token = bearer_token(request)
    if not token:
        return None
    with request.app.state.db_factory() as session:
        user = _user_from_access(request, session, token)
        return user.id if user else None


@router.post("/crash-reports", status_code=202)
def post_crash_report(body: CrashReportIn, request: Request, response: Response) -> dict[str, Any]:
    user_id = _optional_user(request)
    now = _utcnow()
    with request.app.state.db_factory() as session:
        if user_id:
            consent = session.get(Consent, user_id)
            if consent is not None and not consent.crash_reports:
                raise HTTPException(status_code=403, detail="This account has said no to crash reports.")
        report = CrashReport(
            install_id=body.install_id,
            user_id=user_id,
            app_version=body.app_version,
            platform=body.platform,
            arch=body.arch,
            process=body.process,
            message=body.message,
            stack=body.stack,
            occurred_at=min(body.occurred_at, now),
            received_at=now,
        )
        session.add(report)
        # Nothing is kept past the retention period.
        session.execute(delete(CrashReport).where(CrashReport.received_at < now - RETENTION))
        session.commit()
        return {"id": report.id, "received": True}
