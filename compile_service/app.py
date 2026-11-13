"""Kiungo's compile service (POST /firmware/compile).

A separate, compile-only web service: no accounts, no database and no
secrets. Signed-in state lives on Kiungo's main server, which this service
can't check, so it is open to the allowed websites and limited per address
instead: COMPILE_RATE_PER_MINUTE and COMPILE_RATE_PER_HOUR builds per
client address, COMPILE_WORKERS builds at once with COMPILE_QUEUE waiting
(then 429, "busy").
"""

from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .compiler import Compiler, SketchRefused

DEFAULT_ORIGINS = [
    "https://kiungo-labs-technologies.vercel.app",
    "https://jumetra-frontend.vercel.app",
    "https://jumetra-frontendv0.vercel.app",
    "https://hhipsystemv0.web.app",
    "https://hhipsystemv0.firebaseapp.com",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]


def _int_env(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name, default)))
    except ValueError:
        return default


class FileIn(BaseModel):
    path: str = Field(max_length=80)
    content: str


class CompileIn(BaseModel):
    board: str = Field(default="arduino-uno", max_length=40)
    files: list[FileIn] = Field(max_length=32)


class RateLimiter:
    """Sliding windows of build times per client address."""

    def __init__(self, per_minute: int, per_hour: int, now=time.monotonic) -> None:
        self.per_minute = per_minute
        self.per_hour = per_hour
        self._now = now
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> int:
        """0 when allowed, else how many seconds to wait."""
        now = self._now()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] > 3600:
                hits.popleft()
            last_minute = [t for t in hits if now - t <= 60]
            if len(last_minute) >= self.per_minute:
                return int(60 - (now - last_minute[0])) + 1
            if len(hits) >= self.per_hour:
                return int(3600 - (now - hits[0])) + 1
            hits.append(now)
            if len(self._hits) > 10_000:  # keep memory bounded
                for k in [k for k, v in self._hits.items() if not v][:5000]:
                    del self._hits[k]
            return 0


class Slots:
    """At most `workers` builds at once and `queue` waiting; anything more is refused at once."""

    def __init__(self, workers: int, queue: int) -> None:
        self._run = threading.BoundedSemaphore(workers)
        self._admit = threading.BoundedSemaphore(workers + queue)

    def __enter__(self) -> "Slots":
        if not self._admit.acquire(blocking=False):
            raise HTTPException(status_code=429, detail="Kiungo's compiler is busy. Try again in a few seconds.", headers={"Retry-After": "5"})
        self._run.acquire()
        return self

    def __exit__(self, *exc: Any) -> None:
        self._run.release()
        self._admit.release()


def _client(request: Request) -> str:
    # Render puts the caller first in X-Forwarded-For.
    forwarded = request.headers.get("x-forwarded-for", "")
    return forwarded.split(",")[0].strip() or (request.client.host if request.client else "unknown")


def create_app(compiler: Compiler | None = None) -> FastAPI:
    app = FastAPI(title="Kiungo compile service", version="1.0.0", docs_url=None, redoc_url=None, openapi_url=None)
    origins = [o.strip() for o in os.environ.get("COMPILE_CORS_ORIGINS", ",".join(DEFAULT_ORIGINS)).split(",") if o.strip()]
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=False, allow_methods=["POST", "GET"], allow_headers=["content-type"], max_age=600)
    app.state.compiler = compiler or Compiler(os.environ.get("ARDUINO_CLI", "arduino-cli"))
    app.state.limiter = RateLimiter(_int_env("COMPILE_RATE_PER_MINUTE", 6), _int_env("COMPILE_RATE_PER_HOUR", 60))
    app.state.slots = Slots(_int_env("COMPILE_WORKERS", 2), _int_env("COMPILE_QUEUE", 8))
    app.state.origins = set(origins)

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"ok": True, "boards": ["arduino-uno", "arduino-nano"]}

    @app.post("/firmware/compile")
    async def compile_sketch(body: CompileIn, request: Request) -> dict[str, Any]:
        origin = request.headers.get("origin")
        if origin is not None and origin not in app.state.origins:
            raise HTTPException(status_code=403, detail="This website can't use Kiungo's compiler.")
        wait = app.state.limiter.allow(_client(request))
        if wait:
            raise HTTPException(status_code=429, detail=f"That's a lot of builds. Try again in {wait} s.", headers={"Retry-After": str(wait)})
        files = [f.model_dump() for f in body.files]

        def run() -> dict[str, Any]:
            with app.state.slots:
                return app.state.compiler.compile(body.board, files).to_dict()

        try:
            return await run_in_threadpool(run)
        except SketchRefused as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    return app


app = create_app()
