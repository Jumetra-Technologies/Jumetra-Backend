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
            "/auth/refresh",
            "/auth/logout",
            "/auth/ws-ticket",
        }:
            return await call_next(request)

        origin = request.headers.get("x-forwarded-origin") or request.headers.get("origin")
        if not is_allowed_origin(origin, self.allowed_origins, self.origin_pattern):
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