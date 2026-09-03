"""WebSocket event stream for the research dashboard."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Callable

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from engine.events.dashboard_publisher import DashboardEvent, DashboardEventPublisher

router = APIRouter(tags=["websocket"])

Callback = Callable[[DashboardEvent], None]


class WebSocketEventBridge:
    """Bridge DashboardEventPublisher callbacks to WebSocket clients."""

    def __init__(self, publisher: DashboardEventPublisher) -> None:
        self._publisher = publisher
        self._connections: dict[WebSocket, Callback] = {}
        self._loop: asyncio.AbstractEventLoop | None = None

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        if self._loop is None:
            self._loop = asyncio.get_running_loop()

        def _on_event(event: DashboardEvent) -> None:
            if self._loop is None:
                return
            asyncio.run_coroutine_threadsafe(self.broadcast(event.to_dict()), self._loop)

        self._connections[websocket] = _on_event
        self._publisher.subscribe(_on_event)

        for event in self._publisher.history[-20:]:
            await websocket.send_text(json.dumps(event.to_dict()))

    async def disconnect(self, websocket: WebSocket) -> None:
        callback = self._connections.pop(websocket, None)
        if callback is not None:
            self._publisher.unsubscribe(callback)

    async def broadcast(self, payload: dict[str, Any]) -> None:
        message = json.dumps(payload)
        dead: list[WebSocket] = []
        for ws in list(self._connections):
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(ws)


@router.websocket("/ws/discovery")
async def websocket_discovery(websocket: WebSocket) -> None:
    """Live hardware discovery stream — pushes device list on hot-plug changes."""
    await websocket.accept()
    service = websocket.app.state.discovery_service
    loop = asyncio.get_running_loop()

    async def _send(devices: list) -> None:
        await websocket.send_json({"type": "discovery_update", "devices": devices})

    def _on_change(devices: list) -> None:
        asyncio.run_coroutine_threadsafe(_send(devices), loop)

    service.subscribe_ws(_on_change)
    await websocket.send_json({"type": "discovery_update", "devices": service.list_devices()})
    try:
        while True:
            msg = await websocket.receive_text()
            if msg == "scan":
                devices = service.scan_now()
                await websocket.send_json({"type": "discovery_update", "devices": devices})
            elif msg == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        service.unsubscribe_ws(_on_change)


@router.websocket("/ws/events")
async def websocket_events(websocket: WebSocket) -> None:
    bridge: WebSocketEventBridge = websocket.app.state.ws_bridge
    await bridge.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await bridge.disconnect(websocket)


@router.websocket("/ws/hardware")
async def websocket_hardware(websocket: WebSocket) -> None:
    """Sprint 29 — live hardware node / digital twin stream."""
    await websocket.accept()
    service = websocket.app.state.workspace_hardware_service
    sync = service.sync
    loop = asyncio.get_running_loop()

    async def _send(message: dict[str, Any]) -> None:
        await websocket.send_json(message)

    def _on_event(message: dict[str, Any]) -> None:
        asyncio.run_coroutine_threadsafe(_send(message), loop)

    sync.subscribe_ws(_on_event)
    await websocket.send_json(
        {
            "type": "hardware_snapshot",
            "event": "hardware_snapshot",
            "payload": {"hardware": sync.list_nodes()},
        }
    )
    try:
        while True:
            msg = await websocket.receive_text()
            if msg == "ping":
                await websocket.send_json({"type": "pong"})
            elif msg == "snapshot":
                await websocket.send_json(
                    {
                        "type": "hardware_snapshot",
                        "event": "hardware_snapshot",
                        "payload": {"hardware": sync.list_nodes()},
                    }
                )
    except WebSocketDisconnect:
        sync.unsubscribe_ws(_on_event)


@router.websocket("/ws/wiring")
async def websocket_wiring(websocket: WebSocket) -> None:
    """Sprint 30 — live wire / pin connection stream."""
    await websocket.accept()
    service = websocket.app.state.workspace_wiring_service
    manager = service.manager
    loop = asyncio.get_running_loop()

    async def _send(message: dict[str, Any]) -> None:
        await websocket.send_json(message)

    def _on_event(message: dict[str, Any]) -> None:
        asyncio.run_coroutine_threadsafe(_send(message), loop)

    manager.subscribe_ws(_on_event)
    await websocket.send_json(
        {
            "type": "wiring_snapshot",
            "event": "wiring_snapshot",
            "payload": {"connections": manager.list_connections()},
        }
    )
    try:
        while True:
            msg = await websocket.receive_text()
            if msg == "ping":
                await websocket.send_json({"type": "pong"})
            elif msg == "snapshot":
                await websocket.send_json(
                    {
                        "type": "wiring_snapshot",
                        "event": "wiring_snapshot",
                        "payload": {"connections": manager.list_connections()},
                    }
                )
    except WebSocketDisconnect:
        manager.unsubscribe_ws(_on_event)


@router.websocket("/ws/firmware")
async def websocket_firmware(websocket: WebSocket) -> None:
    """Sprint 31 — firmware build / upload / serial / GPIO debug stream."""
    await websocket.accept()
    service = websocket.app.state.firmware_service
    loop = asyncio.get_running_loop()

    async def _send(message: dict[str, Any]) -> None:
        await websocket.send_json(message)

    def _on_event(message: dict[str, Any]) -> None:
        asyncio.run_coroutine_threadsafe(_send(message), loop)

    service.subscribe_ws(_on_event)
    await websocket.send_json(
        {
            "type": "firmware_snapshot",
            "event": "firmware_snapshot",
            "payload": {
                "projects": service.list_projects().get("projects"),
                "toolchains": service.list_toolchains().get("toolchains"),
                "serial": service.serial(limit=50),
            },
        }
    )
    try:
        while True:
            msg = await websocket.receive_text()
            if msg == "ping":
                await websocket.send_json({"type": "pong"})
            elif msg == "snapshot":
                await websocket.send_json(
                    {
                        "type": "firmware_snapshot",
                        "event": "firmware_snapshot",
                        "payload": {"projects": service.list_projects().get("projects")},
                    }
                )
    except WebSocketDisconnect:
        service.unsubscribe_ws(_on_event)


@router.websocket("/ws/workspace/{workspace_id}")
async def websocket_workspace(websocket: WebSocket, workspace_id: str) -> None:
    """Sprint 26 alias — engineering workspace realtime stream."""
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
