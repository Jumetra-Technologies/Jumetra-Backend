"""Canonical pin layouts for supported microcontroller boards."""

from __future__ import annotations

from typing import Any

from .pin_layout import HardwarePinDef


def _pin(
    name: str,
    number: int | str,
    pin_type: str,
    *,
    x: float,
    y: float,
    side: str,
    voltage: float = 3.3,
    supports_input: bool = True,
    supports_output: bool = True,
    interfaces: list[str] | None = None,
) -> HardwarePinDef:
    return HardwarePinDef(
        name=name,
        number=number,
        pin_type=pin_type,
        supports_input=supports_input,
        supports_output=supports_output,
        voltage=voltage,
        x=x,
        y=y,
        side=side,
        interfaces=interfaces or [pin_type.lower()],
    )


def esp32_devkit_v1_pins() -> list[HardwarePinDef]:
    left = [
        ("3V3", "3V3", "POWER", False, False),
        ("EN", "EN", "GPIO", True, False),
        ("VP", 36, "ADC", True, False),
        ("VN", 39, "ADC", True, False),
        ("D34", 34, "ADC", True, False),
        ("D35", 35, "ADC", True, False),
        ("D32", 32, "GPIO", True, True),
        ("D33", 33, "PWM", True, True),
        ("D25", 25, "DAC", True, True),
        ("D26", 26, "DAC", True, True),
        ("D27", 27, "GPIO", True, True),
        ("D14", 14, "SPI", True, True),
        ("D12", 12, "SPI", True, True),
        ("GND", "GND", "GROUND", False, False),
        ("D13", 13, "SPI", True, True),
    ]
    right = [
        ("D23", 23, "SPI", True, True),
        ("D22", 22, "I2C", True, True),
        ("TX", 1, "UART", False, True),
        ("RX", 3, "UART", True, False),
        ("D21", 21, "I2C", True, True),
        ("D19", 19, "SPI", True, True),
        ("D18", 18, "SPI", True, True),
        ("D5", 5, "GPIO", True, True),
        ("D17", 17, "UART", True, True),
        ("D16", 16, "UART", True, True),
        ("D4", 4, "GPIO", True, True),
        ("D2", 2, "GPIO", True, True),
        ("D15", 15, "GPIO", True, True),
        ("GND2", "GND", "GROUND", False, False),
        ("VIN", "VIN", "POWER", False, False),
    ]
    pins: list[HardwarePinDef] = []
    for i, (name, num, ptype, inp, out) in enumerate(left):
        y = 0.08 + i * (0.84 / max(len(left) - 1, 1))
        pins.append(_pin(name, num, ptype, x=0.02, y=y, side="left", supports_input=inp, supports_output=out))
    for i, (name, num, ptype, inp, out) in enumerate(right):
        y = 0.08 + i * (0.84 / max(len(right) - 1, 1))
        pins.append(_pin(name, num, ptype, x=0.98, y=y, side="right", supports_input=inp, supports_output=out))
    return pins


def arduino_uno_r3_pins() -> list[HardwarePinDef]:
    digital = [
        ("D0", 0, "UART"), ("D1", 1, "UART"), ("D2", 2, "GPIO"), ("D3", 3, "PWM"),
        ("D4", 4, "GPIO"), ("D5", 5, "PWM"), ("D6", 6, "PWM"), ("D7", 7, "GPIO"),
        ("D8", 8, "GPIO"), ("D9", 9, "PWM"), ("D10", 10, "SPI"), ("D11", 11, "SPI"),
        ("D12", 12, "SPI"), ("D13", 13, "GPIO"),
    ]
    power = [
        ("IOREF", "IOREF", "POWER"), ("RESET", "RESET", "GPIO"), ("3V3", "3V3", "POWER"),
        ("5V", "5V", "POWER"), ("GND", "GND", "GROUND"), ("GND2", "GND", "GROUND"),
        ("VIN", "VIN", "POWER"),
    ]
    analog = [
        ("A0", "A0", "ADC"), ("A1", "A1", "ADC"), ("A2", "A2", "ADC"),
        ("A3", "A3", "ADC"), ("A4", "A4", "I2C"), ("A5", "A5", "I2C"),
    ]
    pins: list[HardwarePinDef] = []
    for i, (name, num, ptype) in enumerate(digital):
        pins.append(_pin(name, num, ptype, x=0.98, y=0.1 + i * 0.055, side="right", voltage=5.0))
    for i, (name, num, ptype) in enumerate(power):
        pins.append(
            _pin(
                name, num, ptype, x=0.02, y=0.15 + i * 0.08, side="left", voltage=5.0,
                supports_input=ptype == "GPIO", supports_output=ptype == "GPIO",
            )
        )
    for i, (name, num, ptype) in enumerate(analog):
        pins.append(
            _pin(name, num, ptype, x=0.02, y=0.72 + i * 0.04, side="left", voltage=5.0, supports_output=False)
        )
    return pins


def arduino_mega_pins() -> list[HardwarePinDef]:
    pins = arduino_uno_r3_pins()
    # Extra digital pins summarized
    for i, n in enumerate(range(14, 22)):
        pins.append(_pin(f"D{n}", n, "GPIO", x=0.98, y=0.85 + i * 0.015, side="right", voltage=5.0))
    return pins


def stm32_blue_pill_pins() -> list[HardwarePinDef]:
    left = [("PA0", "ADC"), ("PA1", "ADC"), ("PA2", "UART"), ("PA3", "UART"),
            ("PA4", "SPI"), ("PA5", "SPI"), ("PA6", "SPI"), ("PA7", "SPI"),
            ("PB0", "ADC"), ("PB1", "ADC"), ("PB10", "I2C"), ("PB11", "I2C")]
    right = [("PC13", "GPIO"), ("PC14", "GPIO"), ("PC15", "GPIO"),
             ("PB9", "I2C"), ("PB8", "I2C"), ("PB7", "I2C"), ("PB6", "I2C"),
             ("PB5", "GPIO"), ("PB4", "GPIO"), ("PB3", "GPIO"), ("PA15", "GPIO"), ("PA12", "GPIO")]
    pins: list[HardwarePinDef] = []
    for i, (name, ptype) in enumerate(left):
        pins.append(_pin(name, name, ptype, x=0.02, y=0.08 + i * 0.07, side="left"))
    for i, (name, ptype) in enumerate(right):
        pins.append(_pin(name, name, ptype, x=0.98, y=0.08 + i * 0.07, side="right"))
    pins.append(_pin("3V3", "3V3", "POWER", x=0.3, y=0.02, side="top", supports_input=False, supports_output=False))
    pins.append(_pin("GND", "GND", "GROUND", x=0.7, y=0.02, side="top", supports_input=False, supports_output=False))
    return pins


def raspberry_pi_pico_pins() -> list[HardwarePinDef]:
    left = [(f"GP{i}", i, "GPIO") for i in range(0, 15)]
    left[0] = ("GP0", 0, "UART")
    left[1] = ("GP1", 1, "UART")
    right = [(f"GP{i}", i, "GPIO") for i in range(15, 29)]
    right[10] = ("GP25", 25, "GPIO")  # LED
    right[11] = ("GP26", 26, "ADC")
    right[12] = ("GP27", 27, "ADC")
    right[13] = ("GP28", 28, "ADC")
    pins: list[HardwarePinDef] = []
    for i, (name, num, ptype) in enumerate(left):
        pins.append(_pin(name, num, ptype, x=0.02, y=0.06 + i * 0.06, side="left"))
    for i, (name, num, ptype) in enumerate(right):
        pins.append(
            _pin(name, num, ptype, x=0.98, y=0.06 + i * 0.06, side="right", supports_output=ptype != "ADC")
        )
    pins.append(_pin("3V3", "3V3", "POWER", x=0.5, y=0.02, side="top", supports_input=False, supports_output=False))
    pins.append(_pin("GND", "GND", "GROUND", x=0.5, y=0.98, side="bottom", supports_input=False, supports_output=False))
    return pins


def raspberry_pi_4_pins() -> list[HardwarePinDef]:
    # 40-pin header (odd left, even right) — subset with key GPIOs
    header = [
        (1, "3V3", "POWER"), (2, "5V", "POWER"), (3, "GPIO2", "I2C"), (4, "5V", "POWER"),
        (5, "GPIO3", "I2C"), (6, "GND", "GROUND"), (7, "GPIO4", "GPIO"), (8, "GPIO14", "UART"),
        (9, "GND", "GROUND"), (10, "GPIO15", "UART"), (11, "GPIO17", "GPIO"), (12, "GPIO18", "PWM"),
        (13, "GPIO27", "GPIO"), (14, "GND", "GROUND"), (15, "GPIO22", "GPIO"), (16, "GPIO23", "GPIO"),
        (17, "3V3", "POWER"), (18, "GPIO24", "GPIO"), (19, "GPIO10", "SPI"), (20, "GND", "GROUND"),
        (21, "GPIO9", "SPI"), (22, "GPIO25", "GPIO"), (23, "GPIO11", "SPI"), (24, "GPIO8", "SPI"),
        (25, "GND", "GROUND"), (26, "GPIO7", "SPI"),
    ]
    pins: list[HardwarePinDef] = []
    for phys, name, ptype in header:
        odd = phys % 2 == 1
        row = (phys - 1) // 2
        pins.append(
            _pin(
                name if name not in ("3V3", "5V", "GND") else f"{name}_{phys}",
                name if ptype in ("POWER", "GROUND") else int(name.replace("GPIO", "")),
                ptype,
                x=0.02 if odd else 0.98,
                y=0.05 + row * 0.07,
                side="left" if odd else "right",
                voltage=5.0 if "5V" in name else 3.3,
                supports_input=ptype not in ("POWER", "GROUND"),
                supports_output=ptype not in ("POWER", "GROUND", "ADC"),
            )
        )
    return pins


def esp8266_nodemcu_pins() -> list[HardwarePinDef]:
    left = [("3V3", "3V3", "POWER"), ("EN", "EN", "GPIO"), ("ADC0", 0, "ADC"),
            ("D0", 16, "GPIO"), ("D1", 5, "I2C"), ("D2", 4, "I2C"), ("D3", 0, "GPIO"), ("D4", 2, "GPIO")]
    right = [("VIN", "VIN", "POWER"), ("GND", "GND", "GROUND"), ("RST", "RST", "GPIO"),
             ("D5", 14, "SPI"), ("D6", 12, "SPI"), ("D7", 13, "SPI"), ("D8", 15, "SPI"),
             ("RX", 3, "UART"), ("TX", 1, "UART")]
    pins: list[HardwarePinDef] = []
    for i, (name, num, ptype) in enumerate(left):
        pins.append(
            _pin(name, num, ptype, x=0.02, y=0.1 + i * 0.1, side="left",
                 supports_input=ptype not in ("POWER",), supports_output=ptype not in ("POWER", "ADC", "GROUND"))
        )
    for i, (name, num, ptype) in enumerate(right):
        pins.append(
            _pin(name, num, ptype, x=0.98, y=0.1 + i * 0.09, side="right",
                 supports_input=ptype not in ("POWER", "GROUND"), supports_output=ptype not in ("POWER", "GROUND"))
        )
    return pins


LAYOUT_BUILDERS: dict[str, Any] = {
    "esp32": esp32_devkit_v1_pins,
    "esp32-devkit": esp32_devkit_v1_pins,
    "arduino-uno": arduino_uno_r3_pins,
    "arduino_uno": arduino_uno_r3_pins,
    "arduino-mega": arduino_mega_pins,
    "arduino_mega": arduino_mega_pins,
    "stm32": stm32_blue_pill_pins,
    "raspberry-pi-pico": raspberry_pi_pico_pins,
    "raspberry_pi_pico": raspberry_pi_pico_pins,
    "raspberry-pi-4": raspberry_pi_4_pins,
    "raspberry_pi_4": raspberry_pi_4_pins,
    "esp8266": esp8266_nodemcu_pins,
}


def get_pin_layout(board_type: str) -> list[HardwarePinDef]:
    key = (board_type or "").lower().strip()
    builder = LAYOUT_BUILDERS.get(key)
    if builder is None:
        for alias, fn in LAYOUT_BUILDERS.items():
            if alias in key or key in alias:
                builder = fn
                break
    if builder is None:
        return [
            _pin("D0", 0, "GPIO", x=0.02, y=0.3, side="left"),
            _pin("D1", 1, "GPIO", x=0.98, y=0.3, side="right"),
            _pin("GND", "GND", "GROUND", x=0.5, y=0.9, side="bottom", supports_input=False, supports_output=False),
        ]
    return builder()


def layout_as_dicts(board_type: str) -> list[dict[str, Any]]:
    return [p.to_dict() for p in get_pin_layout(board_type)]


# ---- Silhouette / rendering metadata ---------------------------------------

from .pin_layout import PIN_COLORS  # noqa: E402


class BoardRenderer:
    """Accurate board silhouette descriptors for the workspace canvas."""

    SILHOUETTES: dict[str, dict[str, Any]] = {
        "esp32": {
            "width": 300,
            "height": 150,
            "shape": "esp32-devkit",
            "features": ["usb", "en", "boot", "dual-row"],
            "svg_key": "esp32",
        },
        "arduino-uno": {
            "width": 280,
            "height": 200,
            "shape": "arduino-uno",
            "features": ["usb", "power-jack", "digital-header", "analog-header", "icsp"],
            "svg_key": "arduino-uno",
        },
        "arduino-mega": {
            "width": 340,
            "height": 220,
            "shape": "arduino-mega",
            "features": ["usb", "power-jack", "extended-headers", "icsp"],
            "svg_key": "arduino-uno",
        },
        "stm32": {
            "width": 220,
            "height": 160,
            "shape": "blue-pill",
            "features": ["usb", "dual-row", "reset"],
            "svg_key": "stm32",
        },
        "raspberry-pi-pico": {
            "width": 260,
            "height": 120,
            "shape": "pico-40",
            "features": ["usb", "40-pin"],
            "svg_key": "raspberry-pi-pico",
        },
        "raspberry-pi-4": {
            "width": 320,
            "height": 220,
            "shape": "pi4",
            "features": ["40-pin-gpio", "usb", "ethernet", "hdmi"],
            "svg_key": "raspberry-pi-pico",
        },
        "esp8266": {
            "width": 260,
            "height": 140,
            "shape": "nodemcu",
            "features": ["usb", "dual-row"],
            "svg_key": "esp32",
        },
    }

    @classmethod
    def silhouette(cls, board_type: str) -> dict[str, Any]:
        key = (board_type or "").lower()
        if key in cls.SILHOUETTES:
            return dict(cls.SILHOUETTES[key])
        for alias, meta in cls.SILHOUETTES.items():
            if alias in key or key in alias:
                return dict(meta)
        return {
            "width": 240,
            "height": 140,
            "shape": "generic",
            "features": ["dual-row"],
            "svg_key": "esp32",
        }

    @classmethod
    def render_spec(cls, board_type: str) -> dict[str, Any]:
        return {
            "board_type": board_type,
            "silhouette": cls.silhouette(board_type),
            "pins": layout_as_dicts(board_type),
            "pin_colors": dict(PIN_COLORS),
        }
