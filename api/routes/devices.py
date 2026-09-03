"""Device API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ..schemas import DeviceDetail, DeviceSummary

router = APIRouter(prefix="/devices", tags=["devices"])


@router.get("", response_model=list[DeviceSummary])
def list_devices(request: Request) -> list[DeviceSummary]:
    return request.app.state.data_service.list_devices()


@router.get("/{device_id}", response_model=DeviceDetail)
def get_device(device_id: str, request: Request) -> DeviceDetail:
    try:
        return request.app.state.data_service.get_device(device_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
