"""Firmware monitor — GPIO debug + live sync hooks to workspace/wiring."""

from __future__ import annotations

import re
import time
from typing import Any, Callable, Optional

from .serial_console import SerialConsole

GPIO_HIGH_RE = re.compile(r"GPIO\s*(?P<pin>\w+)?\s*HIGH", re.I)
GPIO_LOW_RE = re.compile(r"GPIO\s*(?P<pin>\w+)?\s*LOW", re.I)
GPIO_STATE_RE = re.compile(
    r"(?:GPIO|PIN)\s*(?P<pin>\w+)\s*(?:=|:)?\s*(?P<val>HIGH|LOW|\d+)", re.I
)


class FirmwareMonitor:
    """
    Parse serial firmware logs into GPIO debug events and fan out to
    WireManager / WorkspaceSync when injected.
    """

    def __init__(
        self,
        console: Optional[SerialConsole] = None,
        *,
        wire_manager: Any = None,
        workspace_sync: Any = None,
        device_id: str = "",
    ) -> None:
        self.console = console or SerialConsole()
        self.wire_manager = wire_manager
        self.workspace_sync = workspace_sync
        self.device_id = device_id
        self._gpio: dict[str, dict[str, Any]] = {}
        self._ws: list[Callable[[dict[str, Any]], None]] = []
        self.console.subscribe(self._on_line)

    def subscribe_ws(self, cb: Callable[[dict[str, Any]], None]) -> None:
        self._ws.append(cb)

    def unsubscribe_ws(self, cb: Callable[[dict[str, Any]], None]) -> None:
        try:
            self._ws.remove(cb)
        except ValueError:
            pass

    def set_device(self, device_id: str) -> None:
        self.device_id = device_id

    def gpio_snapshot(self) -> list[dict[str, Any]]:
        return list(self._gpio.values())

    def ingest(self, text: str, *, device_id: str = "") -> list[dict[str, Any]]:
        """Ingest a firmware log line and return GPIO events produced."""
        if device_id:
            self.device_id = device_id
        self.console.append(text, direction="rx")
        return self._parse(text)

    def _on_line(self, line: Any) -> None:
        if getattr(line, "direction", "rx") != "rx":
            return
        self._parse(line.text)

    def _parse(self, text: str) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        pin = "D2"
        value: Optional[int] = None
        m = GPIO_STATE_RE.search(text)
        if m:
            pin = m.group("pin") or pin
            raw = m.group("val").upper()
            value = 1 if raw in ("HIGH", "1") else 0 if raw in ("LOW", "0") else int(raw)
        elif GPIO_HIGH_RE.search(text):
            mh = GPIO_HIGH_RE.search(text)
            pin = (mh.group("pin") if mh and mh.group("pin") else None) or "LED"
            value = 1
        elif GPIO_LOW_RE.search(text):
            ml = GPIO_LOW_RE.search(text)
            pin = (ml.group("pin") if ml and ml.group("pin") else None) or "LED"
            value = 0

        if value is None:
            return events

        state = {
            "device_id": self.device_id or "firmware",
            "pin": pin,
            "value": value,
            "logic": "HIGH" if value else "LOW",
            "direction": "OUTPUT",
            "voltage": 3.3 if value else 0.0,
            "frequency_hz": 0.0,
            "pwm": False,
            "timestamp_ms": int(time.time() * 1000),
        }
        self._gpio[f"{state['device_id']}:{pin}"] = state
        events.append(state)
        self._fanout(state)
        return events

    def _fanout(self, state: dict[str, Any]) -> None:
        payload = {"type": "GPIO_DEBUG", "event": "GPIO_DEBUG", "payload": state}
        for cb in list(self._ws):
            try:
                cb(payload)
            except Exception:  # noqa: BLE001
                pass
        did = str(state["device_id"])
        pin = str(state["pin"])
        val = int(state["value"])
        if self.wire_manager is not None:
            try:
                self.wire_manager.write_pin(did, pin, val, mode="OUTPUT")
            except Exception:  # noqa: BLE001
                pass
        if self.workspace_sync is not None:
            try:
                self.workspace_sync.update_pin_state(did, pin, val, voltage=state.get("voltage"))
            except Exception:  # noqa: BLE001
                pass
