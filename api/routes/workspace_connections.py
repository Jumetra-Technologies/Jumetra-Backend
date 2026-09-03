"""Workspace hybrid wiring REST API — Sprint 30."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/workspace/connections", tags=["workspace-wiring"])


class ConnectionCreateRequest(BaseModel):
    source_device: str = ""
    source_pin: str = ""
    destination_device: str = ""
    destination_pin: str = ""
    # aliases
    source: str = ""
    target: str = ""
    source_handle: str = ""
    target_handle: str = ""
    wire_type: str = "digital"
    protocol: str = ""
    workspace_id: str = ""
    transport: str = ""
    auto: bool = True
    drag: bool = False
    force: bool = False
    source_kind: str = "unknown"
    destination_kind: str = "unknown"
    source_pin_type: str = "GPIO"
    destination_pin_type: str = "GPIO"
    source_voltage: float = 3.3
    destination_voltage: float = 3.3
    source_supports_input: bool = True
    source_supports_output: bool = True
    destination_supports_input: bool = True
    destination_supports_output: bool = True
    source_available: bool = True
    destination_available: bool = True
    source_meta: Optional[dict[str, Any]] = None
    destination_meta: Optional[dict[str, Any]] = None
    routing: Optional[list[dict[str, float]]] = None


class ConnectionPatchRequest(BaseModel):
    wire_type: Optional[str] = None
    wire_color: Optional[str] = None
    direction: Optional[str] = None
    status: Optional[str] = None
    routing: Optional[list[dict[str, float]]] = None
    latency_ms: Optional[float] = None
    transport: Optional[str] = None


class PinWriteRequest(BaseModel):
    device_id: str
    pin: str
    value: Any = 0
    mode: str = ""
    virtual_node_id: str = ""


class PinModeRequest(BaseModel):
    device_id: str
    pin: str
    mode: str = Field(..., description="HIGH|LOW|INPUT|OUTPUT|PWM|PULLUP|PULLDOWN|ANALOG")


class HighlightRequest(BaseModel):
    start_device: str
    start_pin: str
    end_device: str
    end_pin: str


@router.get("")
@router.get("/")
def list_connections(request: Request, workspace_id: str = "") -> dict[str, Any]:
    return request.app.state.workspace_wiring_service.list_connections(workspace_id)


@router.post("")
@router.post("/")
def create_connection(body: ConnectionCreateRequest, request: Request) -> dict[str, Any]:
    try:
        return request.app.state.workspace_wiring_service.create_connection(body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/preview")
def preview_connection(body: ConnectionCreateRequest, request: Request) -> dict[str, Any]:
    return request.app.state.workspace_wiring_service.preview(body.model_dump())


@router.post("/highlight")
def highlight_path(body: HighlightRequest, request: Request) -> dict[str, Any]:
    return request.app.state.workspace_wiring_service.highlight(
        body.start_device, body.start_pin, body.end_device, body.end_pin
    )


@router.post("/pin-write")
def pin_write(body: PinWriteRequest, request: Request) -> dict[str, Any]:
    return request.app.state.workspace_wiring_service.write_pin(body.model_dump())


@router.post("/pin-mode")
def pin_mode(body: PinModeRequest, request: Request) -> dict[str, Any]:
    return request.app.state.workspace_wiring_service.set_pin_mode(body.model_dump())


@router.get("/pin/{device_id}/{pin}")
def inspect_pin(device_id: str, pin: str, request: Request) -> dict[str, Any]:
    return request.app.state.workspace_wiring_service.inspect_pin(device_id, pin)


@router.get("/{connection_id}")
def get_connection(connection_id: str, request: Request) -> dict[str, Any]:
    try:
        return request.app.state.workspace_wiring_service.get_connection(connection_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/{connection_id}")
def patch_connection(
    connection_id: str, body: ConnectionPatchRequest, request: Request
) -> dict[str, Any]:
    try:
        patch = {k: v for k, v in body.model_dump().items() if v is not None}
        return request.app.state.workspace_wiring_service.patch_connection(connection_id, patch)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{connection_id}")
def delete_connection(connection_id: str, request: Request) -> dict[str, Any]:
    try:
        return request.app.state.workspace_wiring_service.delete_connection(connection_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
