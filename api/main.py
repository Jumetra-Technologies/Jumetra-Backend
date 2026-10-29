"""HHIP FastAPI application — research operations platform."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from engine.events.dashboard_publisher import DashboardEventPublisher

from engine.discovery.service import HardwareDiscoveryService
from engine.events.event_bus import EventBus
from engine.devices.device_manager import DeviceManager

from auth.firebase import init_firebase
from auth.account_routes import router as account_router
from auth.routes import router as auth_router
from auth.tokens import session_secret
from database import ensure_identity_schema

from .db import init_db
from .routes.analytics import router as analytics_router
from .routes.components import router as components_router
from .routes.components_v2 import router as components_v2_router
from .routes.controllers import router as controllers_router
from .routes.devices import router as devices_router
from .routes.discovery import router as discovery_router
from .routes.engineering_workspace import router as engineering_workspace_router
from .routes.experiments import router as experiments_router
from .routes.hybrid import router as hybrid_router
from .routes.jobs import router as jobs_router
from .routes.laboratory import router as laboratory_router
from .routes.firmware import router as firmware_router
from .routes.workspace import router as workspace_router
from .routes.workspace_hardware import router as workspace_hardware_router
from .routes.workspace_connections import router as workspace_connections_router
from .routes.ws import WebSocketEventBridge, router as ws_router
from .services.component_service import ComponentService
from .services.component_v2_service import ComponentEngineV2Service
from .services.data_service import DataService
from .services.discovery_service import DiscoveryService
from .services.engineering_workspace_service import EngineeringWorkspaceService
from .services.experiment_service import ExperimentService
from .services.hybrid_service import HybridService
from .services.job_scheduler import JobScheduler
from .services.laboratory_service import LaboratoryService
from .services.workspace_hardware_service import WorkspaceHardwareService
from .services.workspace_wiring_service import WorkspaceWiringService
from .services.workspace_service import WorkspaceService
from engine.firmware import FirmwareStudioService
from security.auth_middleware import AuthenticatedWriteMiddleware


def _default_data_dir() -> Path:
    env = os.environ.get("HHIP_DATA_DIR")
    if env:
        return Path(env)
    return Path(__file__).resolve().parent.parent / "data"


def _cors_origins() -> list[str]:
    configured = os.environ.get("HHIP_CORS_ORIGINS", "")
    origins = [origin.strip() for origin in configured.split(",") if origin.strip()]
    return origins or [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
        "https://hhipsystemv0.web.app",
        "https://hhipsystemv0.firebaseapp.com",
    ]


def _cors_origin_regex() -> str:
    return (
        r"https?://(localhost|127\.0\.0\.1|192\.168\.\d{1,3}\.\d{1,3})(:\d+)?|"
        r"https://[a-z0-9.-]+\.(web\.app|firebaseapp\.com|hosted\.app|run\.app)"
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    data_dir = getattr(app.state, "data_dir", None) or _default_data_dir()
    publisher = DashboardEventPublisher()
    event_bus = EventBus()
    device_manager = DeviceManager()
    device_manager.bind_event_bus(event_bus)
    discovery_inner = HardwareDiscoveryService(
        event_bus=event_bus,
        device_manager=device_manager,
        dashboard_publisher=publisher,
        scan_interval_s=2.0,
    )
    discovery_service = DiscoveryService(discovery_inner)
    if os.environ.get("HHIP_DISABLE_DISCOVERY", "").lower() not in {"1", "true", "yes"}:
        discovery_service.start()

    app.state.job_scheduler = JobScheduler(max_workers=2, max_queued=8)
    app.state.data_service = DataService(data_dir)
    app.state.job_scheduler.submit(
        "experiment_summary_refresh",
        app.state.data_service.refresh_experiment_summary_cache,
        dedupe_key="experiment-summary-index",
    )
    app.state.db_factory = init_db(data_dir)
    ensure_identity_schema(app.state.db_factory)
    init_firebase()
    app.state.session_secret = session_secret(data_dir)
    app.state.publisher = publisher
    app.state.event_bus = event_bus
    app.state.device_manager = device_manager
    app.state.discovery_service = discovery_service
    app.state.experiment_service = ExperimentService(data_dir, publisher)
    app.state.workspace_service = WorkspaceService(
        app.state.db_factory,
        app.state.data_service,
        data_dir,
    )
    app.state.component_service = ComponentService()
    app.state.component_v2_service = ComponentEngineV2Service(event_bus=event_bus)
    app.state.laboratory_service = LaboratoryService(data_dir=data_dir)
    app.state.hybrid_service = HybridService(data_dir=data_dir, event_bus=event_bus)
    app.state.engineering_workspace_service = EngineeringWorkspaceService(data_dir=data_dir)
    app.state.workspace_hardware_service = WorkspaceHardwareService(
        data_dir=data_dir,
        event_bus=event_bus,
        hybrid_service=app.state.hybrid_service,
    )
    app.state.workspace_wiring_service = WorkspaceWiringService(
        data_dir=data_dir,
        event_bus=event_bus,
        hybrid_service=app.state.hybrid_service,
    )
    app.state.firmware_service = FirmwareStudioService(
        data_dir=data_dir,
        event_bus=event_bus,
        hybrid_service=app.state.hybrid_service,
        wire_manager=app.state.workspace_wiring_service.manager,
        workspace_sync=app.state.workspace_hardware_service.sync,
        force_dry_run=os.environ.get("HHIP_FIRMWARE_DRY_RUN", "").lower() in ("1", "true", "yes"),
    )
    app.state.ws_bridge = WebSocketEventBridge(publisher)
    try:
        yield
    finally:
        discovery_service.stop()
        app.state.job_scheduler.shutdown()


def create_app(*, data_dir: Path | str | None = None) -> FastAPI:
    app = FastAPI(
        title="HHIP Research Platform API",
        description="Real-time research operations platform for HHIP",
        version="3.0.0",
        lifespan=lifespan,
    )
    if data_dir is not None:
        app.state.data_dir = Path(data_dir)

    allowed_origins = _cors_origins()
    origin_pattern = _cors_origin_regex()
    app.state.allowed_origins = allowed_origins
    app.state.origin_pattern = origin_pattern
    app.state.require_auth = os.environ.get("HHIP_REQUIRE_AUTH", "true").lower() not in {
        "0",
        "false",
        "no",
    }

    app.add_middleware(
        AuthenticatedWriteMiddleware,
        enabled=app.state.require_auth,
        allowed_origins=allowed_origins,
        origin_pattern=origin_pattern,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_origin_regex=origin_pattern,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth_router)
    app.include_router(account_router)
    app.include_router(experiments_router)
    app.include_router(devices_router)
    app.include_router(analytics_router)
    app.include_router(workspace_router)
    app.include_router(workspace_hardware_router)
    app.include_router(workspace_connections_router)
    app.include_router(firmware_router)
    app.include_router(jobs_router)
    app.include_router(components_router)
    app.include_router(components_v2_router)
    app.include_router(controllers_router)
    app.include_router(laboratory_router)
    app.include_router(hybrid_router)
    app.include_router(engineering_workspace_router)
    app.include_router(discovery_router)
    app.include_router(ws_router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
