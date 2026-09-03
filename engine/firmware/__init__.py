"""HHIP Embedded Development Studio — firmware projects, build, upload, serial."""

from __future__ import annotations

from .build_cache import BuildCache
from .compiler_adapter import BuildResult, CompilerAdapter
from .firmware_monitor import FirmwareMonitor
from .firmware_project import (
    BOARD_PROFILES,
    FirmwareFile,
    FirmwareProject,
    FirmwareProjectRepository,
    Language,
    ProjectType,
)
from .firmware_studio import FirmwareEventType, FirmwareStudioService
from .project_templates import generate_template, list_templates
from .serial_console import SerialConsole, SerialLine
from .toolchain_manager import ToolchainInfo, ToolchainManager
from .upload_manager import UploadManager, UploadResult

__all__ = [
    "BOARD_PROFILES",
    "BuildCache",
    "BuildResult",
    "CompilerAdapter",
    "FirmwareConsole",
    "FirmwareEventType",
    "FirmwareFile",
    "FirmwareMonitor",
    "FirmwareProject",
    "FirmwareProjectRepository",
    "FirmwareStudioService",
    "Language",
    "ProjectType",
    "SerialConsole",
    "SerialLine",
    "ToolchainInfo",
    "ToolchainManager",
    "UploadManager",
    "UploadResult",
    "generate_template",
    "list_templates",
]

# alias
FirmwareConsole = SerialConsole
