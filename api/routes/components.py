"""Component catalog API routes."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request

router = APIRouter(prefix="/components", tags=["components"])


@router.get("/search")
def search_components(
    request: Request,
    q: str = Query("", description="Search query"),
    category: Optional[str] = Query(None),
    interface: Optional[str] = Query(None),
    controller_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
) -> list[dict]:
    return request.app.state.component_service.search(
        q,
        category=category,
        interface=interface,
        controller_id=controller_id,
        limit=limit,
    )


@router.get("/debug")
def debug_components(request: Request) -> dict:
    """Diagnostics for catalog loading (path, counts, samples)."""
    return request.app.state.component_service.debug()


@router.get("/{component_id}")
def get_component(component_id: str, request: Request) -> dict:
    try:
        return request.app.state.component_service.get_component(component_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{component_id}/versions")
def list_component_versions(component_id: str, request: Request) -> list[dict]:
    try:
        return request.app.state.component_service.list_versions(component_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{component_id}/metadata")
def get_component_metadata(component_id: str, request: Request) -> dict:
    try:
        return request.app.state.component_service.get_metadata(component_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
