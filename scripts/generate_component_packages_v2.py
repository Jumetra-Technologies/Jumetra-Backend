"""Generate data/component_packages/* for Component Engine v2."""

from __future__ import annotations

import json
from pathlib import Path


def pin(pid, name, typ, x, y, voltage=3.3, direction="BIDIRECTIONAL", **kw):
    return {
        "id": pid,
        "name": name,
        "type": typ,
        "direction": direction,
        "voltage": voltage,
        "position": {"x": x, "y": y},
        **kw,
    }


def svg_box(title: str, w: int, h: int, fill: str = "#1E293B") -> str:
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">
  <rect x="4" y="4" width="{w-8}" height="{h-8}" rx="8" fill="{fill}" stroke="#64748B" stroke-width="2"/>
  <text x="{w/2}" y="{h/2+4}" text-anchor="middle" fill="#E2E8F0" font-family="monospace" font-size="12">{title}</text>
</svg>
'''


def package(root: Path, cid: str, manifest: dict, title: str | None = None, fill: str = "#1E293B"):
    d = root / cid
    d.mkdir(parents=True, exist_ok=True)
    visual = manifest.setdefault("visual", {})
    w = int(visual.get("width", 140))
    h = int(visual.get("height", 100))
    visual.setdefault("renderer", "renderer.svg")
    (d / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (d / "renderer.svg").write_text(svg_box(title or manifest["name"][:16], w, h, fill), encoding="utf-8")
    (d / "datasheet.md").write_text(
        f"# {manifest['name']}\n\nManufacturer: {manifest.get('manufacturer', 'Generic')}\n\n"
        f"Category: {manifest.get('category')}\n\n"
        f"{manifest.get('description') or manifest['name']}\n",
        encoding="utf-8",
    )
    if manifest.get("category") == "mcu":
        (d / "firmware.json").write_text(
            json.dumps({"board": cid, "fqbn": "", "upload_protocol": "serial"}, indent=2),
            encoding="utf-8",
        )
    if manifest.get("simulation", {}).get("behavior"):
        (d / "simulation.py").write_text(
            f'# Behavior: {manifest["simulation"]["behavior"]}\nBEHAVIOR = "{manifest["simulation"]["behavior"]}"\n',
            encoding="utf-8",
        )


def main() -> None:
    root = Path(__file__).resolve().parents[1] / "data" / "component_packages"
    root.mkdir(parents=True, exist_ok=True)

    packages = [
        (
            "esp32",
            {
                "id": "esp32",
                "name": "ESP32 DevKit",
                "category": "mcu",
                "manufacturer": "Espressif",
                "description": "Dual-core WiFi/BT MCU",
                "visual": {"renderer": "renderer.svg", "width": 300, "height": 150},
                "pins": [
                    pin("3v3", "3V3", "POWER", 10, 20, 3.3, "POWER"),
                    pin("gnd", "GND", "GROUND", 10, 130, 0, "GROUND"),
                    pin("d2", "GPIO2", "GPIO", 290, 40),
                    pin("d4", "GPIO4", "GPIO", 290, 70),
                    pin("d5", "GPIO5", "GPIO", 290, 100),
                    pin("sda", "SDA", "I2C_SDA", 200, 140),
                    pin("scl", "SCL", "I2C_SCL", 230, 140),
                    pin("tx", "TX", "UART_TX", 150, 140),
                    pin("rx", "RX", "UART_RX", 170, 140),
                ],
                "interfaces": ["GPIO", "PWM", "UART", "I2C", "SPI", "WiFi"],
                "simulation": {"behavior": "mcu"},
                "hardware": {"physical_supported": True, "transports": ["serial"]},
                "keywords": ["esp", "esp32", "wifi", "mcu"],
                "aliases": ["esp 32"],
            },
            "#0F172A",
        ),
        (
            "arduino-uno",
            {
                "id": "arduino-uno",
                "name": "Arduino Uno",
                "category": "mcu",
                "manufacturer": "Arduino",
                "description": "ATmega328P development board",
                "visual": {"renderer": "renderer.svg", "width": 280, "height": 200},
                "pins": [
                    pin("5v", "5V", "POWER", 10, 30, 5, "POWER"),
                    pin("3v3", "3V3", "POWER", 10, 60, 3.3, "POWER"),
                    pin("gnd", "GND", "GROUND", 10, 90, 0, "GROUND"),
                    pin("d13", "D13", "GPIO", 270, 40, 5),
                    pin("d2", "D2", "GPIO", 270, 80, 5),
                    pin("a0", "A0", "ADC", 10, 140, 5, "INPUT"),
                    pin("sda", "SDA", "I2C_SDA", 120, 190, 5),
                    pin("scl", "SCL", "I2C_SCL", 150, 190, 5),
                ],
                "interfaces": ["GPIO", "PWM", "UART", "I2C", "SPI"],
                "simulation": {"behavior": "mcu"},
                "hardware": {"physical_supported": True, "transports": ["serial"]},
                "keywords": ["arduino", "uno", "mcu"],
                "aliases": ["uno"],
            },
            "#00789D",
        ),
        (
            "arduino-mega",
            {
                "id": "arduino-mega",
                "name": "Arduino Mega",
                "category": "mcu",
                "manufacturer": "Arduino",
                "description": "ATmega2560 board",
                "visual": {"renderer": "renderer.svg", "width": 320, "height": 180},
                "pins": [
                    pin("5v", "5V", "POWER", 10, 30, 5, "POWER"),
                    pin("gnd", "GND", "GROUND", 10, 60, 0, "GROUND"),
                    pin("d2", "D2", "GPIO", 310, 40, 5),
                    pin("d13", "D13", "GPIO", 310, 80, 5),
                ],
                "interfaces": ["GPIO", "UART", "I2C", "SPI"],
                "simulation": {"behavior": "mcu"},
                "hardware": {"physical_supported": True},
                "keywords": ["arduino", "mega"],
                "aliases": ["mega"],
            },
            "#00789D",
        ),
        (
            "stm32",
            {
                "id": "stm32",
                "name": "STM32 Blue Pill",
                "category": "mcu",
                "manufacturer": "STMicroelectronics",
                "description": "STM32F103C8T6",
                "visual": {"renderer": "renderer.svg", "width": 220, "height": 120},
                "pins": [
                    pin("3v3", "3V3", "POWER", 10, 20, 3.3, "POWER"),
                    pin("gnd", "GND", "GROUND", 10, 100, 0, "GROUND"),
                    pin("b11", "PB11", "GPIO", 210, 40),
                    pin("a5", "PA5", "SPI_CLK", 210, 80),
                ],
                "interfaces": ["GPIO", "UART", "I2C", "SPI"],
                "simulation": {"behavior": "mcu"},
                "hardware": {"physical_supported": True},
                "keywords": ["stm32", "bluepill"],
                "aliases": ["blue pill"],
            },
            "#2563EB",
        ),
        (
            "raspberry-pi-pico",
            {
                "id": "raspberry-pi-pico",
                "name": "Raspberry Pi Pico",
                "category": "mcu",
                "manufacturer": "Raspberry Pi",
                "description": "RP2040 board",
                "visual": {"renderer": "renderer.svg", "width": 260, "height": 110},
                "pins": [
                    pin("gp0", "GP0", "GPIO", 10, 30),
                    pin("gp1", "GP1", "GPIO", 10, 55),
                    pin("3v3", "3V3", "POWER", 130, 100, 3.3, "POWER"),
                    pin("gnd", "GND", "GROUND", 10, 90, 0, "GROUND"),
                ],
                "interfaces": ["GPIO", "PWM", "UART", "I2C", "SPI"],
                "simulation": {"behavior": "mcu"},
                "hardware": {"physical_supported": True},
                "keywords": ["pico", "rp2040"],
                "aliases": ["pico"],
            },
            "#059669",
        ),
        (
            "raspberry-pi-4",
            {
                "id": "raspberry-pi-4",
                "name": "Raspberry Pi 4",
                "category": "mcu",
                "manufacturer": "Raspberry Pi",
                "description": "Linux SBC with WiFi",
                "visual": {"renderer": "renderer.svg", "width": 280, "height": 160},
                "pins": [
                    pin("5v", "5V", "POWER", 10, 20, 5, "POWER"),
                    pin("gnd", "GND", "GROUND", 10, 50, 0, "GROUND"),
                    pin("gpio2", "GPIO2", "I2C_SDA", 10, 90),
                    pin("gpio3", "GPIO3", "I2C_SCL", 10, 120),
                ],
                "interfaces": ["GPIO", "I2C", "SPI", "UART", "WiFi"],
                "simulation": {"behavior": "mcu"},
                "hardware": {"physical_supported": True, "transports": ["ssh"]},
                "keywords": ["raspberry", "pi", "wifi"],
                "aliases": ["rpi4"],
            },
            "#C51A4A",
        ),
        (
            "dht22",
            {
                "id": "dht22",
                "name": "DHT22 Temperature Humidity Sensor",
                "category": "sensor",
                "manufacturer": "Aosong",
                "description": "Digital temperature and humidity sensor",
                "visual": {"renderer": "renderer.svg", "width": 140, "height": 100},
                "pins": [
                    pin("vcc", "VCC", "POWER", 40, 0, 3.3, "POWER"),
                    pin("data", "DATA", "GPIO", 140, 50),
                    pin("gnd", "GND", "GROUND", 40, 100, 0, "GROUND"),
                ],
                "interfaces": ["GPIO"],
                "simulation": {"behavior": "temperature_sensor"},
                "hardware": {"physical_supported": True},
                "keywords": ["temperature", "humidity", "dht", "sensor"],
                "aliases": ["am2302", "dht 22"],
            },
            "#2563EB",
        ),
        (
            "dht11",
            {
                "id": "dht11",
                "name": "DHT11 Temperature Humidity Sensor",
                "category": "sensor",
                "manufacturer": "Aosong",
                "description": "Basic temperature humidity sensor",
                "visual": {"renderer": "renderer.svg", "width": 140, "height": 100},
                "pins": [
                    pin("vcc", "VCC", "POWER", 40, 0, 3.3, "POWER"),
                    pin("data", "DATA", "GPIO", 140, 50),
                    pin("gnd", "GND", "GROUND", 40, 100, 0, "GROUND"),
                ],
                "interfaces": ["GPIO"],
                "simulation": {"behavior": "temperature_sensor"},
                "hardware": {"physical_supported": True},
                "keywords": ["temperature", "humidity", "dht"],
                "aliases": ["dht 11"],
            },
            "#3B82F6",
        ),
        (
            "hc-sr04",
            {
                "id": "hc-sr04",
                "name": "HC-SR04 Ultrasonic",
                "category": "sensor",
                "manufacturer": "Generic",
                "description": "Ultrasonic distance sensor",
                "visual": {"renderer": "renderer.svg", "width": 120, "height": 70},
                "pins": [
                    pin("vcc", "VCC", "POWER", 20, 65, 5, "POWER"),
                    pin("trig", "TRIG", "GPIO", 45, 65, 5, "OUTPUT"),
                    pin("echo", "ECHO", "GPIO", 70, 65, 5, "INPUT"),
                    pin("gnd", "GND", "GROUND", 95, 65, 0, "GROUND"),
                ],
                "interfaces": ["GPIO"],
                "simulation": {"behavior": "ultrasonic"},
                "hardware": {"physical_supported": True},
                "keywords": ["ultrasonic", "distance"],
                "aliases": ["hcsr04"],
            },
            "#1E293B",
        ),
        (
            "pir",
            {
                "id": "pir",
                "name": "PIR Motion Sensor",
                "category": "sensor",
                "manufacturer": "Generic",
                "description": "Passive infrared motion detector",
                "visual": {"renderer": "renderer.svg", "width": 80, "height": 100},
                "pins": [
                    pin("vcc", "VCC", "POWER", 15, 95, 5, "POWER"),
                    pin("out", "OUT", "GPIO", 40, 95, 5, "OUTPUT"),
                    pin("gnd", "GND", "GROUND", 65, 95, 0, "GROUND"),
                ],
                "interfaces": ["GPIO"],
                "simulation": {"behavior": "motion_sensor"},
                "hardware": {"physical_supported": True},
                "keywords": ["motion", "pir"],
                "aliases": ["motion"],
            },
            "#334155",
        ),
        (
            "mq2",
            {
                "id": "mq2",
                "name": "MQ2 Gas Sensor",
                "category": "sensor",
                "manufacturer": "Winsen",
                "description": "Combustible gas sensor",
                "visual": {"renderer": "renderer.svg", "width": 100, "height": 90},
                "pins": [
                    pin("vcc", "VCC", "POWER", 20, 85, 5, "POWER"),
                    pin("aout", "AOUT", "ADC", 50, 85, 5, "INPUT"),
                    pin("gnd", "GND", "GROUND", 80, 85, 0, "GROUND"),
                ],
                "interfaces": ["ADC", "GPIO"],
                "simulation": {"behavior": "analog_sensor"},
                "hardware": {"physical_supported": True},
                "keywords": ["gas", "smoke", "mq2"],
                "aliases": ["mq-2"],
            },
            "#78350F",
        ),
        (
            "soil-moisture",
            {
                "id": "soil-moisture",
                "name": "Soil Moisture Sensor",
                "category": "sensor",
                "manufacturer": "Generic",
                "description": "Capacitive soil moisture probe",
                "visual": {"renderer": "renderer.svg", "width": 90, "height": 120},
                "pins": [
                    pin("vcc", "VCC", "POWER", 20, 10, 3.3, "POWER"),
                    pin("aout", "AOUT", "ADC", 45, 10, 3.3, "INPUT"),
                    pin("gnd", "GND", "GROUND", 70, 10, 0, "GROUND"),
                ],
                "interfaces": ["ADC"],
                "simulation": {"behavior": "analog_sensor"},
                "hardware": {"physical_supported": True},
                "keywords": ["soil", "moisture", "agriculture"],
                "aliases": ["soil"],
            },
            "#166534",
        ),
        (
            "led",
            {
                "id": "led",
                "name": "LED",
                "category": "actuator",
                "manufacturer": "Generic",
                "description": "Discrete LED indicator",
                "visual": {"renderer": "renderer.svg", "width": 60, "height": 80},
                "pins": [
                    pin("a", "Anode", "GPIO", 30, 5, 3.3, "INPUT"),
                    pin("c", "Cathode", "GROUND", 30, 75, 0, "GROUND"),
                ],
                "interfaces": ["GPIO", "PWM"],
                "simulation": {"behavior": "digital_output"},
                "hardware": {"physical_supported": True},
                "keywords": ["led", "light"],
                "aliases": [],
            },
            "#EF4444",
        ),
        (
            "rgb-led",
            {
                "id": "rgb-led",
                "name": "RGB LED",
                "category": "actuator",
                "manufacturer": "Generic",
                "description": "Common-cathode RGB LED",
                "visual": {"renderer": "renderer.svg", "width": 70, "height": 80},
                "pins": [
                    pin("r", "R", "PWM", 15, 5, 3.3, "INPUT"),
                    pin("g", "G", "PWM", 35, 5, 3.3, "INPUT"),
                    pin("b", "B", "PWM", 55, 5, 3.3, "INPUT"),
                    pin("gnd", "GND", "GROUND", 35, 75, 0, "GROUND"),
                ],
                "interfaces": ["PWM", "GPIO"],
                "simulation": {"behavior": "digital_output"},
                "hardware": {"physical_supported": True},
                "keywords": ["rgb", "led"],
                "aliases": ["rgb"],
            },
            "#A855F7",
        ),
        (
            "relay",
            {
                "id": "relay",
                "name": "Relay Module",
                "category": "actuator",
                "manufacturer": "Generic",
                "description": "Single-channel relay",
                "visual": {"renderer": "renderer.svg", "width": 80, "height": 100},
                "pins": [
                    pin("vcc", "VCC", "POWER", 15, 5, 5, "POWER"),
                    pin("gnd", "GND", "GROUND", 65, 5, 0, "GROUND"),
                    pin("in", "IN", "GPIO", 40, 5, 5, "INPUT"),
                ],
                "interfaces": ["GPIO"],
                "simulation": {"behavior": "relay"},
                "hardware": {"physical_supported": True},
                "keywords": ["relay", "switch"],
                "aliases": [],
            },
            "#1E293B",
        ),
        (
            "servo",
            {
                "id": "servo",
                "name": "Servo Motor",
                "category": "actuator",
                "manufacturer": "Generic",
                "description": "Hobby servo",
                "visual": {"renderer": "renderer.svg", "width": 90, "height": 110},
                "pins": [
                    pin("vcc", "VCC", "POWER", 20, 100, 5, "POWER"),
                    pin("gnd", "GND", "GROUND", 45, 100, 0, "GROUND"),
                    pin("sig", "SIG", "PWM", 70, 100, 5, "INPUT"),
                ],
                "interfaces": ["PWM"],
                "simulation": {"behavior": "servo_motor"},
                "hardware": {"physical_supported": True},
                "keywords": ["servo", "motor"],
                "aliases": ["sg90"],
            },
            "#374151",
        ),
        (
            "buzzer",
            {
                "id": "buzzer",
                "name": "Buzzer",
                "category": "actuator",
                "manufacturer": "Generic",
                "description": "Active/passive buzzer",
                "visual": {"renderer": "renderer.svg", "width": 60, "height": 70},
                "pins": [
                    pin("pos", "+", "GPIO", 20, 65, 5, "INPUT"),
                    pin("neg", "-", "GROUND", 40, 65, 0, "GROUND"),
                ],
                "interfaces": ["GPIO", "PWM"],
                "simulation": {"behavior": "digital_output"},
                "hardware": {"physical_supported": True},
                "keywords": ["buzzer", "sound"],
                "aliases": [],
            },
            "#374151",
        ),
    ]

    for cid, manifest, fill in packages:
        package(root, cid, manifest, fill=fill)

    print(f"wrote {len(packages)} packages -> {root}")


if __name__ == "__main__":
    main()
