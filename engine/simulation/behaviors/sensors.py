"""Virtual sensor implementations."""

from __future__ import annotations

import math
from typing import Any

from .base import VirtualSensor


class DHT11Sensor(VirtualSensor):
    component_id = "dht11"

    def _generate_reading(self, sim_time_ms: int) -> dict[str, Any]:
        t = sim_time_ms / 1000.0
        return {
            "temperature_c": round(22.0 + 3.0 * math.sin(t / 10.0), 1),
            "humidity_pct": round(55.0 + 10.0 * math.cos(t / 15.0), 1),
            "unit": "dht11",
        }


class DHT22Sensor(VirtualSensor):
    component_id = "dht22"

    def _generate_reading(self, sim_time_ms: int) -> dict[str, Any]:
        t = sim_time_ms / 1000.0
        return {
            "temperature_c": round(21.5 + 2.5 * math.sin(t / 8.0), 2),
            "humidity_pct": round(50.0 + 8.0 * math.cos(t / 12.0), 2),
            "unit": "dht22",
        }


class HCSR04Sensor(VirtualSensor):
    component_id = "hc-sr04"

    def _generate_reading(self, sim_time_ms: int) -> dict[str, Any]:
        t = sim_time_ms / 1000.0
        distance_cm = round(30.0 + 20.0 * abs(math.sin(t / 5.0)), 1)
        return {"distance_cm": distance_cm, "unit": "hc-sr04"}


class PIRSensor(VirtualSensor):
    component_id = "pir"

    def _generate_reading(self, sim_time_ms: int) -> dict[str, Any]:
        motion = (sim_time_ms // 3000) % 2 == 0
        return {"motion_detected": motion, "unit": "pir"}


class SoilMoistureSensor(VirtualSensor):
    component_id = "soil-moisture"

    def _generate_reading(self, sim_time_ms: int) -> dict[str, Any]:
        t = sim_time_ms / 1000.0
        moisture = round(max(0.0, min(100.0, 60.0 - t * 0.5)), 1)
        return {"moisture_pct": moisture, "raw_adc": int(moisture * 10.23), "unit": "soil-moisture"}


SENSOR_BEHAVIORS: dict[str, type[VirtualSensor]] = {
    "dht11": DHT11Sensor,
    "dht22": DHT22Sensor,
    "hc-sr04": HCSR04Sensor,
    "pir": PIRSensor,
    "soil-moisture": SoilMoistureSensor,
}
