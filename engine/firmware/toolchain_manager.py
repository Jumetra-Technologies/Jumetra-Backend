"""Toolchain detection and guided setup hints."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

WhichFn = Callable[[str], Optional[str]]


@dataclass
class ToolchainInfo:
    id: str
    name: str
    command: str
    installed: bool
    path: str = ""
    version: str = ""
    setup_url: str = ""
    setup_hint: str = ""
    languages: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "command": self.command,
            "installed": self.installed,
            "path": self.path,
            "version": self.version,
            "setup_url": self.setup_url,
            "setup_hint": self.setup_hint,
            "languages": list(self.languages),
            "status": "installed" if self.installed else "missing",
        }


TOOLCHAIN_SPECS: list[dict[str, Any]] = [
    {
        "id": "arduino-cli",
        "name": "Arduino CLI",
        "command": "arduino-cli",
        "setup_url": "https://arduino.github.io/arduino-cli/",
        "setup_hint": "Install Arduino CLI and ensure it is on PATH. Then: arduino-cli core install arduino:avr",
        "languages": ["arduino-cpp"],
    },
    {
        "id": "platformio",
        "name": "PlatformIO",
        "command": "pio",
        "setup_url": "https://platformio.org/install/cli",
        "setup_hint": "pip install platformio  (or install PlatformIO Core)",
        "languages": ["platformio", "arduino-cpp", "esp-idf"],
    },
    {
        "id": "esp-idf",
        "name": "ESP-IDF",
        "command": "idf.py",
        "setup_url": "https://docs.espressif.com/projects/esp-idf/",
        "setup_hint": "Install ESP-IDF and run export.bat / . ./export.sh",
        "languages": ["esp-idf"],
    },
    {
        "id": "python",
        "name": "Python",
        "command": "python",
        "setup_url": "https://www.python.org/downloads/",
        "setup_hint": "Install Python 3.10+ for MicroPython tooling and Raspberry Pi scripts",
        "languages": ["micropython", "circuitpython", "raspberry-pi-python"],
    },
    {
        "id": "openocd",
        "name": "OpenOCD",
        "command": "openocd",
        "setup_url": "https://openocd.org/",
        "setup_hint": "Install OpenOCD for SWD/JTAG debug upload (STM32, nRF52)",
        "languages": ["stm32"],
    },
    {
        "id": "arm-none-eabi-gcc",
        "name": "GCC ARM",
        "command": "arm-none-eabi-gcc",
        "setup_url": "https://developer.arm.com/downloads/-/gnu-rm",
        "setup_hint": "Install GNU Arm Embedded Toolchain",
        "languages": ["stm32", "zephyr", "mbed"],
    },
]


class ToolchainManager:
    """Detect installed embedded toolchains (injectable which() for tests)."""

    def __init__(self, *, which: Optional[WhichFn] = None) -> None:
        self._which = which or shutil.which

    def detect_all(self) -> list[ToolchainInfo]:
        results: list[ToolchainInfo] = []
        for spec in TOOLCHAIN_SPECS:
            path = self._which(spec["command"]) or ""
            # Windows python launcher fallback
            if not path and spec["command"] == "python":
                path = self._which("python3") or self._which("py") or ""
            if not path and spec["command"] == "pio":
                path = self._which("platformio") or ""
            info = ToolchainInfo(
                id=spec["id"],
                name=spec["name"],
                command=spec["command"],
                installed=bool(path),
                path=path or "",
                setup_url=spec["setup_url"],
                setup_hint=spec["setup_hint"],
                languages=list(spec["languages"]),
            )
            if path:
                info.version = self._probe_version(spec["command"], path)
            results.append(info)
        return results

    def get(self, toolchain_id: str) -> Optional[ToolchainInfo]:
        for t in self.detect_all():
            if t.id == toolchain_id:
                return t
        return None

    def resolve_for_board(self, board_type: str, language: str = "") -> ToolchainInfo:
        from .firmware_project import BOARD_PROFILES

        preferred = BOARD_PROFILES.get(board_type, {}).get("toolchain", "arduino-cli")
        if language in ("micropython", "circuitpython", "raspberry-pi-python"):
            preferred = "python"
        if language == "esp-idf":
            preferred = "esp-idf"
        if language == "platformio":
            preferred = "platformio"
        tools = {t.id: t for t in self.detect_all()}
        if preferred in tools:
            return tools[preferred]
        # fallback first installed
        for t in tools.values():
            if t.installed:
                return t
        return tools.get(preferred) or next(iter(tools.values()))

    def guided_setup(self) -> list[dict[str, Any]]:
        return [
            {
                "id": t.id,
                "name": t.name,
                "installed": t.installed,
                "setup_url": t.setup_url,
                "setup_hint": t.setup_hint,
            }
            for t in self.detect_all()
            if not t.installed
        ]

    @staticmethod
    def _probe_version(command: str, path: str) -> str:
        import subprocess

        try:
            args = [path, "--version"]
            if command == "arduino-cli":
                args = [path, "version"]
            proc = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=5,
                env=os.environ.copy(),
            )
            out = (proc.stdout or proc.stderr or "").strip().splitlines()
            return out[0][:120] if out else "unknown"
        except Exception:  # noqa: BLE001
            return "unknown"
