"""Simulation behavior base + registry for Component Engine v2."""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from typing import Any, Optional


class BaseBehavior(ABC):
    """Per-tick simulation behavior for a component instance."""

    name: str = "base"

    def __init__(self, component_id: str, instance_id: str = "", params: Optional[dict[str, Any]] = None) -> None:
        self.component_id = component_id
        self.instance_id = instance_id or component_id
        self.params = dict(params or {})
        self.state: dict[str, Any] = {}

    @abstractmethod
    def tick(self, t_s: float, inputs: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        """Advance simulation; return signal dict."""

    def apply_input(self, signal: dict[str, Any]) -> None:
        self.state.update(signal)


class TemperatureSensorBehavior(BaseBehavior):
    name = "temperature_sensor"

    def tick(self, t_s: float, inputs: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        base_t = float(self.params.get("base_temp", 22.0))
        base_h = float(self.params.get("base_humidity", 55.0))
        temperature = round(base_t + 3.0 * math.sin(t_s / 8.0), 2)
        humidity = round(base_h + 8.0 * math.cos(t_s / 12.0), 1)
        out = {"temperature": temperature, "humidity": humidity, "temperature_c": temperature, "humidity_pct": humidity}
        self.state = out
        return out


class DigitalOutputBehavior(BaseBehavior):
    name = "digital_output"

    def tick(self, t_s: float, inputs: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        inputs = inputs or {}
        level = inputs.get("gpio", inputs.get("level", self.state.get("gpio", 0)))
        if isinstance(level, str):
            on = level.upper() in ("HIGH", "1", "ON", "TRUE")
        else:
            on = bool(level) and float(level) > 0.5
        pwm = float(inputs.get("pwm", self.state.get("pwm", 1.0 if on else 0.0)))
        out = {
            "on": on or pwm > 0.05,
            "gpio": 1 if on or pwm > 0.05 else 0,
            "pwm": pwm,
            "brightness": int(max(0, min(255, pwm * 255))),
        }
        self.state = out
        return out


class ServoMotorBehavior(BaseBehavior):
    name = "servo_motor"

    def tick(self, t_s: float, inputs: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        inputs = inputs or {}
        if "angle" in inputs or "angle_deg" in inputs:
            angle = float(inputs.get("angle_deg", inputs.get("angle", 90)))
        else:
            angle = 90.0 + 45.0 * math.sin(t_s / 3.0)
        angle = max(0.0, min(180.0, angle))
        out = {"angle": angle, "angle_deg": int(angle)}
        self.state = out
        return out


class DisplayBehavior(BaseBehavior):
    name = "display"

    def tick(self, t_s: float, inputs: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        inputs = inputs or {}
        text = str(inputs.get("display_text", self.state.get("display_text", f"t={t_s:.1f}s")))
        out = {"display_text": text, "active": True}
        self.state = out
        return out


class UltrasonicBehavior(BaseBehavior):
    name = "ultrasonic"

    def tick(self, t_s: float, inputs: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        distance = round(30 + 20 * abs(math.sin(t_s / 5.0)), 1)
        out = {"distance_cm": distance}
        self.state = out
        return out


class MotionSensorBehavior(BaseBehavior):
    name = "motion_sensor"

    def tick(self, t_s: float, inputs: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        motion = (int(t_s) // 3) % 2 == 0
        out = {"motion": motion, "motion_detected": motion, "gpio": 1 if motion else 0}
        self.state = out
        return out


class AnalogSensorBehavior(BaseBehavior):
    name = "analog_sensor"

    def tick(self, t_s: float, inputs: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        adc = int(512 + 200 * math.sin(t_s))
        out = {"adc": adc, "voltage": round(adc / 1023 * 3.3, 2)}
        self.state = out
        return out


class RelayBehavior(BaseBehavior):
    name = "relay"

    def tick(self, t_s: float, inputs: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        inputs = inputs or {}
        closed = bool(inputs.get("closed", inputs.get("active", self.state.get("closed", False))))
        out = {"closed": closed, "active": closed, "gpio": 1 if closed else 0}
        self.state = out
        return out


class McuBehavior(BaseBehavior):
    name = "mcu"

    def tick(self, t_s: float, inputs: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        out = {
            "power_on": True,
            "uptime_ms": int(t_s * 1000),
            "gpio": {"D2": int((t_s * 2) % 2), "D4": 1, "D13": 1},
        }
        self.state = out
        return out


_BEHAVIOR_CLASSES: dict[str, type[BaseBehavior]] = {
    TemperatureSensorBehavior.name: TemperatureSensorBehavior,
    DigitalOutputBehavior.name: DigitalOutputBehavior,
    ServoMotorBehavior.name: ServoMotorBehavior,
    DisplayBehavior.name: DisplayBehavior,
    UltrasonicBehavior.name: UltrasonicBehavior,
    MotionSensorBehavior.name: MotionSensorBehavior,
    AnalogSensorBehavior.name: AnalogSensorBehavior,
    RelayBehavior.name: RelayBehavior,
    McuBehavior.name: McuBehavior,
    # aliases
    "led": DigitalOutputBehavior,
    "rgb_led": DigitalOutputBehavior,
    "buzzer": DigitalOutputBehavior,
    "servo": ServoMotorBehavior,
    "temperature_humidity": TemperatureSensorBehavior,
    "dht": TemperatureSensorBehavior,
    "hc_sr04": UltrasonicBehavior,
    "pir": MotionSensorBehavior,
    "mq2": AnalogSensorBehavior,
    "soil_moisture": AnalogSensorBehavior,
    "esp32": McuBehavior,
    "arduino": McuBehavior,
}


class BehaviorRegistry:
    def __init__(self) -> None:
        self._classes = dict(_BEHAVIOR_CLASSES)

    def register(self, name: str, cls: type[BaseBehavior]) -> None:
        self._classes[name] = cls

    def create(
        self,
        behavior_name: str,
        *,
        component_id: str,
        instance_id: str = "",
        params: Optional[dict[str, Any]] = None,
    ) -> BaseBehavior:
        key = (behavior_name or "").strip().lower().replace("-", "_")
        cls = self._classes.get(key) or self._classes.get(behavior_name) or DigitalOutputBehavior
        return cls(component_id=component_id, instance_id=instance_id, params=params)

    def known(self) -> list[str]:
        return sorted(self._classes.keys())


default_behavior_registry = BehaviorRegistry()
