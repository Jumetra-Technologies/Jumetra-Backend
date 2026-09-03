"""Live hybrid workspace hardware nodes API — Sprint 29."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/workspace/hardware", tags=["workspace-hardware"])


class ReconnectRequest(BaseModel):
    device_id: str = ""
    project_id: str = ""


class DisconnectRequest(BaseModel):
    device_id: str


class LayoutUpdateRequest(BaseModel):
    position: Optional[dict[str, float]] = None
    rotation: Optional[float] = None
    collapsed: Optional[bool] = None


@router.get("")
@router.get("/")
def list_workspace_hardware(request: Request, workspace_id: str = "") -> dict[str, Any]:
    svc = request.app.state.workspace_hardware_service
    return svc.list_hardware(workspace_id)


@router.get("/events")
def list_hardware_events(request: Request, limit: int = 100) -> dict[str, Any]:
    return request.app.state.workspace_hardware_service.events(limit=limit)


@router.post("/reconnect")
def reconnect_hardware(body: ReconnectRequest, request: Request) -> dict[str, Any]:
    return request.app.state.workspace_hardware_service.reconnect(
        device_id=body.device_id,
        project_id=body.project_id,
    )


@router.post("/disconnect")
def disconnect_hardware(body: DisconnectRequest, request: Request) -> dict[str, Any]:
    result = request.app.state.workspace_hardware_service.disconnect(body.device_id)
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=f"hardware node not found: {body.device_id}")
    return result


@router.get("/{device_id}")
def get_workspace_hardware(device_id: str, request: Request) -> dict[str, Any]:
    try:
        return request.app.state.workspace_hardware_service.get_hardware(device_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/{device_id}/layout")
def patch_hardware_layout(
    device_id: str,
    body: LayoutUpdateRequest,
    request: Request,
) -> dict[str, Any]:
    try:
        return request.app.state.workspace_hardware_service.update_layout(
            device_id,
            position=body.position,
            rotation=body.rotation,
            collapsed=body.collapsed,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
