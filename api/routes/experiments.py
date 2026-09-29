"""Experiment API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi import APIRouter, HTTPException, Request, Response

from ..services.job_scheduler import JobQueueFull
from ..schemas import ExperimentDetail, ExperimentStartRequest, ExperimentStatusResponse, ExperimentSummary

router = APIRouter(prefix="/experiments", tags=["experiments"])


@router.get("", response_model=list[ExperimentSummary])
def list_experiments(request: Request, response: Response) -> list[ExperimentSummary]:
    data_service = request.app.state.data_service
    cached = data_service.get_cached_experiment_summaries()
    stale = data_service.experiment_summary_cache_is_stale()
    if stale:
        response.headers["X-HHIP-Data-Status"] = "refreshing"
        try:
            request.app.state.job_scheduler.submit(
                "experiment_summary_refresh",
                data_service.refresh_experiment_summary_cache,
                dedupe_key="experiment-summary-index",
            )
        except JobQueueFull:
            response.headers["X-HHIP-Data-Status"] = "stale"
    else:
        response.headers["X-HHIP-Data-Status"] = "fresh"
    return cached or []


@router.post("/start", response_model=ExperimentStatusResponse)
def start_experiment(body: ExperimentStartRequest, request: Request) -> ExperimentStatusResponse:
    try:
        result = request.app.state.experiment_service.start(
            name=body.name,
            devices=body.devices,
            strategy=body.strategy,
            duration_ms=body.duration_ms,
            sync_interval_ms=body.sync_interval_ms,
            metadata=body.metadata,
        )
        return ExperimentStatusResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{experiment_id}/status", response_model=ExperimentStatusResponse)
def get_experiment_status(experiment_id: str, request: Request) -> ExperimentStatusResponse:
    try:
        result = request.app.state.experiment_service.status(experiment_id)
        return ExperimentStatusResponse(**result)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{experiment_id}/pause", response_model=ExperimentStatusResponse)
def pause_experiment(experiment_id: str, request: Request) -> ExperimentStatusResponse:
    try:
        result = request.app.state.experiment_service.pause(experiment_id)
        return ExperimentStatusResponse(**result)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{experiment_id}/stop", response_model=ExperimentStatusResponse)
def stop_experiment(experiment_id: str, request: Request) -> ExperimentStatusResponse:
    try:
        result = request.app.state.experiment_service.stop(experiment_id)
        return ExperimentStatusResponse(**result)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{experiment_id}", response_model=ExperimentDetail)
def get_experiment(experiment_id: str, request: Request) -> ExperimentDetail:
    try:
        return request.app.state.data_service.get_experiment(experiment_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
