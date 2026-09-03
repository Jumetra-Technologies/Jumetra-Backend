"""Firmware Studio orchestrator — projects, build, upload, serial, GPIO debug."""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional

from engine.events.event import Event
from engine.events.event_bus import EventBus

from .build_cache import BuildCache
from .compiler_adapter import BuildResult, CompilerAdapter
from .firmware_monitor import FirmwareMonitor
from .firmware_project import FirmwareProject, FirmwareProjectRepository, ProjectType
from .project_templates import default_language_for, generate_template, list_templates
from .serial_console import SerialConsole
from .toolchain_manager import ToolchainManager
from .upload_manager import UploadManager, UploadResult

logger = logging.getLogger(__name__)

WsBroadcast = Callable[[dict[str, Any]], None]


class FirmwareEventType:
    BUILD_STARTED = "BUILD_STARTED"
    BUILD_PROGRESS = "BUILD_PROGRESS"
    BUILD_COMPLETED = "BUILD_COMPLETED"
    BUILD_FAILED = "BUILD_FAILED"
    UPLOAD_STARTED = "UPLOAD_STARTED"
    UPLOAD_PROGRESS = "UPLOAD_PROGRESS"
    UPLOAD_COMPLETED = "UPLOAD_COMPLETED"
    SERIAL_DATA = "SERIAL_DATA"
    GPIO_DEBUG = "GPIO_DEBUG"


class FirmwareStudioService:
    """DI façade for the Embedded Development Studio."""

    def __init__(
        self,
        data_dir: Path | str,
        *,
        event_bus: Optional[EventBus] = None,
        hybrid_service: Any = None,
        wire_manager: Any = None,
        workspace_sync: Any = None,
        force_dry_run: bool = False,
        toolchain_manager: Optional[ToolchainManager] = None,
    ) -> None:
        self.data_dir = Path(data_dir)
        self.event_bus = event_bus
        self.repo = FirmwareProjectRepository(self.data_dir)
        self.toolchains = toolchain_manager or ToolchainManager()
        self.cache = BuildCache(self.data_dir)
        self.compiler = CompilerAdapter(self.toolchains, force_dry_run=force_dry_run)
        self.uploader = UploadManager(
            self.toolchains, force_dry_run=force_dry_run, hybrid_service=hybrid_service
        )
        self.console = SerialConsole()
        self.monitor = FirmwareMonitor(
            self.console,
            wire_manager=wire_manager,
            workspace_sync=workspace_sync,
        )
        self._lock = threading.RLock()
        self._builds: dict[str, dict[str, Any]] = {}
        self._uploads: dict[str, dict[str, Any]] = {}
        self._logs: list[dict[str, Any]] = []
        self._ws: list[WsBroadcast] = []

        self.console.subscribe(self._on_serial_line)
        self.monitor.subscribe_ws(self._on_monitor_event)

    # ---- WS ---------------------------------------------------------------

    def subscribe_ws(self, cb: WsBroadcast) -> None:
        self._ws.append(cb)

    def unsubscribe_ws(self, cb: WsBroadcast) -> None:
        try:
            self._ws.remove(cb)
        except ValueError:
            pass

    def _broadcast(self, event_type: str, payload: dict[str, Any]) -> None:
        message = {
            "type": event_type,
            "event": event_type,
            "payload": payload,
            "timestamp_ms": int(time.time() * 1000),
        }
        self._logs.append(message)
        if len(self._logs) > 1000:
            self._logs = self._logs[-1000:]
        for cb in list(self._ws):
            try:
                cb(message)
            except Exception:  # noqa: BLE001
                logger.exception("firmware WS fan-out failed")
        if self.event_bus is not None:
            try:
                self.event_bus.publish(
                    Event.create(event_type=event_type, source="firmware-studio", payload=payload)
                )
            except Exception:  # noqa: BLE001
                logger.exception("firmware EventBus publish failed")

    def _on_serial_line(self, line: Any) -> None:
        self._broadcast(FirmwareEventType.SERIAL_DATA, line.to_dict())

    def _on_monitor_event(self, message: dict[str, Any]) -> None:
        # Already shaped; rebroadcast
        for cb in list(self._ws):
            try:
                cb(message)
            except Exception:  # noqa: BLE001
                pass
        if self.event_bus is not None:
            try:
                self.event_bus.publish(
                    Event.create(
                        event_type=str(message.get("type") or FirmwareEventType.GPIO_DEBUG),
                        source="firmware-studio",
                        payload=message.get("payload") or {},
                    )
                )
            except Exception:  # noqa: BLE001
                pass

    # ---- Projects ---------------------------------------------------------

    def list_projects(self) -> dict[str, Any]:
        items = [p.to_dict() for p in self.repo.list_projects()]
        return {"projects": items, "count": len(items)}

    def get_project(self, project_id: str) -> dict[str, Any]:
        p = self.repo.get(project_id)
        if p is None:
            raise KeyError(f"project not found: {project_id}")
        data = p.to_dict()
        data["tree"] = self.project_tree(p)
        return data

    def create_project(self, body: dict[str, Any]) -> dict[str, Any]:
        name = str(body.get("name") or "Untitled Firmware")
        project_type = str(body.get("project_type") or ProjectType.ARDUINO_SKETCH.value)
        board_type = str(body.get("board_type") or "esp32")
        template_id = str(body.get("template_id") or body.get("template") or "blink")
        language = str(body.get("language") or default_language_for(project_type))
        files = generate_template(template_id, board_type=board_type, project_type=project_type)
        project = self.repo.create(
            name=name,
            project_type=project_type,
            language=language,
            board_type=board_type,
            files=files,
            template_id=template_id,
        )
        return project.to_dict()

    def save_file(self, project_id: str, path: str, content: str) -> dict[str, Any]:
        return self.repo.update_file(project_id, path, content).to_dict()

    def project_tree(self, project: FirmwareProject) -> dict[str, Any]:
        groups: dict[str, list[str]] = {
            "Source": [],
            "Include": [],
            "Libraries": [],
            "Assets": [],
            "Configuration": [],
            "Firmware": [],
            "Build output": [],
        }
        for f in project.files:
            p = f.path.replace("\\", "/")
            if p.endswith((".ino", ".cpp", ".c", ".py", ".S")):
                groups["Source"].append(p)
            elif p.endswith((".h", ".hpp")):
                groups["Include"].append(p)
            elif "lib" in p.lower():
                groups["Libraries"].append(p)
            elif p.endswith((".json", ".ini", ".cmake", "CMakeLists.txt")):
                groups["Configuration"].append(p)
            elif p.endswith((".bin", ".elf", ".hex")):
                groups["Firmware"].append(p)
            elif p.endswith((".md", ".txt", ".png")):
                groups["Assets"].append(p)
            else:
                groups["Source"].append(p)
        root = Path(project.root_path)
        build_dir = root / ".hhip_build"
        if build_dir.exists():
            for b in build_dir.iterdir():
                groups["Build output"].append(f".hhip_build/{b.name}")
        return {k: v for k, v in groups.items() if v}

    def list_templates(self) -> dict[str, Any]:
        items = list_templates()
        return {"templates": items, "count": len(items)}

    # ---- Toolchains -------------------------------------------------------

    def list_toolchains(self) -> dict[str, Any]:
        tools = [t.to_dict() for t in self.toolchains.detect_all()]
        return {
            "toolchains": tools,
            "count": len(tools),
            "missing": self.toolchains.guided_setup(),
            "installed_count": sum(1 for t in tools if t["installed"]),
        }

    # ---- Build / Upload ---------------------------------------------------

    def build(self, project_id: str, *, use_cache: bool = True) -> dict[str, Any]:
        project = self.repo.get(project_id)
        if project is None:
            raise KeyError(f"project not found: {project_id}")

        file_dicts = [f.to_dict() for f in project.files]
        cache_key = self.cache.content_hash(file_dicts, project.board_type)
        if use_cache:
            cached = self.cache.get(cache_key)
            if cached and cached.get("success"):
                cached = {**cached, "from_cache": True}
                self._builds[cached["build_id"]] = cached
                self._broadcast(FirmwareEventType.BUILD_COMPLETED, cached)
                return cached

        self._broadcast(
            FirmwareEventType.BUILD_STARTED,
            {"project_id": project_id, "cache_key": cache_key},
        )

        def on_progress(stage: str, payload: dict[str, Any]) -> None:
            if stage in ("started",):
                return
            if stage == "failed":
                self._broadcast(FirmwareEventType.BUILD_FAILED, payload)
            elif stage == "completed":
                pass
            else:
                self._broadcast(FirmwareEventType.BUILD_PROGRESS, {"stage": stage, **payload})

        result = self.compiler.build(project, on_progress=on_progress)
        data = result.to_dict()
        data["from_cache"] = False
        project.last_build_id = result.build_id
        self.repo.save(project)
        self._builds[result.build_id] = data
        if result.success:
            self.cache.put(cache_key, data)
            self._broadcast(FirmwareEventType.BUILD_COMPLETED, data)
            # Simulate serial GPIO from blink templates for live sync demo
            if any("GPIO HIGH" in f.content for f in project.files):
                self.monitor.set_device(project.metadata.get("device_id") or project.project_id)
                self.monitor.ingest("GPIO HIGH")
        else:
            self._broadcast(FirmwareEventType.BUILD_FAILED, data)
        return data

    def upload(
        self,
        project_id: str,
        *,
        port: str = "",
        build_id: str = "",
    ) -> dict[str, Any]:
        project = self.repo.get(project_id)
        if project is None:
            raise KeyError(f"project not found: {project_id}")

        build_data = self._builds.get(build_id) if build_id else None
        if build_data is None and project.last_build_id:
            build_data = self._builds.get(project.last_build_id)
        if build_data is None:
            build_data = self.build(project_id)

        build = BuildResult(
            build_id=str(build_data.get("build_id") or ""),
            project_id=project_id,
            success=bool(build_data.get("success")),
            binary_path=str(build_data.get("binary_path") or ""),
            logs=list(build_data.get("logs") or []),
        )

        self._broadcast(
            FirmwareEventType.UPLOAD_STARTED,
            {"project_id": project_id, "port": port},
        )

        def on_progress(stage: str, payload: dict[str, Any]) -> None:
            if stage == "progress":
                self._broadcast(FirmwareEventType.UPLOAD_PROGRESS, payload)
            elif stage == "started":
                self._broadcast(FirmwareEventType.UPLOAD_STARTED, payload)

        result: UploadResult = self.uploader.upload(
            project, build, port=port, on_progress=on_progress
        )
        data = result.to_dict()
        self._uploads[result.upload_id] = data
        self._broadcast(FirmwareEventType.UPLOAD_COMPLETED, data)
        if result.success:
            self.console.append(f"[HHIP] Upload {result.upload_id} OK", direction="rx")
            self.monitor.set_device(project.metadata.get("device_id") or project.project_id)
            self.monitor.ingest("GPIO HIGH")
        return data

    def logs(self, limit: int = 200) -> dict[str, Any]:
        return {"logs": self._logs[-limit:], "count": min(limit, len(self._logs))}

    def serial(
        self,
        *,
        limit: int = 500,
        query: str = "",
        action: str = "",
        line: str = "",
        port: str = "",
        baud: int = 0,
    ) -> dict[str, Any]:
        if port or baud:
            self.console.configure(port=port, baud=baud or 115200)
        if action == "pause":
            self.console.pause()
        elif action == "resume":
            self.console.resume()
        elif action == "clear":
            self.console.clear()
        elif action == "write" and line:
            self.console.write(line)
        return {
            **self.console.status(),
            "lines": self.console.lines(limit=limit, query=query),
            "export": self.console.export_text(query=query) if action == "export" else None,
            "gpio": self.monitor.gpio_snapshot(),
        }
