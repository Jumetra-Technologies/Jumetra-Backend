from __future__ import annotations

from fastapi import HTTPException, Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from auth.routes import current_user
from .origins import is_allowed_origin


class AuthenticatedWriteMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, enabled: bool, allowed_origins: list[str], origin_pattern: str):
        super().__init__(app)
        self.enabled = enabled
        self.allowed_origins = allowed_origins
        self.origin_pattern = origin_pattern

    async def dispatch(self, request: Request, call_next):
        if not self.enabled or request.method in {"GET", "HEAD", "OPTIONS"}:
            return await call_next(request)
        if request.url.path in {
            "/auth/google",
            "/auth/github",
            "/auth/refresh",
            "/auth/logout",
            "/auth/ws-ticket",
            "/auth/desktop/codes",
            "/auth/desktop/token",
            "/auth/desktop/refresh",
            "/auth/desktop/logout",
            "/telemetry/heartbeat",  # checks its own origin or token; signed-out visitors count too
            "/admin/session",  # the admin password, or the admin token on sign-out
        }:
            return await call_next(request)
        # Routes that check their own credentials: the release pipeline's token (api/routes/releases.py).
        if request.url.path == "/releases" or request.url.path.startswith("/releases/"):
            return await call_next(request)
        # Crash reports are accepted signed out, with the sender's stated consent (api/routes/crash_reports.py).
        if request.url.path == "/crash-reports":
            return await call_next(request)

        # The origin check stops other websites using the browser's cookies (CSRF). A request that
        # carries its own bearer token, like the desktop app's, can't be forged that way: a browser
        # only sends an Authorization header cross-site after a CORS preflight, which only allowed
        # origins pass. So it needs a valid session, but no website origin.
        bearer = request.headers.get("authorization", "").lower().startswith("bearer ")

        origin = request.headers.get("x-forwarded-origin") or request.headers.get("origin")
        if not bearer and not is_allowed_origin(origin, self.allowed_origins, self.origin_pattern):
            return JSONResponse({"detail": "Untrusted request origin"}, status_code=403)

        auth_response = Response()
        try:
            current_user(request, auth_response)
        except HTTPException as exc:
            response = JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
            for name, value in auth_response.raw_headers:
                if name.lower() == b"set-cookie":
                    response.raw_headers.append((name, value))
            return response

        response = await call_next(request)
        for name, value in auth_response.raw_headers:
            if name.lower() == b"set-cookie":
                response.raw_headers.append((name, value))
        return response