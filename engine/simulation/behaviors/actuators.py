"""Virtual actuator implementations."""

from __future__ import annotations

from typing import Any

from .base import VirtualActuator


class LEDActuator(VirtualActuator):
    component_id = "led"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.state.setdefault("on", False)
        self.state.setdefault("brightness", 0)

    def _apply_command(self, action: str, value: Any) -> dict[str, Any]:
        if action in {"on", "ON"}:
            self.state["on"] = True
            self.state["brightness"] = 255
        elif action in {"off", "OFF"}:
            self.state["on"] = False
            self.state["brightness"] = 0
        elif action == "brightness":
            level = max(0, min(255, int(value or 0)))
            self.state["brightness"] = level
            self.state["on"] = level > 0
        elif action == "toggle":
            self.state["on"] = not self.state.get("on", False)
            self.state["brightness"] = 255 if self.state["on"] else 0
        return dict(self.state)


class RelayActuator(VirtualActuator):
    component_id = "relay"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.state.setdefault("closed", False)

    def _apply_command(self, action: str, value: Any) -> dict[str, Any]:
        if action in {"close", "on", "ON"}:
            self.state["closed"] = True
        elif action in {"open", "off", "OFF"}:
            self.state["closed"] = False
        elif action == "toggle":
            self.state["closed"] = not self.state.get("closed", False)
        return dict(self.state)


class ServoActuator(VirtualActuator):
    component_id = "servo"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.state.setdefault("angle_deg", 90)

    def _apply_command(self, action: str, value: Any) -> dict[str, Any]:
        if action in {"angle", "position", "write"}:
            self.state["angle_deg"] = max(0, min(180, int(value or 90)))
        elif action == "sweep":
            current = int(self.state.get("angle_deg", 90))
            self.state["angle_deg"] = 180 - current if current < 90 else 0
        return dict(self.state)


ACTUATOR_BEHAVIORS: dict[str, type[VirtualActuator]] = {
    "led": LEDActuator,
    "relay": RelayActuator,
    "servo": ServoActuator,
}
