"""POST /telemetry/heartbeat: the website and desktop app saying someone is using Kiungo.

What's kept, and for how long, is in api/services/activity.py. Nothing is
counted without consent:

- Signed in (bearer token or the website's cookies), a heartbeat counts only
  when the account said yes to usage counting (consents.usage); otherwise it's
  dropped, recording nothing. The website and the desktop app also check first.
- Signed out, the website sends heartbeats only after the visitor allowed it in
  the banner, and they count for a keyed hash of the visitor id the browser
  made. POST /telemetry/forget deletes that visitor's rows when they change
  their mind.

A heartbeat or forget without a token must come from one of the website's own origins.

The website sends its last heartbeat with navigator.sendBeacon when a tab
closes. That can't set headers, so the body is read as JSON whatever its
content type.
"""

from __future__ import annotations

import json
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field, ValidationError

from auth.tokens import ACCESS_COOKIE, REFRESH_COOKIE, bearer_token, decode_access
from database.service import get_valid_access, get_valid_refresh
from security.origins import is_allowed_origin

from ..services import activity

router = APIRouter(prefix="/telemetry", tags=["telemetry"])

MAX_BODY = 2048


class Heartbeat(BaseModel):
    client: Literal["web", "desktop"] = "web"
    page: str = Field(default="/", max_length=512)
    event: Literal["view", "beat", "leave"] = "beat"
    visitor: Optional[str] = Field(default=None, min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    app_version: str = Field(default="", max_length=32)


def signed_in_user(request: Request) -> Optional[str]:
    """Who this request is from, without refreshing anything: a valid access token, else a valid refresh cookie."""
    secret = request.app.state.session_secret
    with request.app.state.db_factory() as session:
        access = bearer_token(request) or request.cookies.get(ACCESS_COOKIE)
        if access:
            try:
                claims = decode_access(access, secret)
            except Exception:
                claims = None
            if claims and claims.get("typ") in (None, "access") and get_valid_access(session, claims.get("jti", ""), claims.get("sub", "")):
                return claims["sub"]
        refresh = request.cookies.get(REFRESH_COOKIE)
        if refresh:
            row = get_valid_refresh(session, refresh)
            if row is not None:
                return row.user_id
    return None


@router.post("/heartbeat", status_code=204, response_class=Response)
async def heartbeat(request: Request) -> Response:
    raw = await request.body()
    if len(raw) > MAX_BODY:
        raise HTTPException(status_code=413, detail="Heartbeat too large.")
    try:
        body = Heartbeat.model_validate(json.loads(raw or b"{}"))
    except (ValueError, ValidationError):
        raise HTTPException(status_code=422, detail="Not a heartbeat.")

    has_token = bearer_token(request) is not None
    if not has_token:
        origin = request.headers.get("origin")
        if not is_allowed_origin(origin, request.app.state.allowed_origins, request.app.state.origin_pattern):
            raise HTTPException(status_code=403, detail="Untrusted request origin")

    user_id = signed_in_user(request)
    if user_id is None and body.client == "desktop":
        return Response(status_code=204)  # the desktop app is always signed in; nothing to credit
    if user_id is not None:
        with request.app.state.db_factory() as session:
            if not activity.usage_allowed(session, user_id):
                return Response(status_code=204)  # the account hasn't said yes: record nothing
    secret = request.app.state.session_secret
    visitor_key = activity.keyed_hash(secret, f"visitor:{body.visitor}") if body.visitor and not user_id else None
    with request.app.state.db_factory() as session:
        activity.record(
            session,
            activity.Beat(client=body.client, page=body.page, event=body.event, user_id=user_id, visitor_key=visitor_key, app_version=body.app_version),
        )
    return Response(status_code=204)


class ForgetVisitor(BaseModel):
    visitor: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")


@router.post("/forget", status_code=204, response_class=Response)
async def forget_visitor(request: Request) -> Response:
    """A signed-out visitor said no after saying yes: delete what was counted for their browser's id."""
    raw = await request.body()
    if len(raw) > MAX_BODY:
        raise HTTPException(status_code=413, detail="Too large.")
    try:
        body = ForgetVisitor.model_validate(json.loads(raw or b"{}"))
    except (ValueError, ValidationError):
        raise HTTPException(status_code=422, detail="Name the visitor id to forget.")
    origin = request.headers.get("origin")
    if not is_allowed_origin(origin, request.app.state.allowed_origins, request.app.state.origin_pattern):
        raise HTTPException(status_code=403, detail="Untrusted request origin")
    with request.app.state.db_factory() as session:
        activity.forget_visitor(session, activity.keyed_hash(request.app.state.session_secret, f"visitor:{body.visitor}"))
    return Response(status_code=204)
