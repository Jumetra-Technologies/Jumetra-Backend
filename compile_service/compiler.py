"""Compile one Arduino sketch to Intel HEX with Arduino CLI.

Stateless: every build gets a fresh temporary folder that is deleted
afterwards. Inputs are checked before the compiler sees them, because a
sketch is code from a stranger:

* only the Uno and Nano (arduino:avr), with the core installed in the image;
* at most 16 flat files and 256 KB, named like ``blink.ino`` or ``motor.h``,
  with exactly one ``.ino``; no ``sketch.yaml`` or other build settings;
* every ``#include`` names a plain header (``<Servo.h>``, ``"motor.h"``):
  no absolute paths, no ``..``, no macro includes, no ``__has_include`` and
  no ``.incbin`` (which would read a server file into the program);
* a time limit on the compiler.

The service still runs the compiler in a container with no secrets (see
Dockerfile), because these checks are a first line, not a sandbox.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Any, Callable, Optional

BOARDS: dict[str, str] = {
    "arduino-uno": "arduino:avr:uno",
    "arduino-nano": "arduino:avr:nano:cpu=atmega328",
}
MAX_FILES = 16
MAX_TOTAL_BYTES = 256 * 1024
TIMEOUT_S = 60
CACHE_SIZE = 64

_NAME = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_-]{0,63}\.(ino|h|hpp|c|cpp)$")
_INCLUDE_LINE = re.compile(r"^\s*#\s*include")
_INCLUDE_OK = re.compile(r'^\s*#\s*include\s*(<[A-Za-z0-9_][A-Za-z0-9_./-]*>|"[A-Za-z0-9_][A-Za-z0-9_./-]*")\s*(//.*|/\*.*\*/\s*)?$')
_FORBIDDEN = re.compile(r"incbin|__has_include|#\s*include_next|#\s*embed|#\s*import", re.IGNORECASE)

Runner = Callable[..., subprocess.CompletedProcess]


class SketchRefused(ValueError):
    """The sketch can't be built as sent: the message says why, in plain words."""


@dataclass
class CompileOutcome:
    ok: bool
    log: str = ""
    hex: Optional[str] = None
    flash: Optional[dict[str, int]] = None
    ram: Optional[dict[str, int]] = None
    duration_ms: int = 0
    cached: bool = False
    sketch_dir: str = ""
    message: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "ok": self.ok,
            "log": self.log,
            "durationMs": self.duration_ms,
            "cached": self.cached,
            "sketchDir": self.sketch_dir,
        }
        for key, value in (("hex", self.hex), ("flash", self.flash), ("ram", self.ram), ("message", self.message)):
            if value is not None:
                out[key] = value
        return out


def check_sketch(board: str, files: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """The sketch's files as (name, text), or SketchRefused saying what's wrong."""
    if board not in BOARDS:
        raise SketchRefused(f"Kiungo builds for the Arduino Uno and Nano here, not {board!r}.")
    if not isinstance(files, list) or not files:
        raise SketchRefused("Send the sketch's files.")
    if len(files) > MAX_FILES:
        raise SketchRefused(f"A sketch can have up to {MAX_FILES} files here.")
    out: list[tuple[str, str]] = []
    total = 0
    seen: set[str] = set()
    for f in files:
        name = f.get("path") if isinstance(f, dict) else None
        text = f.get("content") if isinstance(f, dict) else None
        if not isinstance(name, str) or not _NAME.match(name):
            raise SketchRefused(
                f"{name!r} isn't an allowed file name: use letters, digits, '_' and '-', ending in .ino, .h, .hpp, .c or .cpp, with no folders."
            )
        if name.lower() in seen:
            raise SketchRefused(f"Two files are called {name}.")
        seen.add(name.lower())
        if not isinstance(text, str):
            raise SketchRefused(f"{name} has no text.")
        total += len(text.encode("utf-8"))
        if total > MAX_TOTAL_BYTES:
            raise SketchRefused(f"The sketch is over {MAX_TOTAL_BYTES // 1024} KB.")
        _check_text(name, text)
        out.append((name, text))
    inos = [n for n, _ in out if n.endswith(".ino")]
    if len(inos) != 1:
        raise SketchRefused("A sketch needs exactly one .ino file.")
    return out


def _check_text(name: str, text: str) -> None:
    if _FORBIDDEN.search(text):
        found = _FORBIDDEN.search(text).group(0)  # type: ignore[union-attr]
        raise SketchRefused(f"{name} uses {found}, which Kiungo's online build doesn't allow.")
    lines = text.splitlines()
    for number, line in enumerate(lines, start=1):
        if not _INCLUDE_LINE.match(line):
            continue
        if line.rstrip().endswith("\\"):
            raise SketchRefused(f"{name} line {number}: an #include can't continue onto the next line.")
        if not _INCLUDE_OK.match(line) or ".." in line or "<" + "/" in line or '"/' in line:
            raise SketchRefused(
                f"{name} line {number}: #include a library or a file of this sketch by name, "
                "like #include <Servo.h> or #include \"motor.h\"."
            )


def cache_key(board: str, files: list[tuple[str, str]]) -> str:
    h = hashlib.sha256(board.encode())
    for name, text in sorted(files):
        h.update(b"\0" + name.encode() + b"\0" + text.encode())
    return h.hexdigest()


class Compiler:
    """Runs Arduino CLI, one fresh folder per build, with a small LRU cache of good builds."""

    def __init__(self, cli: str = "arduino-cli", *, runner: Optional[Runner] = None, now: Callable[[], float] = time.perf_counter) -> None:
        self.cli = cli
        self._runner = runner or subprocess.run
        self._now = now
        self._cache: "OrderedDict[str, CompileOutcome]" = OrderedDict()
        self._lock = Lock()

    def compile(self, board: str, files: list[dict[str, Any]]) -> CompileOutcome:
        sketch = check_sketch(board, files)
        key = cache_key(board, sketch)
        with self._lock:
            hit = self._cache.get(key)
            if hit is not None:
                self._cache.move_to_end(key)
                return CompileOutcome(**{**hit.__dict__, "cached": True, "duration_ms": 0})

        started = self._now()
        work = Path(tempfile.mkdtemp(prefix="kiungo-build-"))
        try:
            ino = next(n for n, _ in sketch if n.endswith(".ino"))
            sketch_dir = work / ino[: -len(".ino")]
            out_dir = work / "out"
            sketch_dir.mkdir()
            out_dir.mkdir()
            for name, text in sketch:
                (sketch_dir / name).write_text(text, encoding="utf-8")
            cmd = [self.cli, "compile", "--fqbn", BOARDS[board], "--output-dir", str(out_dir), "--build-path", str(work / "build"), "--format", "json", str(sketch_dir)]
            try:
                proc = self._runner(cmd, capture_output=True, text=True, timeout=TIMEOUT_S, cwd=str(work), env=_compiler_env())
            except subprocess.TimeoutExpired:
                return CompileOutcome(ok=False, message=f"The build took longer than {TIMEOUT_S} seconds, so it was stopped.", duration_ms=self._ms(started), sketch_dir=str(sketch_dir))
            outcome = _report(proc, out_dir / f"{ino}.hex", self._ms(started), str(sketch_dir))
        finally:
            shutil.rmtree(work, ignore_errors=True)

        if outcome.ok:
            with self._lock:
                self._cache[key] = outcome
                self._cache.move_to_end(key)
                while len(self._cache) > CACHE_SIZE:
                    self._cache.popitem(last=False)
        return outcome

    def _ms(self, started: float) -> int:
        return int(round((self._now() - started) * 1000))


def _compiler_env() -> dict[str, str]:
    """Only what Arduino CLI needs: no secrets from the service's own environment."""
    keep = ("PATH", "HOME", "LANG", "ARDUINO_DIRECTORIES_DATA", "ARDUINO_DIRECTORIES_USER", "ARDUINO_DIRECTORIES_DOWNLOADS", "ARDUINO_BUILD_CACHE_PATH", "TMPDIR")
    env = {k: os.environ[k] for k in keep if k in os.environ}
    env.setdefault("PATH", "/usr/local/bin:/usr/bin:/bin")
    env["ARDUINO_UPDATER_ENABLE_NOTIFICATION"] = "false"
    return env


def _report(proc: subprocess.CompletedProcess, hex_file: Path, duration_ms: int, sketch_dir: str) -> CompileOutcome:
    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        data = {}
    log = "\n".join(s for s in (data.get("compiler_out"), data.get("compiler_err")) if s).strip() or (proc.stderr or proc.stdout or "").strip()
    sections = (data.get("builder_result") or {}).get("executable_sections_size") or []
    text = next((s for s in sections if s.get("name") == "text"), None)
    ram = next((s for s in sections if s.get("name") == "data"), None)
    ok = bool(data.get("success")) and proc.returncode == 0
    outcome = CompileOutcome(
        ok=ok,
        log=log,
        flash={"used": int(text["size"]), "max": int(text["max_size"])} if text else None,
        ram={"used": int(ram["size"]), "max": int(ram["max_size"])} if ram else None,
        duration_ms=duration_ms,
        sketch_dir=sketch_dir,
    )
    if ok:
        if not hex_file.exists():
            outcome.ok = False
            outcome.message = "The build finished but no program was written."
        else:
            outcome.hex = hex_file.read_text(encoding="ascii")
    elif not log:
        outcome.message = "The compiler didn't run. Try again in a minute."
    return outcome
