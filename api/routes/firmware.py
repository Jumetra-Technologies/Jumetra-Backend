"""Embedded firmware studio REST API — Sprint 31."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from auth.routes import current_user_id

from ..services.job_scheduler import JobQueueFull

router = APIRouter(prefix="/firmware", tags=["firmware"])

LOCAL_OWNER = "local"


def firmware_owner(request: Request, response: Response) -> str:
    """Whose firmware projects these are: the signed-in person.

    Every project belongs to the account that created it; others get a 404,
    reads included. With sign-in switched off (HHIP_REQUIRE_AUTH=false, for
    local runs and tests) a signed-out caller is the single "local" owner.
    """
    if not getattr(request.app.state, "require_auth", True):
        try:
            return current_user_id(request, response)
        except HTTPException:
            return LOCAL_OWNER
    return current_user_id(request, response)


def _owned(request: Request, project_id: str, owner: str) -> None:
    try:
        request.app.state.firmware_service.check_owner(project_id, owner)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


class CreateProjectRequest(BaseModel):
    name: str = "Untitled Firmware"
    project_type: str = "arduino-sketch"
    board_type: str = "esp32"
    language: str = ""
    template_id: str = "blink"
    template: str = ""


class SaveFileRequest(BaseModel):
    path: str
    content: str


class BuildRequest(BaseModel):
    project_id: str
    use_cache: bool = True


class UploadRequest(BaseModel):
    project_id: str
    port: str = ""
    build_id: str = ""


class SerialRequest(BaseModel):
    action: str = ""  # pause|resume|clear|write|export
    line: str = ""
    port: str = ""
    baud: int = 115200
    query: str = ""
    limit: int = 500


@router.get("/projects")
def list_projects(request: Request, owner: str = Depends(firmware_owner)) -> dict[str, Any]:
    return request.app.state.firmware_service.list_projects(owner)


@router.post("/projects")
def create_project(body: CreateProjectRequest, request: Request, owner: str = Depends(firmware_owner)) -> dict[str, Any]:
    data = body.model_dump()
    if data.get("template") and not data.get("template_id"):
        data["template_id"] = data["template"]
    return request.app.state.firmware_service.create_project(data, owner)


@router.get("/projects/{project_id}")
def get_project(project_id: str, request: Request, owner: str = Depends(firmware_owner)) -> dict[str, Any]:
    try:
        return request.app.state.firmware_service.get_project(project_id, owner)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/projects/{project_id}/files")
def save_file(project_id: str, body: SaveFileRequest, request: Request, owner: str = Depends(firmware_owner)) -> dict[str, Any]:
    _owned(request, project_id, owner)
    try:
        return request.app.state.firmware_service.save_file(project_id, body.path, body.content)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/templates")
def templates(request: Request) -> dict[str, Any]:
    return request.app.state.firmware_service.list_templates()


@router.get("/toolchains")
def toolchains(request: Request) -> dict[str, Any]:
    return request.app.state.firmware_service.list_toolchains()


@router.post("/build")
def build_firmware(body: BuildRequest, request: Request, owner: str = Depends(firmware_owner)) -> dict[str, Any]:
    _owned(request, body.project_id, owner)
    try:
        return request.app.state.firmware_service.build(body.project_id, use_cache=body.use_cache)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/build/jobs", status_code=status.HTTP_202_ACCEPTED)
def queue_firmware_build(body: BuildRequest, request: Request, owner: str = Depends(firmware_owner)) -> dict[str, Any]:
    _owned(request, body.project_id, owner)

    try:
        return request.app.state.job_scheduler.submit(
            "firmware_build",
            request.app.state.firmware_service.build,
            body.project_id,
            use_cache=body.use_cache,
            dedupe_key=f"firmware-build:{body.project_id}:{body.use_cache}",
        )
    except JobQueueFull as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc


@router.post("/upload")
def upload_firmware(body: UploadRequest, request: Request, owner: str = Depends(firmware_owner)) -> dict[str, Any]:
    _owned(request, body.project_id, owner)
    try:
        return request.app.state.firmware_service.upload(
            body.project_id, port=body.port, build_id=body.build_id
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/logs")
def firmware_logs(request: Request, limit: int = 200, _owner: str = Depends(firmware_owner)) -> dict[str, Any]:
    return request.app.state.firmware_service.logs(limit=limit)


@router.get("/serial")
def get_serial(
    request: Request,
    _owner: str = Depends(firmware_owner),
    limit: int = 500,
    query: str = "",
) -> dict[str, Any]:
    return request.app.state.firmware_service.serial(limit=limit, query=query)


@router.post("/serial")
def post_serial(body: SerialRequest, request: Request, _owner: str = Depends(firmware_owner)) -> dict[str, Any]:
    return request.app.state.firmware_service.serial(
        limit=body.limit,
        query=body.query,
        action=body.action,
        line=body.line,
        port=body.port,
        baud=body.baud,
    )
