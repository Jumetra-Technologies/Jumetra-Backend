"""The compile service (POST /firmware/compile): checks, the compiler report, limits. The compiler is stubbed here; CI's compile-service job runs the real one."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from compile_service.app import RateLimiter, create_app
from compile_service.compiler import Compiler, SketchRefused, check_sketch

BLINK = "void setup(){pinMode(13,OUTPUT);}\nvoid loop(){digitalWrite(13,HIGH);delay(500);digitalWrite(13,LOW);delay(500);}\n"
HEX = ":100000000C945C000C946E000C946E000C946E00CA\n:00000001FF\n"
ORIGIN = "https://kiungo-labs-technologies.vercel.app"


class FakeCli:
    """Plays Arduino CLI: writes the .hex where --output-dir says and answers with its JSON report."""

    def __init__(self, *, success: bool = True, err: str = "", timeout: bool = False) -> None:
        self.success, self.err, self.timeout = success, err, timeout
        self.calls: list[list[str]] = []
        self.envs: list[dict[str, str]] = []

    def __call__(self, cmd, **kw):
        self.calls.append(cmd)
        self.envs.append(kw.get("env") or {})
        if self.timeout:
            raise subprocess.TimeoutExpired(cmd, 60)
        out = Path(cmd[cmd.index("--output-dir") + 1])
        sketch = Path(cmd[-1])
        assert (sketch / f"{sketch.name}.ino").exists()
        if self.success:
            (out / f"{sketch.name}.ino.hex").write_text(HEX)
        report = {
            "success": self.success,
            "compiler_out": "Sketch uses 924 bytes (2%) of program storage space.",
            "compiler_err": self.err,
            "builder_result": {"executable_sections_size": [{"name": "text", "size": 924, "max_size": 32256}, {"name": "data", "size": 9, "max_size": 2048}]},
        }
        return subprocess.CompletedProcess(cmd, 0 if self.success else 1, json.dumps(report), "")


def files(**named: str) -> list[dict[str, str]]:
    return [{"path": k.replace("__", "."), "content": v} for k, v in named.items()]


# ----- what gets refused before the compiler runs -----


@pytest.mark.parametrize(
    "sketch, why",
    [
        (files(Blink__ino=BLINK, Other__ino=BLINK), "exactly one .ino"),
        (files(motor__h="int x;"), "exactly one .ino"),
        ([{"path": "../Blink.ino", "content": BLINK}], "allowed file name"),
        ([{"path": "src/Blink.ino", "content": BLINK}], "allowed file name"),
        ([{"path": "sketch.yaml", "content": "x"}], "allowed file name"),
        (files(Blink__ino='#include "/etc/passwd"\n' + BLINK), "#include a library"),
        (files(Blink__ino='#include "../../app/main.py"\n' + BLINK), "#include a library"),
        (files(Blink__ino="#define F \"/etc/passwd\"\n#include F\n" + BLINK), "#include a library"),
        (files(Blink__ino='#include <Servo.h> \\\n' + BLINK), "continue onto the next line"),
        (files(Blink__ino='asm(".incbin \\"/etc/passwd\\"");\n' + BLINK), "incbin"),
        (files(Blink__ino="#if __has_include(<x.h>)\n#endif\n" + BLINK), "__has_include"),
        (files(Blink__ino="#include_next <x.h>\n" + BLINK), "include_next"),
    ],
)
def test_unsafe_or_odd_sketches_are_refused(sketch, why):
    with pytest.raises(SketchRefused, match=why):
        check_sketch("arduino-uno", sketch)


def test_ordinary_includes_are_fine():
    text = '#include <Servo.h>\n#include <avr/pgmspace.h>\n#include "motor.h" // the motor\n' + BLINK
    assert check_sketch("arduino-uno", files(Blink__ino=text, motor__h="int speed;"))


def test_other_boards_and_big_sketches_are_refused():
    with pytest.raises(SketchRefused, match="Uno and Nano"):
        check_sketch("esp32", files(Blink__ino=BLINK))
    with pytest.raises(SketchRefused, match="KB"):
        check_sketch("arduino-uno", files(Blink__ino="//" + "x" * 300_000))
    with pytest.raises(SketchRefused, match="up to 16"):
        check_sketch("arduino-uno", files(Blink__ino=BLINK) + [{"path": f"f{i}.h", "content": ""} for i in range(16)])


# ----- the build -----


def test_a_good_build_returns_the_hex_sizes_and_log_and_cleans_up():
    cli = FakeCli()
    out = Compiler(runner=cli).compile("arduino-uno", files(Blink__ino=BLINK)).to_dict()
    assert out["ok"] is True
    assert out["hex"] == HEX
    assert out["flash"] == {"used": 924, "max": 32256}
    assert out["ram"] == {"used": 9, "max": 2048}
    assert "Sketch uses 924 bytes" in out["log"]
    assert out["sketchDir"].endswith("/Blink")
    assert not Path(out["sketchDir"]).exists()  # the build folder is gone
    cmd = cli.calls[0]
    assert cmd[cmd.index("--fqbn") + 1] == "arduino:avr:uno"


def test_the_compiler_never_sees_the_services_secrets(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "s3cret")
    monkeypatch.setenv("DATABASE_URL", "postgres://x")
    cli = FakeCli()
    Compiler(runner=cli).compile("arduino-uno", files(Blink__ino=BLINK))
    assert "SESSION_SECRET" not in cli.envs[0] and "DATABASE_URL" not in cli.envs[0]


def test_a_failed_build_returns_the_compiler_messages_and_no_hex():
    err = "/tmp/kiungo-build-x/Blink/Blink.ino:2:1: error: 'digitalWrit' was not declared in this scope"
    out = Compiler(runner=FakeCli(success=False, err=err)).compile("arduino-uno", files(Blink__ino=BLINK)).to_dict()
    assert out["ok"] is False and "hex" not in out
    assert "was not declared" in out["log"]


def test_the_same_sketch_twice_is_built_once():
    cli = FakeCli()
    compiler = Compiler(runner=cli)
    first = compiler.compile("arduino-uno", files(Blink__ino=BLINK))
    again = compiler.compile("arduino-uno", files(Blink__ino=BLINK))
    assert len(cli.calls) == 1
    assert again.cached is True and again.hex == first.hex
    compiler.compile("arduino-nano", files(Blink__ino=BLINK))
    assert len(cli.calls) == 2  # another board is another build
    assert cli.calls[1][cli.calls[1].index("--fqbn") + 1] == "arduino:avr:nano:cpu=atmega328"


def test_a_build_that_runs_too_long_is_stopped_with_a_plain_message():
    out = Compiler(runner=FakeCli(timeout=True)).compile("arduino-uno", files(Blink__ino=BLINK)).to_dict()
    assert out["ok"] is False
    assert "60 seconds" in out["message"]


# ----- the web service -----


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("COMPILE_RATE_PER_MINUTE", "3")
    app = create_app(Compiler(runner=FakeCli()))
    with TestClient(app) as c:
        yield c


def test_the_endpoint_compiles_for_an_allowed_website(client):
    res = client.post("/firmware/compile", json={"board": "arduino-uno", "files": files(Blink__ino=BLINK)}, headers={"Origin": ORIGIN})
    assert res.status_code == 200
    assert res.json()["hex"] == HEX
    assert res.headers["access-control-allow-origin"] == ORIGIN


def test_the_endpoint_refuses_other_websites_and_bad_sketches(client):
    assert client.post("/firmware/compile", json={"files": files(Blink__ino=BLINK)}, headers={"Origin": "https://evil.example"}).status_code == 403
    bad = client.post("/firmware/compile", json={"files": [{"path": "../x.ino", "content": ""}]}, headers={"Origin": ORIGIN})
    assert bad.status_code == 422 and "allowed file name" in bad.json()["detail"]


def test_the_endpoint_limits_builds_per_address(client):
    for i in range(3):
        assert client.post("/firmware/compile", json={"files": files(Blink__ino=BLINK + f"//{i}")}, headers={"X-Forwarded-For": "203.0.113.9"}).status_code == 200
    res = client.post("/firmware/compile", json={"files": files(Blink__ino=BLINK)}, headers={"X-Forwarded-For": "203.0.113.9"})
    assert res.status_code == 429 and "Retry-After" in res.headers
    # Another address still builds.
    assert client.post("/firmware/compile", json={"files": files(Blink__ino=BLINK)}, headers={"X-Forwarded-For": "198.51.100.7"}).status_code == 200


def test_the_hourly_limit_also_holds():
    t = [0.0]
    limiter = RateLimiter(per_minute=100, per_hour=2, now=lambda: t[0])
    assert limiter.allow("a") == 0
    t[0] += 120
    assert limiter.allow("a") == 0
    t[0] += 120
    assert limiter.allow("a") > 0
    t[0] += 3600
    assert limiter.allow("a") == 0


def test_health(client):
    assert client.get("/health").json()["ok"] is True


# ----- the same rules as the preprocessor sees the text (audit N-1, 13 Nov 2026) -----

SECRET = "/proc/1/environ"


@pytest.mark.parametrize(
    "text",
    [
        f'# /**/ include "{SECRET}"\n',  # a comment between # and include
        f'#in\\\nclude "{SECRET}"\n',  # include split across lines
        f'#include \\\n"{SECRET}"\n',  # the header on the next line
        f'%:include "{SECRET}"\n',  # digraph for #
        f'??=include "{SECRET}"\n',  # trigraph for #
        f'#include /* x */ "{SECRET}"\n',
        f'asm(".inc" "bin \\"{SECRET}\\"");\n',  # string pasting
        f'__asm__ __volatile__ (".include \\"{SECRET}\\"");\n',  # the assembler's own include
        '#define S(x) #x\nasm(".inc" S(bin) " \\"/etc/passwd\\"");\n',  # template built by a macro
        '#define A asm\nA(".incbin \\"/etc/passwd\\"");\n',  # asm by another name
        "#define CAT(a, b) a##b\n",  # token pasting
        '#define CAT(a, b) a%:%:b\n',
        "#if __has_embed(<x>)\n#endif\n",
        '_Pragma("once")\n',
        f'#embed "{SECRET}"\n',
        f'#import "{SECRET}"\n',
    ],
)
def test_preprocessor_spellings_of_forbidden_things_are_refused(text):
    with pytest.raises(SketchRefused):
        check_sketch("arduino-uno", files(Blink__ino=text + BLINK))


@pytest.mark.parametrize(
    "text",
    [
        "#define PINS(x) \\\n  pinMode(x, OUTPUT); \\\n  digitalWrite(x, LOW)\n",  # multi-line macros still work
        '# include <Servo.h>\n',
        '#include <Servo.h> /* the servo library */\n',
        '// #include "/etc/passwd" is only a comment\n',
        '/* asm(".word 1") in a comment */\n',
        'const char *msg = "use # and ## and asm(\\".x\\") freely in text";\n',
        'const char *raw = R"(// not a comment, "quotes" too)";\n',
        'void tick() { asm("nop"); __asm__ __volatile__ ("cli" ::: "memory"); asm volatile("sei\\n\\t"); }\n',
        "char c = '#'; char q = '\"';\n",
        '#define LED 13\n#ifdef LED\n#endif\n',
    ],
)
def test_ordinary_sketches_still_pass(text):
    assert check_sketch("arduino-uno", files(Blink__ino=text + BLINK))


def test_a_trusted_client_header_keys_the_limit(monkeypatch):
    from compile_service.app import _client

    class Req:
        def __init__(self, headers):
            self.headers = headers
            self.client = None

    monkeypatch.setenv("COMPILE_CLIENT_IP_HEADER", "CF-Connecting-IP")
    assert _client(Req({"cf-connecting-ip": "203.0.113.9", "x-forwarded-for": "1.2.3.4"})) == "203.0.113.9"
    assert _client(Req({"x-forwarded-for": "1.2.3.4, 10.0.0.1"})) == "1.2.3.4"
    monkeypatch.delenv("COMPILE_CLIENT_IP_HEADER")
    assert _client(Req({"cf-connecting-ip": "203.0.113.9", "x-forwarded-for": "1.2.3.4"})) == "1.2.3.4"


def test_an_oversized_file_is_refused_while_reading(client):
    big = [{"path": "Blink.ino", "content": "x" * (256 * 1024 + 1)}]
    assert client.post("/firmware/compile", json={"board": "arduino-uno", "files": big}, headers={"Origin": ORIGIN}).status_code == 422
