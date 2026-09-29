"""Status endpoint for background API jobs."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{job_id}")
def get_job(job_id: str, request: Request) -> dict[str, object]:
    job = request.app.state.job_scheduler.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job