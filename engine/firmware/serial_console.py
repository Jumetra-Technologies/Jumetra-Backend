"""In-memory serial console with search/filter/export."""

from __future__ import annotations

import re
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Deque, Optional

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


@dataclass
class SerialLine:
    timestamp_ms: int
    text: str
    raw: str = ""
    port: str = ""
    direction: str = "rx"  # rx | tx

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp_ms": self.timestamp_ms,
            "text": self.text,
            "raw": self.raw or self.text,
            "port": self.port,
            "direction": self.direction,
        }


class SerialConsole:
    """Buffered serial monitor supporting 115200+ baud sessions (logical)."""

    def __init__(self, *, max_lines: int = 5000) -> None:
        self.max_lines = max_lines
        self._lines: Deque[SerialLine] = deque(maxlen=max_lines)
        self._paused = False
        self._baud = 115200
        self._port = ""
        self._subscribers: list[Callable[[SerialLine], None]] = []

    def configure(self, *, port: str = "", baud: int = 115200) -> None:
        self._port = port
        self._baud = baud

    def subscribe(self, cb: Callable[[SerialLine], None]) -> None:
        self._subscribers.append(cb)

    def unsubscribe(self, cb: Callable[[SerialLine], None]) -> None:
        try:
            self._subscribers.remove(cb)
        except ValueError:
            pass

    def pause(self) -> None:
        self._paused = True

    def resume(self) -> None:
        self._paused = False

    @property
    def paused(self) -> bool:
        return self._paused

    def clear(self) -> None:
        self._lines.clear()

    def append(
        self,
        text: str,
        *,
        port: str = "",
        direction: str = "rx",
        timestamp_ms: Optional[int] = None,
    ) -> Optional[SerialLine]:
        if self._paused and direction == "rx":
            return None
        raw = text
        clean = ANSI_RE.sub("", text)
        line = SerialLine(
            timestamp_ms=timestamp_ms or int(time.time() * 1000),
            text=clean.rstrip("\r\n"),
            raw=raw,
            port=port or self._port,
            direction=direction,
        )
        self._lines.append(line)
        for cb in list(self._subscribers):
            try:
                cb(line)
            except Exception:  # noqa: BLE001
                pass
        return line

    def write(self, text: str) -> SerialLine:
        """TX to device (buffered; physical transport optional)."""
        line = self.append(text, direction="tx") 
        assert line is not None
        return line

    def lines(
        self,
        *,
        limit: int = 500,
        query: str = "",
        direction: str = "",
    ) -> list[dict[str, Any]]:
        items = list(self._lines)
        if direction:
            items = [l for l in items if l.direction == direction]
        if query:
            q = query.lower()
            items = [l for l in items if q in l.text.lower()]
        return [l.to_dict() for l in items[-limit:]]

    def export_text(self, *, query: str = "") -> str:
        rows = self.lines(limit=self.max_lines, query=query)
        return "\n".join(f"{r['timestamp_ms']}\t{r['direction']}\t{r['text']}" for r in rows)

    def status(self) -> dict[str, Any]:
        return {
            "port": self._port,
            "baud": self._baud,
            "paused": self._paused,
            "line_count": len(self._lines),
        }
