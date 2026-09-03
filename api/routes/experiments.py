"""Experiment API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ..schemas import ExperimentDetail, ExperimentStartRequest, ExperimentStatusResponse, ExperimentSummary

router = APIRouter(prefix="/experiments", tags=["experiments"])


@router.get("", response_model=list[ExperimentSummary])
def list_experiments(request: Request) -> list[ExperimentSummary]:
    return request.app.state.data_service.list_experiments()


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
