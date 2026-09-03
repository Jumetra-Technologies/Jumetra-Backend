"""Engineering laboratory workspace API.

Routes live under ``/engineering/workspace`` to avoid colliding with the
research ``/workspace/projects`` endpoints. Documented as the Sprint 26
workspace API surface.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

router = APIRouter(prefix="/engineering/workspace", tags=["engineering-workspace"])


class CreateWorkspaceRequest(BaseModel):
    name: str = "Untitled Workspace"
    project_id: str = ""


class RunRequest(BaseModel):
    speed: str = "1x"


class StepRequest(BaseModel):
    delta_ms: int = 100


class AddNodeRequest(BaseModel):
    component_id: str
    position: dict = Field(default_factory=lambda: {"x": 100, "y": 100})
    device_mode: str = "virtual"
    physical_port: str = ""
    physical_device_id: str = ""
    available: bool | None = None
    label: str = ""


class UpdateNodeRequest(BaseModel):
    position: dict | None = None
    device_mode: str | None = None
    properties: dict | None = None
    label: str | None = None
    pin_map: dict | None = None
    available: bool | None = None


class IdsRequest(BaseModel):
    ids: list[str] = Field(default_factory=list)


class AddWireRequest(BaseModel):
    source: str
    target: str
    source_handle: str = "out"
    target_handle: str = "in"
    protocol: str = "digital"
    voltage_v: float = 3.3


class SerialRequest(BaseModel):
    line: str


@router.get("/catalog")
def catalog(
    request: Request,
    q: str = "",
    category: str | None = None,
    interface: str | None = None,
    interfaces: str | None = None,
    voltage: float | None = None,
    voltages: str | None = None,
    controller_id: str | None = None,
) -> dict:
    iface_list = [i.strip() for i in (interfaces or "").split(",") if i.strip()]
    volt_list = [float(v) for v in (voltages or "").split(",") if v.strip()]
    return request.app.state.engineering_workspace_service.catalog(
        q=q,
        category=category,
        interface=interface,
        interfaces=iface_list or None,
        voltage=voltage,
        voltages=volt_list or None,
        controller_id=controller_id,
    )


@router.get("")
def list_workspaces(request: Request) -> list:
    return request.app.state.engineering_workspace_service.list_workspaces()


@router.post("")
def create_workspace(body: CreateWorkspaceRequest, request: Request) -> dict:
    return request.app.state.engineering_workspace_service.create(
        name=body.name, project_id=body.project_id
    )


@router.get("/{workspace_id}")
def get_workspace(workspace_id: str, request: Request) -> dict:
    try:
        return request.app.state.engineering_workspace_service.get(workspace_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{workspace_id}/state")
def get_workspace_state(workspace_id: str, request: Request) -> dict:
    try:
        return request.app.state.engineering_workspace_service.get_state(workspace_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{workspace_id}/connect")
def connect_workspace(workspace_id: str, request: Request) -> dict:
    try:
        return request.app.state.engineering_workspace_service.connect(workspace_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{workspace_id}/disconnect")
def disconnect_workspace(workspace_id: str, request: Request) -> dict:
    try:
        return request.app.state.engineering_workspace_service.disconnect(workspace_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{workspace_id}/run")
def run_workspace(workspace_id: str, body: RunRequest, request: Request) -> dict:
    try:
        return request.app.state.engineering_workspace_service.run(workspace_id, body.speed)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{workspace_id}/pause")
def pause_workspace(workspace_id: str, request: Request) -> dict:
    try:
        return request.app.state.engineering_workspace_service.pause(workspace_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{workspace_id}/reset")
def reset_workspace(workspace_id: str, request: Request) -> dict:
    try:
        return request.app.state.engineering_workspace_service.reset(workspace_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{workspace_id}/step")
def step_workspace(workspace_id: str, body: StepRequest, request: Request) -> dict:
    try:
        return request.app.state.engineering_workspace_service.step(workspace_id, body.delta_ms)
    except (KeyError, RuntimeError) as exc:
        code = 404 if isinstance(exc, KeyError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc


@router.post("/{workspace_id}/nodes")
def add_node(workspace_id: str, body: AddNodeRequest, request: Request) -> dict:
    try:
        return request.app.state.engineering_workspace_service.add_node(
            workspace_id,
            component_id=body.component_id,
            position=body.position,
            device_mode=body.device_mode,
            physical_port=body.physical_port,
            physical_device_id=body.physical_device_id,
            available=body.available,
            label=body.label,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/{workspace_id}/nodes/{node_id}")
def update_node(workspace_id: str, node_id: str, body: UpdateNodeRequest, request: Request) -> dict:
    try:
        patch = {k: v for k, v in body.model_dump().items() if v is not None}
        return request.app.state.engineering_workspace_service.update_node(workspace_id, node_id, patch)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{workspace_id}/nodes/delete")
def delete_nodes(workspace_id: str, body: IdsRequest, request: Request) -> dict:
    try:
        return request.app.state.engineering_workspace_service.delete_nodes(workspace_id, body.ids)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{workspace_id}/nodes/duplicate")
def duplicate_nodes(workspace_id: str, body: IdsRequest, request: Request) -> list:
    try:
        return request.app.state.engineering_workspace_service.duplicate_nodes(workspace_id, body.ids)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{workspace_id}/wires")
def add_wire(workspace_id: str, body: AddWireRequest, request: Request) -> dict:
    try:
        return request.app.state.engineering_workspace_service.add_wire(
            workspace_id,
            source=body.source,
            target=body.target,
            source_handle=body.source_handle,
            target_handle=body.target_handle,
            protocol=body.protocol,
            voltage_v=body.voltage_v,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{workspace_id}/wires/delete")
def delete_wires(workspace_id: str, body: IdsRequest, request: Request) -> dict:
    try:
        return request.app.state.engineering_workspace_service.delete_wires(workspace_id, body.ids)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{workspace_id}/undo")
def undo(workspace_id: str, request: Request) -> dict:
    try:
        return request.app.state.engineering_workspace_service.undo(workspace_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{workspace_id}/redo")
def redo(workspace_id: str, request: Request) -> dict:
    try:
        return request.app.state.engineering_workspace_service.redo(workspace_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{workspace_id}/serial")
def send_serial(workspace_id: str, body: SerialRequest, request: Request) -> dict:
    try:
        return request.app.state.engineering_workspace_service.send_serial(workspace_id, body.line)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.websocket("/ws/{workspace_id}")
async def workspace_ws(websocket: WebSocket, workspace_id: str) -> None:
    """Realtime workspace stream — polls state without modifying Event Bus."""
    await websocket.accept()
    service = websocket.app.state.engineering_workspace_service
    try:
        while True:
            try:
                state = service.get_state(workspace_id)
                await websocket.send_json({"type": "workspace_state", "payload": state})
            except KeyError:
                await websocket.send_json({"type": "error", "payload": {"detail": "not found"}})
                break
            msg = await websocket.receive_text()
            if msg == "step":
                service.step(workspace_id, 100)
            elif msg == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        return
