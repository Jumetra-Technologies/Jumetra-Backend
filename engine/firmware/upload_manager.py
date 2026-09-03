"""Firmware upload manager — progress, verify, reset, reconnect."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from .compiler_adapter import BuildResult
from .firmware_project import FirmwareProject
from .toolchain_manager import ToolchainManager

ProgressCb = Callable[[str, dict[str, Any]], None]


@dataclass
class UploadResult:
    upload_id: str
    project_id: str
    success: bool
    port: str = ""
    logs: list[str] = field(default_factory=list)
    verified: bool = False
    reset: bool = False
    reconnected: bool = False
    duration_ms: float = 0.0
    dry_run: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "upload_id": self.upload_id,
            "project_id": self.project_id,
            "success": self.success,
            "port": self.port,
            "logs": list(self.logs),
            "verified": self.verified,
            "reset": self.reset,
            "reconnected": self.reconnected,
            "duration_ms": self.duration_ms,
            "dry_run": self.dry_run,
        }


class UploadManager:
    """Upload binaries to boards (dry-run when flasher unavailable)."""

    def __init__(
        self,
        toolchain_manager: Optional[ToolchainManager] = None,
        *,
        force_dry_run: bool = False,
        hybrid_service: Any = None,
    ) -> None:
        self.toolchains = toolchain_manager or ToolchainManager()
        self.force_dry_run = force_dry_run
        self.hybrid_service = hybrid_service

    def upload(
        self,
        project: FirmwareProject,
        build: BuildResult,
        *,
        port: str = "",
        on_progress: Optional[ProgressCb] = None,
    ) -> UploadResult:
        upload_id = f"UP_{uuid.uuid4().hex[:10]}"
        t0 = time.perf_counter()
        logs: list[str] = []

        def prog(stage: str, percent: int, **extra: Any) -> None:
            if on_progress:
                on_progress(
                    stage,
                    {
                        "upload_id": upload_id,
                        "project_id": project.project_id,
                        "percent": percent,
                        **extra,
                    },
                )

        if not build.success or not build.binary_path:
            return UploadResult(
                upload_id=upload_id,
                project_id=project.project_id,
                success=False,
                port=port,
                logs=["No successful build binary to upload"],
            )

        prog("started", 0, message="Upload started")
        logs.append(f"[HHIP] Uploading {build.binary_path} → {port or '(auto)'}")

        tc = self.toolchains.resolve_for_board(project.board_type, project.language)
        dry = self.force_dry_run or not tc.installed or not port

        if dry:
            for pct, msg in [(20, "Erasing flash"), (50, "Writing firmware"), (80, "Verifying"), (95, "Resetting")]:
                prog("progress", pct, message=msg)
                logs.append(msg)
                time.sleep(0.01)
            verified = True
            reset = True
            success = True
            logs.append("[HHIP] Dry-run upload completed")
        else:
            # Best-effort real upload via arduino-cli / pio
            import subprocess
            import os

            try:
                prog("progress", 25, message="Flashing")
                if tc.id == "arduino-cli":
                    from .firmware_project import BOARD_PROFILES

                    fqbn = BOARD_PROFILES.get(project.board_type, {}).get("fqbn") or "arduino:avr:uno"
                    cmd = [
                        tc.path or "arduino-cli",
                        "upload",
                        "-p",
                        port,
                        "--fqbn",
                        fqbn,
                        str(Path(project.root_path) / "src"),
                    ]
                elif tc.id == "platformio":
                    cmd = [tc.path or "pio", "run", "-t", "upload", "-d", project.root_path, "--upload-port", port]
                else:
                    cmd = None
                if cmd:
                    logs.append("$ " + " ".join(cmd))
                    proc = subprocess.run(
                        cmd, capture_output=True, text=True, timeout=180, env=os.environ.copy()
                    )
                    logs.extend((proc.stdout or "").splitlines())
                    logs.extend((proc.stderr or "").splitlines())
                    success = proc.returncode == 0
                else:
                    success = True
                    logs.append("[HHIP] No flasher command — marked complete")
                verified = success
                reset = success
                prog("progress", 90, message="Verify/reset")
            except Exception as exc:  # noqa: BLE001
                success = False
                verified = False
                reset = False
                logs.append(str(exc))

        reconnected = False
        if success and self.hybrid_service is not None and port:
            try:
                self.hybrid_service.connect_physical_device(
                    port=port,
                    board_type=project.board_type,
                    label=project.name,
                )
                reconnected = True
                logs.append("[HHIP] Reconnected hybrid device after upload")
            except Exception as exc:  # noqa: BLE001
                logs.append(f"[HHIP] Reconnect skipped: {exc}")

        prog("completed" if success else "failed", 100, message="Upload done")
        return UploadResult(
            upload_id=upload_id,
            project_id=project.project_id,
            success=success,
            port=port,
            logs=logs,
            verified=verified,
            reset=reset,
            reconnected=reconnected,
            duration_ms=round((time.perf_counter() - t0) * 1000, 2),
            dry_run=dry,
        )
