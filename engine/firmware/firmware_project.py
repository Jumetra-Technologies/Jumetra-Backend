"""Firmware project model and repository."""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class ProjectType(str, Enum):
    ARDUINO_SKETCH = "arduino-sketch"
    ESP_IDF = "esp-idf"
    PLATFORMIO = "platformio"
    MICROPYTHON = "micropython"
    CIRCUITPYTHON = "circuitpython"
    STM32 = "stm32"
    RASPBERRY_PI = "raspberry-pi"


class Language(str, Enum):
    ARDUINO_CPP = "arduino-cpp"
    ESP_IDF = "esp-idf"
    PLATFORMIO = "platformio"
    MICROPYTHON = "micropython"
    CIRCUITPYTHON = "circuitpython"
    RASPBERRY_PI_PYTHON = "raspberry-pi-python"
    ZEPHYR = "zephyr"  # future
    MBED = "mbed"  # future


BOARD_PROFILES: dict[str, dict[str, Any]] = {
    "arduino-uno": {"fqbn": "arduino:avr:uno", "toolchain": "arduino-cli", "flash_kb": 32, "ram_kb": 2},
    "arduino-mega": {"fqbn": "arduino:avr:mega", "toolchain": "arduino-cli", "flash_kb": 256, "ram_kb": 8},
    "esp32": {"fqbn": "esp32:esp32:esp32", "toolchain": "arduino-cli", "flash_kb": 4096, "ram_kb": 520},
    "esp8266": {"fqbn": "esp8266:esp8266:nodemcuv2", "toolchain": "arduino-cli", "flash_kb": 4096, "ram_kb": 80},
    "stm32": {"fqbn": "STMicroelectronics:stm32:GenF1", "toolchain": "platformio", "flash_kb": 64, "ram_kb": 20},
    "raspberry-pi-pico": {"fqbn": "rp2040:rp2040:rpipico", "toolchain": "arduino-cli", "flash_kb": 2048, "ram_kb": 264},
    "raspberry-pi-4": {"fqbn": "", "toolchain": "python", "flash_kb": 0, "ram_kb": 0},
    "teensy": {"fqbn": "teensy:avr:teensy41", "toolchain": "arduino-cli", "flash_kb": 7936, "ram_kb": 1024},
    "nrf52": {"fqbn": "nordic:nrf52:nrf52840", "toolchain": "platformio", "flash_kb": 1024, "ram_kb": 256},
    "microbit": {"fqbn": "arduino:mbed_nano:nanoble", "toolchain": "arduino-cli", "flash_kb": 512, "ram_kb": 128},
}


@dataclass
class FirmwareFile:
    path: str  # relative to project root
    content: str = ""
    language: str = "cpp"

    def to_dict(self) -> dict[str, Any]:
        return {"path": self.path, "content": self.content, "language": self.language}


@dataclass
class FirmwareProject:
    project_id: str
    name: str
    project_type: str
    language: str
    board_type: str
    root_path: str = ""
    template_id: str = ""
    files: list[FirmwareFile] = field(default_factory=list)
    created_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    updated_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    last_build_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "name": self.name,
            "project_type": self.project_type,
            "language": self.language,
            "board_type": self.board_type,
            "root_path": self.root_path,
            "template_id": self.template_id,
            "files": [f.to_dict() for f in self.files],
            "created_at_ms": self.created_at_ms,
            "updated_at_ms": self.updated_at_ms,
            "last_build_id": self.last_build_id,
            "metadata": dict(self.metadata),
            "board_profile": BOARD_PROFILES.get(self.board_type, {}),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FirmwareProject":
        files = [
            FirmwareFile(
                path=str(f.get("path") or ""),
                content=str(f.get("content") or ""),
                language=str(f.get("language") or "cpp"),
            )
            for f in (data.get("files") or [])
            if isinstance(f, dict)
        ]
        return cls(
            project_id=str(data.get("project_id") or ""),
            name=str(data.get("name") or "Untitled"),
            project_type=str(data.get("project_type") or ProjectType.ARDUINO_SKETCH.value),
            language=str(data.get("language") or Language.ARDUINO_CPP.value),
            board_type=str(data.get("board_type") or "esp32"),
            root_path=str(data.get("root_path") or ""),
            template_id=str(data.get("template_id") or ""),
            files=files,
            created_at_ms=int(data.get("created_at_ms") or time.time() * 1000),
            updated_at_ms=int(data.get("updated_at_ms") or time.time() * 1000),
            last_build_id=str(data.get("last_build_id") or ""),
            metadata=dict(data.get("metadata") or {}),
        )


class FirmwareProjectRepository:
    """File-backed repository under data/firmware/projects."""

    def __init__(self, data_dir: Path | str) -> None:
        self.base = Path(data_dir) / "firmware" / "projects"
        self.base.mkdir(parents=True, exist_ok=True)

    def list_projects(self) -> list[FirmwareProject]:
        projects: list[FirmwareProject] = []
        for meta in sorted(self.base.glob("*/project.json")):
            try:
                data = json.loads(meta.read_text(encoding="utf-8"))
                projects.append(FirmwareProject.from_dict(data))
            except (OSError, json.JSONDecodeError):
                continue
        return projects

    def get(self, project_id: str) -> Optional[FirmwareProject]:
        path = self.base / project_id / "project.json"
        if not path.exists():
            return None
        return FirmwareProject.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def save(self, project: FirmwareProject) -> FirmwareProject:
        project.updated_at_ms = int(time.time() * 1000)
        root = self.base / project.project_id
        root.mkdir(parents=True, exist_ok=True)
        project.root_path = str(root)
        (root / "project.json").write_text(
            json.dumps(project.to_dict(), indent=2), encoding="utf-8"
        )
        for f in project.files:
            fp = root / f.path
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(f.content, encoding="utf-8")
        return project

    def create(
        self,
        *,
        name: str,
        project_type: str,
        language: str,
        board_type: str,
        files: list[FirmwareFile],
        template_id: str = "",
        project_id: str = "",
    ) -> FirmwareProject:
        pid = project_id or f"FW_{uuid.uuid4().hex[:10]}"
        project = FirmwareProject(
            project_id=pid,
            name=name,
            project_type=project_type,
            language=language,
            board_type=board_type,
            template_id=template_id,
            files=files,
        )
        return self.save(project)

    def update_file(self, project_id: str, path: str, content: str) -> FirmwareProject:
        project = self.get(project_id)
        if project is None:
            raise KeyError(f"project not found: {project_id}")
        found = False
        for f in project.files:
            if f.path == path:
                f.content = content
                found = True
                break
        if not found:
            lang = "python" if path.endswith(".py") else "cpp" if path.endswith((".cpp", ".ino", ".c", ".h")) else "text"
            project.files.append(FirmwareFile(path=path, content=content, language=lang))
        return self.save(project)

    def delete(self, project_id: str) -> bool:
        root = self.base / project_id
        if not root.exists():
            return False
        import shutil

        shutil.rmtree(root)
        return True
