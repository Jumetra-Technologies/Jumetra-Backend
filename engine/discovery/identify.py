"""USB VID/PID and description heuristics for board identification."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class BoardSignature:
    board_type: str
    label: str
    vid: Optional[int] = None
    pid: Optional[int] = None
    description_contains: tuple[str, ...] = ()
    manufacturer_contains: tuple[str, ...] = ()


# Well-known USB identities for supported boards.
BOARD_SIGNATURES: list[BoardSignature] = [
    BoardSignature("arduino-uno", "Arduino Uno R3", 0x2341, 0x0043),
    BoardSignature("arduino-uno", "Arduino Uno R3", 0x2341, 0x0001),
    BoardSignature("arduino-mega", "Arduino Mega 2560", 0x2341, 0x0010),
    BoardSignature("arduino-mega", "Arduino Mega 2560", 0x2341, 0x0042),
    BoardSignature("arduino-nano", "Arduino Nano", 0x2341, 0x0050),
    BoardSignature("esp32", "ESP32 DevKit", 0x10C4, 0xEA60, ("CP210", "USB to UART")),
    BoardSignature("esp32", "ESP32 DevKit", 0x1A86, 0x55D4, ("CH340", "USB-SERIAL")),
    BoardSignature("esp32", "ESP32 DevKit", 0x303A, 0x1001, ("Espressif", "JTAG")),
    BoardSignature("esp8266", "ESP8266", 0x1A86, 0x7523, ("CH340",)),
    BoardSignature("esp8266", "ESP8266", 0x10C4, 0xEA60, ("CP210",)),
    BoardSignature("stm32", "STM32 Blue Pill", 0x0483, 0x5740),
    BoardSignature("stm32", "STM32", 0x0483, 0x3748, ("STM32",)),
    BoardSignature("stm32", "STM32", 0x1EAF, 0x0003, ("LeafLabs", "Maple")),
    BoardSignature("raspberry-pi-pico", "Raspberry Pi Pico", 0x2E8A, 0x0005),
    BoardSignature("raspberry-pi-pico", "Raspberry Pi Pico", 0x2E8A, 0x000A),
    # CH340 clones often used for Arduino Nano / Uno clones
    BoardSignature("arduino-nano", "Arduino Nano (CH340)", 0x1A86, 0x7523, ("CH340",)),
    BoardSignature("arduino-uno", "Arduino Uno (CH340)", 0x1A86, 0x7523, ("CH340", "Arduino")),
]

DESCRIPTION_HINTS: list[tuple[str, str, str]] = [
    ("arduino uno", "arduino-uno", "Arduino Uno R3"),
    ("mega 2560", "arduino-mega", "Arduino Mega 2560"),
    ("arduino nano", "arduino-nano", "Arduino Nano"),
    ("esp32", "esp32", "ESP32 DevKit V1"),
    ("esp8266", "esp8266", "ESP8266"),
    ("stm32", "stm32", "STM32"),
    ("blue pill", "stm32", "STM32 Blue Pill"),
    ("pico", "raspberry-pi-pico", "Raspberry Pi Pico"),
]


def identify_board(
    *,
    vid: Optional[int],
    pid: Optional[int],
    description: Optional[str],
    manufacturer: Optional[str],
) -> tuple[str, str]:
    """Return ``(board_type, label)`` for a serial port."""
    desc = (description or "").lower()
    mfr = (manufacturer or "").lower()

    for sig in BOARD_SIGNATURES:
        if sig.vid is not None and sig.pid is not None:
            if vid == sig.vid and pid == sig.pid:
                if sig.description_contains and not any(h.lower() in desc for h in sig.description_contains):
                    continue
                if sig.manufacturer_contains and not any(h.lower() in mfr for h in sig.manufacturer_contains):
                    continue
                return sig.board_type, sig.label

    combined = f"{desc} {mfr}".strip()
    for hint, board_type, label in DESCRIPTION_HINTS:
        if hint in combined:
            return board_type, label

    if vid is not None or desc or mfr:
        return "unknown-serial", "Unknown Serial Device"
    return "unknown-serial", "Unknown Serial Device"
