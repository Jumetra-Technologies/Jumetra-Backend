"""Sprint 31 — Embedded Development Studio tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from engine.firmware import (
    BuildCache,
    CompilerAdapter,
    FirmwareEventType,
    FirmwareMonitor,
    FirmwareProjectRepository,
    FirmwareStudioService,
    SerialConsole,
    ToolchainManager,
    UploadManager,
    generate_template,
    list_templates,
)
from engine.firmware.compiler_adapter import BuildResult
from engine.firmware.firmware_project import FirmwareProject, ProjectType
from engine.firmware.project_templates import default_language_for
from engine.hybrid.wiring import WireManager


@pytest.fixture()
def which_none():
    return lambda _cmd: None


@pytest.fixture()
def studio(tmp_path: Path, which_none):
    tc = ToolchainManager(which=which_none)
    return FirmwareStudioService(
        data_dir=tmp_path,
        force_dry_run=True,
        toolchain_manager=tc,
    )


class TestTemplates:
    def test_list_templates(self):
        items = list_templates()
        ids = {t["id"] for t in items}
        assert "blink" in ids and "mqtt" in ids and "dht11" in ids
        assert len(items) >= 13

    def test_generate_arduino_blink(self):
        files = generate_template("blink", board_type="esp32")
        assert any(f.path.endswith(".ino") for f in files)
        assert "GPIO HIGH" in files[0].content

    def test_generate_platformio_and_python(self):
        pio = generate_template(
            "led", board_type="arduino-uno", project_type=ProjectType.PLATFORMIO.value
        )
        assert any(f.path == "platformio.ini" for f in pio)
        py = generate_template(
            "blink",
            board_type="raspberry-pi-4",
            project_type=ProjectType.RASPBERRY_PI.value,
        )
        assert any(f.path.endswith(".py") for f in py)

    def test_default_language(self):
        assert default_language_for(ProjectType.ESP_IDF.value) == "esp-idf"


class TestToolchainDetection:
    def test_all_missing(self, which_none):
        mgr = ToolchainManager(which=which_none)
        tools = mgr.detect_all()
        assert len(tools) >= 6
        assert all(not t.installed for t in tools)
        missing = mgr.guided_setup()
        assert len(missing) == len(tools)

    def test_python_detected(self):
        mgr = ToolchainManager(
            which=lambda c: "/usr/bin/python" if c in ("python", "python3") else None
        )
        tools = {t.id: t for t in mgr.detect_all()}
        assert tools["python"].installed
        assert tools["arduino-cli"].installed is False


class TestProjectCreation:
    def test_create_and_list(self, studio: FirmwareStudioService):
        created = studio.create_project(
            {"name": "Demo", "board_type": "esp32", "template_id": "blink"}
        )
        assert created["project_id"]
        assert created["files"]
        listed = studio.list_projects()
        assert listed["count"] == 1
        got = studio.get_project(created["project_id"])
        assert "tree" in got
        assert "Source" in got["tree"]

    def test_save_file(self, studio: FirmwareStudioService):
        created = studio.create_project({"name": "X", "template_id": "led"})
        path = created["files"][0]["path"]
        updated = studio.save_file(created["project_id"], path, "// edited\n")
        assert any(f["content"].startswith("// edited") for f in updated["files"])


class TestBuildUpload:
    def test_build_dry_run(self, studio: FirmwareStudioService):
        p = studio.create_project(
            {"name": "B", "template_id": "blink", "board_type": "arduino-uno"}
        )
        result = studio.build(p["project_id"], use_cache=False)
        assert result["success"] is True
        assert result["dry_run"] is True
        assert result["binary_size_bytes"] > 0
        assert result["memory"]["flash_total"] > 0
        assert result["build_time_ms"] >= 0

    def test_build_cache(self, studio: FirmwareStudioService):
        p = studio.create_project({"name": "C", "template_id": "blink"})
        first = studio.build(p["project_id"], use_cache=False)
        second = studio.build(p["project_id"], use_cache=True)
        assert second.get("from_cache") is True
        assert second["build_id"] == first["build_id"]

    def test_build_failure_marker(self, studio: FirmwareStudioService):
        p = studio.create_project({"name": "Fail", "template_id": "blink"})
        path = p["files"][0]["path"]
        studio.save_file(p["project_id"], path, "TODO_ERROR\n")
        result = studio.build(p["project_id"], use_cache=False)
        assert result["success"] is False
        assert result["errors"]

    def test_upload(self, studio: FirmwareStudioService):
        p = studio.create_project({"name": "U", "template_id": "blink"})
        studio.build(p["project_id"], use_cache=False)
        up = studio.upload(p["project_id"], port="COM9")
        assert up["success"] is True
        assert up["verified"] is True
        assert up["reset"] is True


class TestSerialAndGpio:
    def test_serial_console(self):
        c = SerialConsole()
        c.append("hello\x1b[31mred\x1b[0m")
        lines = c.lines()
        assert lines[0]["text"] == "hellored"
        c.pause()
        assert c.append("skipped") is None
        c.resume()
        c.write("AT")
        assert c.lines(direction="tx")[-1]["text"] == "AT"
        assert "hello" in c.export_text()

    def test_gpio_monitor_fanout(self, tmp_path: Path):
        wm = WireManager(data_dir=tmp_path)
        mon = FirmwareMonitor(device_id="esp1", wire_manager=wm)
        events = mon.ingest("GPIO HIGH")
        assert events
        assert events[0]["logic"] == "HIGH"
        assert mon.gpio_snapshot()


class TestCompilerAdapterUnit:
    def test_adapter_dry(self, tmp_path: Path, which_none):
        repo = FirmwareProjectRepository(tmp_path)
        files = generate_template("servo", board_type="arduino-uno")
        project = repo.create(
            name="S",
            project_type="arduino-sketch",
            language="arduino-cpp",
            board_type="arduino-uno",
            files=files,
        )
        adapter = CompilerAdapter(ToolchainManager(which=which_none), force_dry_run=True)
        result = adapter.build(project)
        assert result.success
        assert Path(result.binary_path).exists()


class TestBuildCache:
    def test_cache_roundtrip(self, tmp_path: Path):
        cache = BuildCache(tmp_path)
        key = cache.content_hash([{"path": "a", "content": "x"}], "esp32")
        cache.put(key, {"build_id": "1", "success": True})
        assert cache.get(key)["build_id"] == "1"
        assert cache.clear() >= 1


@pytest.fixture()
def client(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HHIP_FIRMWARE_DRY_RUN", "1")
    app = create_app(data_dir=tmp_path)
    with TestClient(app) as test_client:
        yield test_client


class TestFirmwareREST:
    def test_projects_build_upload_logs_serial(self, client: TestClient):
        created = client.post(
            "/firmware/projects",
            json={"name": "API Blink", "board_type": "esp32", "template_id": "blink"},
        )
        assert created.status_code == 200
        pid = created.json()["project_id"]

        listed = client.get("/firmware/projects")
        assert listed.status_code == 200
        assert listed.json()["count"] >= 1

        got = client.get(f"/firmware/projects/{pid}")
        assert got.status_code == 200
        assert "tree" in got.json()

        tools = client.get("/firmware/toolchains")
        assert tools.status_code == 200
        assert tools.json()["count"] >= 6

        templates = client.get("/firmware/templates")
        assert templates.status_code == 200
        assert templates.json()["count"] >= 10

        built = client.post("/firmware/build", json={"project_id": pid, "use_cache": False})
        assert built.status_code == 200
        assert built.json()["success"] is True

        uploaded = client.post("/firmware/upload", json={"project_id": pid, "port": "COM3"})
        assert uploaded.status_code == 200
        assert uploaded.json()["success"] is True

        logs = client.get("/firmware/logs")
        assert logs.status_code == 200
        assert logs.json()["count"] >= 1

        serial = client.get("/firmware/serial")
        assert serial.status_code == 200
        assert "lines" in serial.json()

        client.post("/firmware/serial", json={"action": "write", "line": "ping"})
        serial2 = client.get("/firmware/serial")
        assert any(l.get("direction") == "tx" for l in serial2.json()["lines"])

    def test_missing_project(self, client: TestClient):
        assert client.get("/firmware/projects/nope").status_code == 404
        assert client.post("/firmware/build", json={"project_id": "nope"}).status_code == 404


class TestFirmwareWebsocket:
    def test_ws_build_events(self, client: TestClient):
        created = client.post(
            "/firmware/projects",
            json={"name": "WS", "template_id": "blink", "board_type": "esp32"},
        )
        pid = created.json()["project_id"]
        with client.websocket_connect("/ws/firmware") as ws:
            snap = ws.receive_json()
            assert snap["type"] == "firmware_snapshot"
            client.app.state.firmware_service.build(pid, use_cache=False)
            types: set[str] = set()
            for _ in range(12):
                msg = ws.receive_json()
                types.add(str(msg.get("type") or ""))
                if (
                    FirmwareEventType.BUILD_COMPLETED in types
                    or FirmwareEventType.BUILD_FAILED in types
                ):
                    break
            assert (
                FirmwareEventType.BUILD_STARTED in types
                or FirmwareEventType.BUILD_COMPLETED in types
            )
            ws.send_text("ping")
            for _ in range(20):
                msg = ws.receive_json()
                if msg.get("type") == "pong":
                    return
            pytest.fail("expected pong")


class TestUploadManagerUnit:
    def test_upload_without_binary(self, tmp_path: Path, which_none):
        mgr = UploadManager(ToolchainManager(which=which_none), force_dry_run=True)
        project = FirmwareProject(
            project_id="p1",
            name="n",
            project_type="arduino-sketch",
            language="arduino-cpp",
            board_type="esp32",
            root_path=str(tmp_path),
        )
        bad = BuildResult(build_id="b", project_id="p1", success=False)
        res = mgr.upload(project, bad, port="COM1")
        assert res.success is False


@pytest.mark.parametrize(
    "template_id",
    ["blink", "led", "servo", "relay", "dht11", "hc-sr04", "mq2", "lcd", "i2c", "spi", "wifi", "bluetooth", "mqtt"],
)
class TestAllTemplatesGenerate:
    def test_template_has_files(self, template_id: str):
        files = generate_template(template_id, board_type="esp32")
        assert files
        assert all(f.path for f in files)


@pytest.mark.parametrize(
    "board",
    [
        "arduino-uno",
        "arduino-mega",
        "esp32",
        "esp8266",
        "stm32",
        "raspberry-pi-pico",
        "teensy",
        "nrf52",
        "microbit",
    ],
)
class TestBoardBuilds:
    def test_build_board(self, studio: FirmwareStudioService, board: str):
        p = studio.create_project({"name": board, "board_type": board, "template_id": "blink"})
        result = studio.build(p["project_id"], use_cache=False)
        assert result["success"] is True
        assert result["memory"]["flash_total"] > 0


class TestEspIdfAndMicropythonProjects:
    def test_esp_idf_project(self, studio: FirmwareStudioService):
        p = studio.create_project(
            {
                "name": "IDF",
                "project_type": "esp-idf",
                "board_type": "esp32",
                "template_id": "blink",
            }
        )
        assert any(f["path"].endswith("main.c") for f in p["files"])
        assert studio.build(p["project_id"], use_cache=False)["success"]

    def test_micropython_project(self, studio: FirmwareStudioService):
        p = studio.create_project(
            {
                "name": "MP",
                "project_type": "micropython",
                "board_type": "esp32",
                "template_id": "blink",
            }
        )
        assert any(f["path"].endswith(".py") for f in p["files"])


class TestStudioEvents:
    def test_build_emits_events(self, studio: FirmwareStudioService):
        seen: list[str] = []
        studio.subscribe_ws(lambda m: seen.append(m["type"]))
        p = studio.create_project({"name": "E", "template_id": "blink"})
        studio.build(p["project_id"], use_cache=False)
        assert FirmwareEventType.BUILD_STARTED in seen
        assert FirmwareEventType.BUILD_COMPLETED in seen

    def test_serial_api_actions(self, studio: FirmwareStudioService):
        studio.serial(action="write", line="hi")
        studio.serial(action="pause")
        assert studio.serial()["paused"] is True
        studio.serial(action="resume")
        studio.serial(action="clear")
        assert studio.serial()["line_count"] == 0
