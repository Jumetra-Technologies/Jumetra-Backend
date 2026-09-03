"""Extended component catalog for the engineering workspace explorer.

Layout mirrors the product Explorer:

  Arduino · ESP32 · STM32 · Pico
  Sensors · Displays · Communication
  AI Modules · Robotics · Marketplace

Enrichment: JSON catalog under data/components/ via ComponentSearchEngine.
"""

from __future__ import annotations

from typing import Any, Optional

from engine.components.search import ComponentSearchEngine, SearchFilters


# Ordered for the left Explorer UI
EXPLORER_ORDER: list[str] = [
    "arduino",
    "esp32",
    "stm32",
    "pico",
    "sensors",
    "actuators",
    "displays",
    "communication",
    "ai-modules",
    "robotics",
    "marketplace",
]

CATEGORY_LABELS: dict[str, str] = {
    "arduino": "Arduino",
    "esp32": "ESP32",
    "stm32": "STM32",
    "pico": "Pico",
    "sensors": "Sensors",
    "actuators": "Actuators",
    "displays": "Displays",
    "communication": "Communication",
    "ai-modules": "AI Modules",
    "robotics": "Robotics",
    "marketplace": "Marketplace",
}

EXPLORER_CATALOG: dict[str, list[dict[str, Any]]] = {
    "arduino": [
        {"component_id": "arduino-uno", "name": "Arduino Uno", "pins": 20, "voltage_v": 5.0, "protocols": ["gpio", "adc", "pwm", "uart", "i2c", "spi", "digital"]},
        {"component_id": "arduino-mega", "name": "Arduino Mega", "pins": 70, "voltage_v": 5.0, "protocols": ["gpio", "adc", "pwm", "uart", "i2c", "spi", "digital"]},
        {"component_id": "arduino-nano", "name": "Arduino Nano", "pins": 22, "voltage_v": 5.0, "protocols": ["gpio", "adc", "pwm", "uart", "i2c", "spi", "digital"]},
        {"component_id": "teensy", "name": "Teensy", "pins": 34, "voltage_v": 3.3, "protocols": ["gpio", "adc", "pwm", "uart", "i2c", "spi", "digital"]},
        {"component_id": "microbit", "name": "BBC Microbit", "pins": 25, "voltage_v": 3.3, "protocols": ["gpio", "i2c", "spi", "digital"]},
    ],
    "esp32": [
        {"component_id": "esp32", "name": "ESP32", "pins": 34, "voltage_v": 3.3, "protocols": ["gpio", "adc", "pwm", "uart", "i2c", "spi", "wifi", "bluetooth", "digital"]},
        {"component_id": "esp8266", "name": "ESP8266", "pins": 17, "voltage_v": 3.3, "protocols": ["gpio", "adc", "pwm", "uart", "i2c", "wifi", "digital"]},
        {"component_id": "esp32-s3", "name": "ESP32-S3", "pins": 45, "voltage_v": 3.3, "protocols": ["gpio", "adc", "pwm", "uart", "i2c", "spi", "wifi", "bluetooth", "digital"]},
    ],
    "stm32": [
        {"component_id": "stm32", "name": "STM32 Nucleo", "pins": 48, "voltage_v": 3.3, "protocols": ["gpio", "adc", "pwm", "uart", "i2c", "spi", "can", "digital"]},
        {"component_id": "stm32-f4", "name": "STM32 F4", "pins": 64, "voltage_v": 3.3, "protocols": ["gpio", "adc", "pwm", "uart", "i2c", "spi", "can", "digital"]},
    ],
    "pico": [
        {"component_id": "raspberry-pi-pico", "name": "Raspberry Pi Pico", "pins": 26, "voltage_v": 3.3, "protocols": ["gpio", "adc", "pwm", "uart", "i2c", "spi", "digital"]},
        {"component_id": "pico-w", "name": "Raspberry Pi Pico W", "pins": 26, "voltage_v": 3.3, "protocols": ["gpio", "adc", "pwm", "uart", "i2c", "spi", "wifi", "digital"]},
        {"component_id": "raspberry-pi-4", "name": "Raspberry Pi 4", "pins": 40, "voltage_v": 3.3, "protocols": ["gpio", "pwm", "uart", "i2c", "spi", "wifi", "bluetooth", "digital"]},
    ],
    "sensors": [
        {"component_id": "dht11", "name": "DHT11", "voltage_v": 3.3, "protocols": ["digital"], "params": {"noise": 0.1, "sampling_interval_ms": 1000}},
        {"component_id": "dht22", "name": "DHT22", "voltage_v": 3.3, "protocols": ["digital"], "params": {"noise": 0.05, "sampling_interval_ms": 500}},
        {"component_id": "am2302", "name": "AM2302", "voltage_v": 3.3, "protocols": ["digital"]},
        {"component_id": "bmp280", "name": "BMP280", "voltage_v": 3.3, "protocols": ["i2c", "spi"]},
        {"component_id": "bme280", "name": "BME280", "voltage_v": 3.3, "protocols": ["i2c", "spi"]},
        {"component_id": "mpu6050", "name": "MPU6050", "voltage_v": 3.3, "protocols": ["i2c"]},
        {"component_id": "hc-sr04", "name": "HC-SR04", "voltage_v": 5.0, "protocols": ["digital"]},
        {"component_id": "pir", "name": "PIR", "voltage_v": 5.0, "protocols": ["digital"]},
        {"component_id": "mq2", "name": "MQ2", "voltage_v": 5.0, "protocols": ["analog", "digital"]},
        {"component_id": "ldr", "name": "LDR", "voltage_v": 3.3, "protocols": ["analog"]},
        {"component_id": "soil-moisture", "name": "Soil Moisture", "voltage_v": 3.3, "protocols": ["analog"]},
        {"component_id": "ds18b20", "name": "DS18B20", "voltage_v": 3.3, "protocols": ["digital", "onewire"]},
        {"component_id": "water-level", "name": "Water Level", "voltage_v": 3.3, "protocols": ["analog"]},
        {"component_id": "rain-sensor", "name": "Rain Sensor", "voltage_v": 5.0, "protocols": ["analog", "digital"]},
        {"component_id": "flame-sensor", "name": "Flame Sensor", "voltage_v": 5.0, "protocols": ["digital"]},
        {"component_id": "gas-sensor", "name": "Gas Sensor", "voltage_v": 5.0, "protocols": ["analog"]},
        {"component_id": "gps", "name": "GPS", "voltage_v": 3.3, "protocols": ["uart"]},
        {"component_id": "rfid", "name": "RFID", "voltage_v": 3.3, "protocols": ["spi"]},
        {"component_id": "camera", "name": "Camera", "voltage_v": 3.3, "protocols": ["i2c", "spi"]},
    ],
    "actuators": [
        {"component_id": "led", "name": "LED", "voltage_v": 3.3, "protocols": ["digital", "pwm"]},
        {"component_id": "rgb-led", "name": "RGB LED", "voltage_v": 3.3, "protocols": ["pwm"]},
        {"component_id": "relay", "name": "Relay", "voltage_v": 5.0, "protocols": ["digital"]},
        {"component_id": "buzzer", "name": "Buzzer", "voltage_v": 5.0, "protocols": ["digital", "pwm"]},
        {"component_id": "servo", "name": "Servo", "voltage_v": 5.0, "protocols": ["pwm"]},
        {"component_id": "dc-motor", "name": "DC Motor", "voltage_v": 5.0, "protocols": ["pwm"]},
        {"component_id": "stepper-motor", "name": "Stepper Motor", "voltage_v": 5.0, "protocols": ["digital"]},
        {"component_id": "push-button", "name": "Push Button", "voltage_v": 3.3, "protocols": ["digital"]},
        {"component_id": "fan", "name": "Fan", "voltage_v": 5.0, "protocols": ["digital", "pwm"]},
    ],
    "displays": [
        {"component_id": "lcd", "name": "LCD 16x2", "voltage_v": 5.0, "protocols": ["i2c", "digital"]},
        {"component_id": "lcd-16x2", "name": "LCD 16x2 (I2C)", "voltage_v": 5.0, "protocols": ["i2c", "digital"]},
        {"component_id": "oled", "name": "OLED SSD1306", "voltage_v": 3.3, "protocols": ["i2c"]},
        {"component_id": "oled-ssd1306", "name": "OLED SSD1306", "voltage_v": 3.3, "protocols": ["i2c", "spi"]},
        {"component_id": "tft", "name": "TFT Display", "voltage_v": 3.3, "protocols": ["spi"]},
        {"component_id": "tft-display", "name": "TFT Display", "voltage_v": 3.3, "protocols": ["spi"]},
        {"component_id": "led-matrix", "name": "LED Matrix", "voltage_v": 5.0, "protocols": ["spi"]},
    ],
    "communication": [
        {"component_id": "bluetooth", "name": "Bluetooth Module", "voltage_v": 3.3, "protocols": ["uart"]},
        {"component_id": "hc-05", "name": "Bluetooth HC05", "voltage_v": 3.3, "protocols": ["uart"]},
        {"component_id": "wifi-module", "name": "WiFi Module", "voltage_v": 3.3, "protocols": ["uart", "spi"]},
        {"component_id": "lora", "name": "LoRa", "voltage_v": 3.3, "protocols": ["spi"]},
        {"component_id": "nrf24l01", "name": "NRF24L01", "voltage_v": 3.3, "protocols": ["spi"]},
        {"component_id": "can", "name": "CAN Transceiver", "voltage_v": 5.0, "protocols": ["can"]},
        {"component_id": "rs485", "name": "RS485", "voltage_v": 5.0, "protocols": ["uart"]},
        {"component_id": "mqtt-bridge", "name": "MQTT Bridge", "voltage_v": 3.3, "protocols": ["wifi", "uart"]},
    ],
    "ai-modules": [
        {"component_id": "ai-vision", "name": "AI Vision Module", "voltage_v": 3.3, "protocols": ["spi", "uart"], "params": {"model": "edge-detect"}},
        {"component_id": "ai-voice", "name": "AI Voice Module", "voltage_v": 3.3, "protocols": ["uart", "i2s"], "params": {"model": "wake-word"}},
        {"component_id": "edge-tpu", "name": "Edge TPU", "voltage_v": 3.3, "protocols": ["spi", "i2c"]},
        {"component_id": "ml-sensor-fusion", "name": "ML Sensor Fusion", "voltage_v": 3.3, "protocols": ["i2c"], "params": {"window_ms": 200}},
    ],
    "robotics": [
        {"component_id": "stepper", "name": "Stepper", "voltage_v": 5.0, "protocols": ["digital"]},
        {"component_id": "motor-driver", "name": "Motor Driver (L298N)", "voltage_v": 5.0, "protocols": ["digital", "pwm"]},
        {"component_id": "robot-arm", "name": "Robot Arm Kit", "voltage_v": 5.0, "protocols": ["pwm"]},
        {"component_id": "breadboard", "name": "Breadboard", "voltage_v": 0, "protocols": ["digital"]},
        {"component_id": "resistor", "name": "Resistor", "voltage_v": 0, "protocols": ["digital"]},
        {"component_id": "capacitor", "name": "Capacitor", "voltage_v": 0, "protocols": ["digital"]},
        {"component_id": "potentiometer", "name": "Potentiometer", "voltage_v": 3.3, "protocols": ["analog"]},
        {"component_id": "jumper-wire", "name": "Jumper Wire", "voltage_v": 0, "protocols": ["digital"]},
    ],
    "marketplace": [
        {"component_id": "mkt-custom-sensor", "name": "Custom Sensor Pack", "voltage_v": 3.3, "protocols": ["digital", "analog"], "marketplace": True},
        {"component_id": "mkt-wokwi-adapter", "name": "Wokwi Adapter (plugin)", "voltage_v": 3.3, "protocols": ["simulator"], "marketplace": True},
        {"component_id": "mkt-proteus-adapter", "name": "Proteus Adapter (plugin)", "voltage_v": 3.3, "protocols": ["simulator"], "marketplace": True},
        {"component_id": "mkt-firmware-bundle", "name": "Firmware Bundle", "voltage_v": 3.3, "protocols": ["uart"], "marketplace": True},
    ],
}

_search_engine: Optional[ComponentSearchEngine] = None


def _engine() -> ComponentSearchEngine:
    global _search_engine
    if _search_engine is None:
        _search_engine = ComponentSearchEngine()
    return _search_engine


def list_categories() -> list[str]:
    return list(EXPLORER_ORDER)


def _merge_item(base: dict[str, Any], enriched: dict[str, Any]) -> dict[str, Any]:
    merged = {**base, **{k: v for k, v in enriched.items() if v not in (None, "", [], {})}}
    if base.get("category"):
        merged["category"] = base["category"]
    return merged


def search_catalog(
    query: str = "",
    category: str | None = None,
    *,
    interface: str | None = None,
    interfaces: list[str] | None = None,
    voltage: float | None = None,
    voltages: list[float] | None = None,
    controller_id: str | None = None,
) -> list[dict[str, Any]]:
    q = query.strip().lower()
    filters = SearchFilters(
        category=None,
        categories=[],
        interface=interface,
        interfaces=list(interfaces or []),
        voltage=voltage,
        voltages=list(voltages or []),
        controller_id=controller_id,
    )

    catalog_category = None
    if category in {"sensors", "sensor"}:
        catalog_category = "sensor"
    elif category in {"actuators", "actuator"}:
        catalog_category = "actuator"
    elif category in {"displays", "display"}:
        catalog_category = "display"
    elif category in {"communication"}:
        catalog_category = "communication"
    elif category in {"arduino", "esp32", "stm32", "pico"}:
        catalog_category = "mcu"

    if catalog_category:
        filters.category = catalog_category

    engine_hits = _engine().search(q, filters=filters, limit=200)
    by_id = {h["component_id"]: h for h in engine_hits}

    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    categories = [category] if category and category in EXPLORER_CATALOG else list(EXPLORER_ORDER)

    for cat in categories:
        for item in EXPLORER_CATALOG.get(cat, []):
            cid = item["component_id"]
            enriched = by_id.get(cid)
            row = {**item, "category": cat, "category_label": CATEGORY_LABELS.get(cat, cat)}
            if enriched:
                row = _merge_item(row, enriched)
                row["category"] = cat
            else:
                if q and q not in str(item.get("name", "")).lower() and q not in cid.lower():
                    protocols = " ".join(str(p) for p in (item.get("protocols") or []))
                    if q not in protocols:
                        continue
            if filters.interfaces or filters.interface:
                wanted = {i.upper() for i in filters.interfaces}
                if filters.interface:
                    wanted.add(filters.interface.upper())
                protocols = {str(p).upper() for p in (row.get("protocols") or row.get("interfaces") or [])}
                if "GPIO" in wanted:
                    wanted.add("DIGITAL")
                proto_lower = {p.lower() for p in protocols}
                if not (protocols & wanted) and not any(w.lower() in proto_lower for w in wanted):
                    continue
            if filters.voltages or filters.voltage is not None:
                volts = list(filters.voltages)
                if filters.voltage is not None:
                    volts.append(filters.voltage)
                vv = float(row.get("voltage_v", 3.3))
                if not any(
                    abs(vv - v) < 0.3 or (v == 3.3 and vv <= 3.4) or (v == 5.0 and vv >= 4.5) for v in volts
                ):
                    continue
            if filters.controller_id:
                controllers = [str(c).lower() for c in (row.get("compatible_controllers") or [])]
                cid_l = cid.lower()
                ctrl = filters.controller_id.lower()
                if controllers and ctrl not in controllers:
                    if ctrl not in cid_l and ctrl not in cat:
                        continue
            results.append(row)
            seen.add(cid)

    for hit in engine_hits:
        cid = hit["component_id"]
        if cid in seen:
            continue
        if category and category in EXPLORER_CATALOG:
            if hit.get("category") != category and hit.get("catalog_category") != catalog_category:
                continue
        results.append(
            {
                **hit,
                "category_label": CATEGORY_LABELS.get(str(hit.get("category")), str(hit.get("category"))),
            }
        )
        seen.add(cid)

    if q:
        results.sort(key=lambda r: (-float(r.get("score") or 0), str(r.get("name") or "")))
    return results


def get_component(component_id: str) -> dict[str, Any] | None:
    for cat in EXPLORER_ORDER:
        for item in EXPLORER_CATALOG.get(cat, []):
            if item["component_id"] == component_id:
                enriched = _engine().get(component_id)
                row = {**item, "category": cat, "category_label": CATEGORY_LABELS.get(cat, cat)}
                if enriched:
                    row = _merge_item(row, enriched)
                    row["category"] = cat
                return row
    enriched = _engine().get(component_id)
    if enriched:
        return {**enriched, "category_label": CATEGORY_LABELS.get(str(enriched.get("category")), "")}
    return None


def explorer_tree() -> list[dict[str, Any]]:
    """Return Explorer sections for the left sidebar tree."""
    return [
        {
            "id": cat,
            "label": CATEGORY_LABELS[cat],
            "items": [{**item, "category": cat} for item in EXPLORER_CATALOG[cat]],
        }
        for cat in EXPLORER_ORDER
    ]
