"""The admin portal: a password sign-in, and what's happening across Kiungo.

POST /admin/session    password -> a 30-minute admin token (wrong passwords lock out)
DELETE /admin/session  ends that token
GET /admin/overview    accounts, projects, time per account, pages, who's online

The token goes in ``Authorization: Bearer``. It is not an account token: it
opens these routes only, and account routes refuse it. How the password is
stored and changed is in api/services/admin_auth.py.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

from auth.routes import _client_ip
from auth.tokens import bearer_token
from database.models import AdminSession

from ..services import activity, admin_auth

router = APIRouter(prefix="/admin", tags=["admin"])

NO_STORE = {"Cache-Control": "no-store", "X-Robots-Tag": "noindex"}


class PasswordBody(BaseModel):
    password: str = Field(min_length=1, max_length=200)


class AdminSessionOut(BaseModel):
    token: str
    expires_at: str


def _ip_hash(request: Request) -> str:
    return activity.keyed_hash(request.app.state.session_secret, f"ip:{_client_ip(request) or 'unknown'}", 16)


def require_admin(request: Request) -> AdminSession:
    token = bearer_token(request)
    if token:
        with request.app.state.db_factory() as session:
            row = admin_auth.session_for(session, token, request.app.state.session_secret)
            if row is not None:
                return row
    raise HTTPException(status_code=401, detail="Sign in to the admin portal again.", headers={"WWW-Authenticate": "Bearer"})


@router.post("/session", response_model=AdminSessionOut)
def admin_sign_in(body: PasswordBody, request: Request, response: Response) -> AdminSessionOut:
    response.headers.update(NO_STORE)
    with request.app.state.db_factory() as session:
        try:
            token, expires, wait = admin_auth.sign_in(session, password=body.password, ip_hash=_ip_hash(request), secret=request.app.state.session_secret)
        except admin_auth.AdminNotConfigured as exc:
            raise HTTPException(status_code=503, detail=str(exc), headers=NO_STORE) from exc
    if wait:
        minutes = max(1, round(wait / 60))
        raise HTTPException(
            status_code=429,
            detail=f"Too many wrong passwords. Try again in {minutes} minute{'s' if minutes != 1 else ''}.",
            headers={"Retry-After": str(wait), **NO_STORE},
        )
    if token is None or expires is None:
        raise HTTPException(status_code=401, detail="That password isn't right.", headers=NO_STORE)
    return AdminSessionOut(token=token, expires_at=expires.isoformat())


@router.delete("/session", status_code=204, response_class=Response)
def admin_sign_out(request: Request, admin: AdminSession = Depends(require_admin)) -> Response:
    with request.app.state.db_factory() as session:
        row = session.get(AdminSession, admin.id)
        if row is not None and row.revoked_at is None:
            row.revoked_at = datetime.now(timezone.utc)
            session.commit()
    return Response(status_code=204, headers=NO_STORE)


@router.get("/overview")
def admin_overview(request: Request, response: Response, days: int = Query(7, ge=1, le=90), _: AdminSession = Depends(require_admin)) -> dict:
    response.headers.update(NO_STORE)
    with request.app.state.db_factory() as session:
        activity.prune(session)
        return activity.overview(session, days=days)
