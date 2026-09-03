"""Microcontroller controller API routes."""

from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter(prefix="/controllers", tags=["controllers"])


@router.get("")
def list_controllers(request: Request) -> list[dict]:
    return request.app.state.component_service.list_controllers()
