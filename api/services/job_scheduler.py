"""Bounded in-process scheduler for work that should not block API requests."""

from __future__ import annotations

import copy
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable


class JobQueueFull(RuntimeError):
    """Raised when the worker pool and its pending queue are full."""


@dataclass
class _Job:
    job_id: str
    job_type: str
    status: str = "queued"
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    result: Any = None
    error: str | None = None
    dedupe_key: str | None = None

    def to_dict(self) -> dict[str, Any]:
        duration_ms = None
        if self.started_at is not None:
            end_time = self.finished_at or time.time()
            duration_ms = round((end_time - self.started_at) * 1000)
        return {
            "job_id": self.job_id,
            "job_type": self.job_type,
            "status": self.status,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_ms": duration_ms,
            "result": self.result,
            "error": self.error,
        }


class JobScheduler:
    """Run submitted callables on a bounded worker pool and expose their status."""

    def __init__(self, *, max_workers: int = 2, max_queued: int = 8) -> None:
        if max_workers < 1 or max_queued < 0:
            raise ValueError("max_workers must be positive and max_queued cannot be negative")
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="hhip-job")
        self._capacity = threading.BoundedSemaphore(max_workers + max_queued)
        self._lock = threading.Lock()
        self._jobs: dict[str, _Job] = {}
        self._active_dedupe_keys: dict[str, str] = {}

    def submit(
        self,
        job_type: str,
        operation: Callable[..., Any],
        *args: Any,
        dedupe_key: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        with self._lock:
            if dedupe_key:
                active_id = self._active_dedupe_keys.get(dedupe_key)
                active_job = self._jobs.get(active_id or "")
                if active_job and active_job.status in {"queued", "running"}:
                    return copy.deepcopy(active_job.to_dict())

            if not self._capacity.acquire(blocking=False):
                raise JobQueueFull("The background job queue is full")

            job = _Job(job_id=uuid.uuid4().hex, job_type=job_type, dedupe_key=dedupe_key)
            self._jobs[job.job_id] = job
            if dedupe_key:
                self._active_dedupe_keys[dedupe_key] = job.job_id

        try:
            self._executor.submit(self._run, job.job_id, operation, args, kwargs)
        except Exception:
            with self._lock:
                self._jobs.pop(job.job_id, None)
                if dedupe_key and self._active_dedupe_keys.get(dedupe_key) == job.job_id:
                    self._active_dedupe_keys.pop(dedupe_key, None)
            self._capacity.release()
            raise
        return self.get(job.job_id) or job.to_dict()

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return copy.deepcopy(job.to_dict()) if job else None

    def _run(
        self,
        job_id: str,
        operation: Callable[..., Any],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.status = "running"
            job.started_at = time.time()

        try:
            result = operation(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001
            with self._lock:
                job.status = "failed"
                job.error = str(exc) or exc.__class__.__name__
                job.finished_at = time.time()
        else:
            with self._lock:
                job.status = "succeeded"
                job.result = result
                job.finished_at = time.time()
        finally:
            with self._lock:
                if job.dedupe_key and self._active_dedupe_keys.get(job.dedupe_key) == job_id:
                    self._active_dedupe_keys.pop(job.dedupe_key, None)
            self._capacity.release()

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)