"""Hybrid hardware bridge API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field


class HybridCreateRequest(BaseModel):
    name: str
    controller_id: str
    component_ids: list[str] = Field(default_factory=list)
    device_modes: dict[str, str] = Field(default_factory=dict)
    physical_device_id: str = "esp32_01"
    simulator_backend: str = "in-process"


class HybridAdvanceRequest(BaseModel):
    delta_ms: int = 100


class PhysicalConnectRequest(BaseModel):
    port: str = ""
    endpoint: str = ""
    board_type: str = "esp32"
    device_id: str = ""
    label: str = ""
    transport: str = ""
    username: str = "pi"


class PinConnectionRequest(BaseModel):
    virtual_node_id: str
    virtual_pin_id: str
    physical_device_id: str
    physical_pin_id: str
    workspace_id: str = ""


router = APIRouter(prefix="/hybrid", tags=["hybrid"])


# ---- Sprint 27/28 physical device routes (must precede /{experiment_id}) ----


@router.get("/devices")
def list_physical_devices(request: Request) -> dict:
    devices = request.app.state.hybrid_service.list_physical_devices()
    return {"devices": devices, "count": len(devices)}


@router.get("/profiles")
def list_hardware_profiles(request: Request) -> dict:
    profiles = request.app.state.hybrid_service.list_hardware_profiles()
    return {"profiles": profiles, "count": len(profiles)}


@router.post("/devices/connect")
def connect_physical_device(body: PhysicalConnectRequest, request: Request) -> dict:
    try:
        return request.app.state.hybrid_service.connect_physical_device(
            port=body.port,
            endpoint=body.endpoint,
            board_type=body.board_type,
            device_id=body.device_id,
            label=body.label,
            transport=body.transport,
            username=body.username,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/devices/{device_id}/pins")
def get_physical_device_pins(device_id: str, request: Request) -> dict:
    try:
        pins = request.app.state.hybrid_service.get_physical_pins(device_id)
        return {"device_id": device_id, "pins": pins, "count": len(pins)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/connections")
def create_pin_connection(body: PinConnectionRequest, request: Request) -> dict:
    try:
        return request.app.state.hybrid_service.create_pin_connection(
            virtual_node_id=body.virtual_node_id,
            virtual_pin_id=body.virtual_pin_id,
            physical_device_id=body.physical_device_id,
            physical_pin_id=body.physical_pin_id,
            workspace_id=body.workspace_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/connections")
def list_pin_connections(request: Request) -> dict:
    items = request.app.state.hybrid_service.list_pin_connections()
    return {"connections": items, "count": len(items)}


# ---- Sprint 25 experiment routes ----------------------------------------


@router.post("/create")
def create_hybrid_experiment(body: HybridCreateRequest, request: Request) -> dict:
    try:
        return request.app.state.hybrid_service.create(
            name=body.name,
            controller_id=body.controller_id,
            component_ids=body.component_ids,
            device_modes=body.device_modes,
            physical_device_id=body.physical_device_id,
            simulator_backend=body.simulator_backend,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/")
def list_hybrid_experiments(request: Request) -> list:
    return request.app.state.hybrid_service.list_experiments()


@router.get("/{experiment_id}")
def get_hybrid_experiment(experiment_id: str, request: Request) -> dict:
    try:
        return request.app.state.hybrid_service.get(experiment_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{experiment_id}/start")
def start_hybrid_experiment(experiment_id: str, request: Request) -> dict:
    try:
        return request.app.state.hybrid_service.start(experiment_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{experiment_id}/advance")
def advance_hybrid_experiment(
    experiment_id: str, body: HybridAdvanceRequest, request: Request
) -> dict:
    try:
        return request.app.state.hybrid_service.advance(experiment_id, body.delta_ms)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{experiment_id}/stop")
def stop_hybrid_experiment(experiment_id: str, request: Request) -> dict:
    try:
        return request.app.state.hybrid_service.stop(experiment_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
