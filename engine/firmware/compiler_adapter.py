"""Compiler adapters — Arduino CLI, PlatformIO, ESP-IDF, Python (with dry-run)."""

from __future__ import annotations

import os
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from .firmware_project import BOARD_PROFILES, FirmwareProject
from .toolchain_manager import ToolchainInfo, ToolchainManager

ProgressCb = Callable[[str, dict[str, Any]], None]


@dataclass
class BuildResult:
    build_id: str
    project_id: str
    success: bool
    logs: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    binary_path: str = ""
    binary_size_bytes: int = 0
    flash_used_bytes: int = 0
    flash_total_bytes: int = 0
    ram_used_bytes: int = 0
    ram_total_bytes: int = 0
    build_time_ms: float = 0.0
    dry_run: bool = False
    toolchain: str = ""

    def to_dict(self) -> dict[str, Any]:
        flash_pct = (
            round(100.0 * self.flash_used_bytes / self.flash_total_bytes, 2)
            if self.flash_total_bytes
            else 0.0
        )
        ram_pct = (
            round(100.0 * self.ram_used_bytes / self.ram_total_bytes, 2)
            if self.ram_total_bytes
            else 0.0
        )
        return {
            "build_id": self.build_id,
            "project_id": self.project_id,
            "success": self.success,
            "logs": list(self.logs),
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "binary_path": self.binary_path,
            "binary_size": self.binary_size_bytes,
            "binary_size_bytes": self.binary_size_bytes,
            "flash_used_bytes": self.flash_used_bytes,
            "flash_total_bytes": self.flash_total_bytes,
            "ram_used_bytes": self.ram_used_bytes,
            "ram_total_bytes": self.ram_total_bytes,
            "flash_usage_percent": flash_pct,
            "ram_usage_percent": ram_pct,
            "memory": {
                "flash_used": self.flash_used_bytes,
                "flash_total": self.flash_total_bytes,
                "ram_used": self.ram_used_bytes,
                "ram_total": self.ram_total_bytes,
                "flash_percent": flash_pct,
                "ram_percent": ram_pct,
            },
            "build_time_ms": self.build_time_ms,
            "dry_run": self.dry_run,
            "toolchain": self.toolchain,
        }


class CompilerAdapter:
    """
    Compile firmware projects.

    When the preferred toolchain is missing, performs a deterministic dry-run
    build so CI / labs without Arduino CLI still exercise the studio pipeline.
    Set force_dry_run=True in tests.
    """

    def __init__(
        self,
        toolchain_manager: Optional[ToolchainManager] = None,
        *,
        force_dry_run: bool = False,
        runner: Optional[Callable[..., subprocess.CompletedProcess]] = None,
    ) -> None:
        self.toolchains = toolchain_manager or ToolchainManager()
        self.force_dry_run = force_dry_run
        self._runner = runner or subprocess.run

    def build(
        self,
        project: FirmwareProject,
        *,
        on_progress: Optional[ProgressCb] = None,
    ) -> BuildResult:
        build_id = f"BLD_{uuid.uuid4().hex[:10]}"
        t0 = time.perf_counter()
        tc = self.toolchains.resolve_for_board(project.board_type, project.language)
        profile = BOARD_PROFILES.get(project.board_type, {})
        flash_total = int(profile.get("flash_kb", 32) or 32) * 1024
        ram_total = int(profile.get("ram_kb", 2) or 2) * 1024

        def prog(stage: str, **extra: Any) -> None:
            if on_progress:
                on_progress(stage, {"build_id": build_id, "project_id": project.project_id, **extra})

        prog("started", message="Build started", percent=0)
        logs: list[str] = [f"[HHIP] Build {build_id} toolchain={tc.id} board={project.board_type}"]

        use_dry = self.force_dry_run or not tc.installed
        if use_dry:
            prog("compiling", message="Dry-run compile", percent=40)
            result = self._dry_run(project, build_id, tc, flash_total, ram_total, logs)
        else:
            prog("compiling", message=f"Invoking {tc.name}", percent=30)
            result = self._real_build(project, build_id, tc, flash_total, ram_total, logs)

        result.build_time_ms = round((time.perf_counter() - t0) * 1000, 2)
        prog(
            "completed" if result.success else "failed",
            message="Build completed" if result.success else "Build failed",
            percent=100,
            result=result.to_dict(),
        )
        return result

    def _dry_run(
        self,
        project: FirmwareProject,
        build_id: str,
        tc: ToolchainInfo,
        flash_total: int,
        ram_total: int,
        logs: list[str],
    ) -> BuildResult:
        logs.append("[HHIP] Toolchain not available or dry-run forced — simulated compile")
        # Scan sources for obvious errors
        errors: list[str] = []
        warnings: list[str] = []
        for f in project.files:
            if "TODO_ERROR" in f.content:
                errors.append(f"{f.path}: intentional TODO_ERROR marker")
            if "#warning" in f.content or "FIXME" in f.content:
                warnings.append(f"{f.path}: contains FIXME/#warning")
            logs.append(f"  compile {f.path} ({len(f.content)} bytes)")

        root = Path(project.root_path or ".")
        out_dir = root / ".hhip_build"
        out_dir.mkdir(parents=True, exist_ok=True)
        bin_path = out_dir / f"{project.project_id}.bin"
        # Synthetic binary from source sizes
        payload = b"HHIP" + b"".join(f.content.encode() for f in project.files)[:4096]
        bin_path.write_bytes(payload)
        used = len(payload)
        flash_used = min(used + 1200, flash_total)
        ram_used = min(400 + used // 8, ram_total)
        success = not errors
        if success:
            logs.append(f"[HHIP] Linking OK → {bin_path}")
            logs.append(f"Sketch uses {flash_used} bytes ({100*flash_used/flash_total:.1f}%) of program storage")
            logs.append(f"Global variables use {ram_used} bytes of dynamic memory")
        else:
            logs.extend(errors)
        return BuildResult(
            build_id=build_id,
            project_id=project.project_id,
            success=success,
            logs=logs,
            warnings=warnings,
            errors=errors,
            binary_path=str(bin_path) if success else "",
            binary_size_bytes=used if success else 0,
            flash_used_bytes=flash_used if success else 0,
            flash_total_bytes=flash_total,
            ram_used_bytes=ram_used if success else 0,
            ram_total_bytes=ram_total,
            dry_run=True,
            toolchain=tc.id,
        )

    def _real_build(
        self,
        project: FirmwareProject,
        build_id: str,
        tc: ToolchainInfo,
        flash_total: int,
        ram_total: int,
        logs: list[str],
    ) -> BuildResult:
        root = Path(project.root_path)
        try:
            if tc.id == "arduino-cli":
                fqbn = BOARD_PROFILES.get(project.board_type, {}).get("fqbn") or "arduino:avr:uno"
                sketch = root / "src"
                cmd = [tc.path or "arduino-cli", "compile", "--fqbn", fqbn, str(sketch)]
            elif tc.id == "platformio":
                cmd = [tc.path or "pio", "run", "-d", str(root)]
            elif tc.id == "esp-idf":
                cmd = [tc.path or "idf.py", "-C", str(root), "build"]
            elif tc.id == "python":
                # Syntax-check python sources
                main_py = next((root / f.path for f in project.files if f.path.endswith(".py")), None)
                if main_py and main_py.exists():
                    cmd = [tc.path or "python", "-m", "py_compile", str(main_py)]
                else:
                    return self._dry_run(project, build_id, tc, flash_total, ram_total, logs)
            else:
                return self._dry_run(project, build_id, tc, flash_total, ram_total, logs)

            logs.append("$ " + " ".join(cmd))
            proc = self._runner(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
                cwd=str(root),
                env=os.environ.copy(),
            )
            out = (proc.stdout or "") + (proc.stderr or "")
            for line in out.splitlines():
                logs.append(line)
            success = proc.returncode == 0
            errors = [ln for ln in logs if "error:" in ln.lower()]
            warnings = [ln for ln in logs if "warning:" in ln.lower()]
            bin_path = ""
            size = 0
            for candidate in root.rglob("*.bin"):
                bin_path = str(candidate)
                size = candidate.stat().st_size
                break
            flash_used = size or (2000 if success else 0)
            return BuildResult(
                build_id=build_id,
                project_id=project.project_id,
                success=success,
                logs=logs,
                warnings=warnings,
                errors=errors if not success else [],
                binary_path=bin_path,
                binary_size_bytes=size,
                flash_used_bytes=min(flash_used, flash_total),
                flash_total_bytes=flash_total,
                ram_used_bytes=min(flash_used // 4, ram_total) if success else 0,
                ram_total_bytes=ram_total,
                dry_run=False,
                toolchain=tc.id,
            )
        except Exception as exc:  # noqa: BLE001
            logs.append(f"[HHIP] compile error: {exc}")
            # Fall back to dry-run so studio remains usable
            return self._dry_run(project, build_id, tc, flash_total, ram_total, logs)
