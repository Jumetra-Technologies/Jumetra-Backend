"""Firmware file paths stay inside their project (S1, 12 Nov 2026)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from engine.firmware.firmware_project import (
    FirmwareFile,
    FirmwareProjectRepository,
    safe_project_id,
    safe_relative_path,
)

BAD_PATHS = [
    "../escape.txt",
    "../../api/main.py",
    "src/../../escape.ino",
    "/etc/passwd",
    "src//main.ino",
    ".hhip_build/x.bin",
    "src/.hidden",
    "a/b/c/d/e.ino",
    "src\\..\\x.ino",
    "",
    "x" * 201,
]


@pytest.mark.parametrize("path", BAD_PATHS)
def test_unsafe_paths_are_refused(path: str) -> None:
    with pytest.raises(ValueError):
        safe_relative_path(path)


@pytest.mark.parametrize("path", ["src/main.ino", "README.md", "main/main.c", "platformio.ini", "lib/my_lib/my_lib.h"])
def test_template_paths_are_allowed(path: str) -> None:
    assert safe_relative_path(path) == path


@pytest.mark.parametrize("pid", ["..", "../x", "a/b", "", "x" * 65])
def test_odd_project_ids_are_refused(pid: str) -> None:
    with pytest.raises(ValueError):
        safe_project_id(pid)


def test_the_repository_never_writes_outside_the_project(tmp_path: Path) -> None:
    repo = FirmwareProjectRepository(tmp_path)
    project = repo.create(name="p", project_type="arduino-sketch", language="arduino-cpp", board_type="arduino-uno", files=[FirmwareFile(path="src/main.ino", content="void setup(){} void loop(){}")])
    with pytest.raises(ValueError):
        repo.update_file(project.project_id, "../../pwned.txt", "x")
    assert not (tmp_path / "pwned.txt").exists()
    assert not list(tmp_path.rglob("pwned.txt"))
    assert repo.get("../..") is None


def test_the_repository_refuses_a_link_out_of_the_project(tmp_path: Path) -> None:
    repo = FirmwareProjectRepository(tmp_path)
    project = repo.create(name="p", project_type="arduino-sketch", language="arduino-cpp", board_type="arduino-uno", files=[FirmwareFile(path="src/main.ino", content="")])
    outside = tmp_path / "outside"
    outside.mkdir()
    (Path(project.root_path) / "lib").symlink_to(outside)
    with pytest.raises(ValueError):
        repo.update_file(project.project_id, "lib/x.h", "x")
    assert not (outside / "x.h").exists()


def test_the_api_answers_400_for_a_bad_path(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HHIP_DATA_DIR", str(tmp_path))
    app = create_app(data_dir=tmp_path)
    with TestClient(app) as client:
        pid = client.post("/firmware/projects", json={"name": "p", "board_type": "arduino-uno", "template_id": "blink"}).json()["project_id"]
        res = client.put(f"/firmware/projects/{pid}/files", json={"path": "../../pwned.txt", "content": "x"})
        assert res.status_code == 400
        assert "allowed file path" in res.json()["detail"]
        ok = client.put(f"/firmware/projects/{pid}/files", json={"path": "src/helper.h", "content": "// ok"})
        assert ok.status_code == 200
    assert not list(tmp_path.rglob("pwned.txt"))
