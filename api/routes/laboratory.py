"""Virtual laboratory API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field


class LaboratoryCreateRequest(BaseModel):
    name: str
    controller_id: str
    component_ids: list[str] = Field(default_factory=list)
    description: str = ""
    metadata: dict = Field(default_factory=dict)


class AdvanceRequest(BaseModel):
    delta_ms: int = 100


class ActuatorCommandRequest(BaseModel):
    instance_id: str
    action: str
    value: object = None


router = APIRouter(prefix="/laboratory", tags=["laboratory"])


@router.post("/create")
def create_laboratory(body: LaboratoryCreateRequest, request: Request) -> dict:
    try:
        return request.app.state.laboratory_service.create(
            name=body.name,
            controller_id=body.controller_id,
            component_ids=body.component_ids,
            description=body.description,
            metadata=body.metadata,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{laboratory_id}/start")
def start_laboratory(laboratory_id: str, request: Request) -> dict:
    try:
        return request.app.state.laboratory_service.start(laboratory_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{laboratory_id}")
def get_laboratory(laboratory_id: str, request: Request) -> dict:
    try:
        return request.app.state.laboratory_service.get(laboratory_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{laboratory_id}/simulation")
def get_simulation(laboratory_id: str, request: Request) -> dict:
    try:
        return request.app.state.laboratory_service.get_simulation(laboratory_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{laboratory_id}/simulation/pause")
def pause_simulation(laboratory_id: str, request: Request) -> dict:
    try:
        return request.app.state.laboratory_service.pause_simulation(laboratory_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{laboratory_id}/simulation/stop")
def stop_simulation(laboratory_id: str, request: Request) -> dict:
    try:
        return request.app.state.laboratory_service.stop_simulation(laboratory_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{laboratory_id}/simulation/advance")
def advance_simulation(laboratory_id: str, body: AdvanceRequest, request: Request) -> dict:
    try:
        return request.app.state.laboratory_service.advance_simulation(
            laboratory_id, body.delta_ms
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{laboratory_id}/simulation/command")
def actuator_command(laboratory_id: str, body: ActuatorCommandRequest, request: Request) -> dict:
    try:
        return request.app.state.laboratory_service.send_command(
            laboratory_id, body.instance_id, body.action, body.value
        )
    except (KeyError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
