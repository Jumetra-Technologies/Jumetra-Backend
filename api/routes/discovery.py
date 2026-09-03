"""Hardware discovery REST API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/discovery", tags=["discovery"])


class FirmwareUploadRequest(BaseModel):
    port: str
    firmware_path: str = Field(default="", description="Optional local firmware binary path")


@router.get("/devices")
def list_discovered_devices(request: Request) -> dict[str, Any]:
    service = request.app.state.discovery_service
    return {"devices": service.list_devices(), "count": len(service.list_devices())}


@router.get("/devices/{port:path}")
def get_discovered_device(port: str, request: Request) -> dict[str, Any]:
    service = request.app.state.discovery_service
    device = service.get_device(port)
    if device is None:
        raise HTTPException(status_code=404, detail=f"Port {port!r} not found")
    return device


@router.post("/scan")
def trigger_scan(request: Request) -> dict[str, Any]:
    service = request.app.state.discovery_service
    devices = service.scan_now()
    return {"devices": devices, "count": len(devices)}


@router.post("/devices/{port:path}/connect")
def connect_device(port: str, request: Request) -> dict[str, Any]:
    """Force an immediate handshake on a port."""
    inner = request.app.state.discovery_service.inner
    device = inner.get_device(port)
    if device is None:
        raise HTTPException(status_code=404, detail=f"Port {port!r} not found")
    inner._probe_device(device, is_new=True)  # noqa: SLF001
    updated = inner.get_device(port)
    return updated.to_dict() if updated else {"port": port, "status": "error"}


@router.post("/firmware/upload")
def upload_firmware(body: FirmwareUploadRequest, request: Request) -> dict[str, Any]:
    """Placeholder for HHIP firmware upload — returns guidance until flasher ships."""
    device = request.app.state.discovery_service.get_device(body.port)
    return {
        "ok": False,
        "port": body.port,
        "message": "Firmware upload is not yet automated. Flash HHIP firmware using Arduino IDE or esptool, then rescan.",
        "device": device,
        "install_url": "https://github.com/Okelo123/Hybrid-Hardware-Simulation",
    }
