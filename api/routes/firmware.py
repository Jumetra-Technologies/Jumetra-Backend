"""Embedded firmware studio REST API — Sprint 31."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/firmware", tags=["firmware"])


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
def list_projects(request: Request) -> dict[str, Any]:
    return request.app.state.firmware_service.list_projects()


@router.post("/projects")
def create_project(body: CreateProjectRequest, request: Request) -> dict[str, Any]:
    data = body.model_dump()
    if data.get("template") and not data.get("template_id"):
        data["template_id"] = data["template"]
    return request.app.state.firmware_service.create_project(data)


@router.get("/projects/{project_id}")
def get_project(project_id: str, request: Request) -> dict[str, Any]:
    try:
        return request.app.state.firmware_service.get_project(project_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/projects/{project_id}/files")
def save_file(project_id: str, body: SaveFileRequest, request: Request) -> dict[str, Any]:
    try:
        return request.app.state.firmware_service.save_file(project_id, body.path, body.content)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/templates")
def templates(request: Request) -> dict[str, Any]:
    return request.app.state.firmware_service.list_templates()


@router.get("/toolchains")
def toolchains(request: Request) -> dict[str, Any]:
    return request.app.state.firmware_service.list_toolchains()


@router.post("/build")
def build_firmware(body: BuildRequest, request: Request) -> dict[str, Any]:
    try:
        return request.app.state.firmware_service.build(body.project_id, use_cache=body.use_cache)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/upload")
def upload_firmware(body: UploadRequest, request: Request) -> dict[str, Any]:
    try:
        return request.app.state.firmware_service.upload(
            body.project_id, port=body.port, build_id=body.build_id
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/logs")
def firmware_logs(request: Request, limit: int = 200) -> dict[str, Any]:
    return request.app.state.firmware_service.logs(limit=limit)


@router.get("/serial")
def get_serial(
    request: Request,
    limit: int = 500,
    query: str = "",
) -> dict[str, Any]:
    return request.app.state.firmware_service.serial(limit=limit, query=query)


@router.post("/serial")
def post_serial(body: SerialRequest, request: Request) -> dict[str, Any]:
    return request.app.state.firmware_service.serial(
        limit=body.limit,
        query=body.query,
        action=body.action,
        line=body.line,
        port=body.port,
        baud=body.baud,
    )
