from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.services.job_scheduler import JobQueueFull, JobScheduler


def _wait_for_job(client: TestClient, job_id: str, timeout_seconds: float = 3.0) -> dict:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        response = client.get(f"/jobs/{job_id}")
        assert response.status_code == 200
        job = response.json()
        if job["status"] in {"succeeded", "failed"}:
            return job
        time.sleep(0.01)
    raise AssertionError(f"job did not finish within {timeout_seconds} seconds")


def test_scheduler_tracks_results_deduplicates_and_bounds_pending_jobs():
    scheduler = JobScheduler(max_workers=1, max_queued=1)
    started = threading.Event()
    release = threading.Event()

    def blocked_operation() -> str:
        started.set()
        release.wait(timeout=2)
        return "finished"

    try:
        first = scheduler.submit(
            "blocked", blocked_operation, dedupe_key="same-operation"
        )
        assert started.wait(timeout=1)
        duplicate = scheduler.submit(
            "blocked", blocked_operation, dedupe_key="same-operation"
        )
        assert duplicate["job_id"] == first["job_id"]

        pending = scheduler.submit("pending", lambda: "next")
        with pytest.raises(JobQueueFull):
            scheduler.submit("rejected", lambda: None)

        release.set()
        first_result = _wait_for_scheduler_job(scheduler, first["job_id"])
        pending_result = _wait_for_scheduler_job(scheduler, pending["job_id"])
        assert first_result["status"] == "succeeded"
        assert first_result["result"] == "finished"
        assert pending_result["status"] == "succeeded"
        assert pending_result["result"] == "next"
    finally:
        release.set()
        scheduler.shutdown()


def _wait_for_scheduler_job(
    scheduler: JobScheduler,
    job_id: str,
    timeout_seconds: float = 2.0,
) -> dict:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        job = scheduler.get(job_id)
        if job and job["status"] in {"succeeded", "failed"}:
            return job
        time.sleep(0.01)
    raise AssertionError(f"job did not finish within {timeout_seconds} seconds")


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("HHIP_FIRMWARE_DRY_RUN", "1")
    app = create_app(data_dir=tmp_path)
    with TestClient(app) as test_client:
        yield test_client


def test_firmware_build_job_returns_immediately_and_exposes_result(client: TestClient):
    project_response = client.post(
        "/firmware/projects",
        json={"name": "Queued Build", "board_type": "esp32", "template_id": "blink"},
    )
    assert project_response.status_code == 200
    project_id = project_response.json()["project_id"]

    started_at = time.monotonic()
    response = client.post(
        "/firmware/build/jobs",
        json={"project_id": project_id, "use_cache": False},
    )
    elapsed = time.monotonic() - started_at

    assert response.status_code == 202
    assert elapsed < 1.0
    job_id = response.json()["job_id"]
    job = _wait_for_job(client, job_id)
    assert job["status"] == "succeeded"
    assert job["result"]["success"] is True
    assert client.get("/jobs/missing").status_code == 404


def test_experiment_list_returns_cached_data_while_refresh_runs(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    data_service = client.app.state.data_service
    deadline = time.monotonic() + 2.0
    while data_service.experiment_summary_cache_is_stale() and time.monotonic() < deadline:
        time.sleep(0.01)

    refresh_started = threading.Event()
    release_refresh = threading.Event()
    monkeypatch.setattr(data_service, "get_cached_experiment_summaries", lambda: [])
    monkeypatch.setattr(data_service, "experiment_summary_cache_is_stale", lambda: True)

    def delayed_refresh() -> dict[str, int]:
        refresh_started.set()
        release_refresh.wait(timeout=2)
        return {"experiment_count": 0}

    monkeypatch.setattr(data_service, "refresh_experiment_summary_cache", delayed_refresh)
    try:
        started_at = time.monotonic()
        response = client.get("/experiments")
        elapsed = time.monotonic() - started_at
        assert response.status_code == 200
        assert response.json() == []
        assert response.headers["x-hhip-data-status"] == "refreshing"
        assert elapsed < 1.0
        assert refresh_started.wait(timeout=1)
    finally:
        release_refresh.set()