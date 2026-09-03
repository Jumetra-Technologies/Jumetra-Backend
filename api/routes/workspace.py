"""Research workspace API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/workspace", tags=["workspace"])


@router.get("/projects")
def list_projects(request: Request) -> list[dict]:
    return request.app.state.workspace_service.list_projects()


@router.get("/projects/{project_id}")
def get_project(project_id: str, request: Request) -> dict:
    try:
        return request.app.state.workspace_service.get_project(project_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
