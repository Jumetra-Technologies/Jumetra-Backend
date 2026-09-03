"""Component Engine v2 API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

router = APIRouter(prefix="/components/v2", tags=["components-v2"])


class BindingRequest(BaseModel):
    component_id: str
    instance_id: str = ""
    mode: str = "virtual"
    transport: str = ""
    device_id: str = ""
    port: str = ""


class SwitchBindingRequest(BaseModel):
    mode: str
    device_id: str = ""
    transport: str = ""
    port: str = ""


class SimulateTickRequest(BaseModel):
    instance_id: str = ""
    t_s: float = 0.0
    inputs: dict = Field(default_factory=dict)


@router.get("/search")
def search_v2(
    request: Request,
    q: str = Query(""),
    category: str | None = None,
    interface: str | None = None,
    limit: int = Query(50, ge=1, le=200),
) -> dict:
    return request.app.state.component_v2_service.search(q, category=category, interface=interface, limit=limit)


@router.get("/debug")
def debug_v2(request: Request) -> dict:
    return request.app.state.component_v2_service.debug()


@router.get("/packages")
def list_packages(request: Request) -> list:
    return request.app.state.component_v2_service.list_packages()


@router.get("/{component_id}/renderer.svg")
def get_renderer(component_id: str, request: Request) -> Response:
    try:
        svg = request.app.state.component_v2_service.get_renderer_svg(component_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(content=svg, media_type="image/svg+xml")


@router.get("/{component_id}")
def get_component_v2(component_id: str, request: Request) -> dict:
    try:
        return request.app.state.component_v2_service.get(component_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/bindings")
def create_binding(body: BindingRequest, request: Request) -> dict:
    return request.app.state.component_v2_service.create_binding(body.model_dump())


@router.post("/bindings/{instance_id}/mode")
def switch_binding(instance_id: str, body: SwitchBindingRequest, request: Request) -> dict:
    try:
        return request.app.state.component_v2_service.switch_binding(
            instance_id,
            body.mode,
            device_id=body.device_id,
            transport=body.transport,
            port=body.port,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{component_id}/simulate")
def simulate_tick(component_id: str, body: SimulateTickRequest, request: Request) -> dict:
    try:
        return request.app.state.component_v2_service.simulate_tick(
            component_id,
            instance_id=body.instance_id,
            t_s=body.t_s,
            inputs=body.inputs,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
