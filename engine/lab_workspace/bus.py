"""Bus metadata helpers for I2C / SPI / UART workspace wires."""

from __future__ import annotations

from typing import Any, Optional


I2C_DEFAULT_ADDRESSES: dict[str, str] = {
    "oled": "0x3C",
    "oled-ssd1306": "0x3C",
    "bmp280": "0x76",
    "bme280": "0x76",
    "mpu6050": "0x68",
    "lcd": "0x27",
    "lcd-16x2": "0x27",
}

BUS_PIN_HINTS = {
    "i2c": {"SDA", "SCL"},
    "spi": {"MOSI", "MISO", "SCK", "CS", "SS"},
    "uart": {"TX", "RX", "TX0", "RX0"},
}


def infer_bus_type(source_handle: str, target_handle: str, protocol: str = "") -> Optional[str]:
    proto = (protocol or "").lower()
    if proto in {"i2c", "spi", "uart"}:
        return proto
    handles = {source_handle.upper(), target_handle.upper()}
    for bus, pins in BUS_PIN_HINTS.items():
        if handles & pins:
            return bus
    return None


def build_bus_metadata(
    *,
    protocol: str,
    source_handle: str,
    target_handle: str,
    source_component_id: str = "",
    target_component_id: str = "",
) -> dict[str, Any]:
    bus = infer_bus_type(source_handle, target_handle, protocol)
    if not bus:
        return {}
    meta: dict[str, Any] = {
        "type": bus.upper(),
        "source_pin": source_handle,
        "target_pin": target_handle,
    }
    if bus == "i2c":
        addr = I2C_DEFAULT_ADDRESSES.get(target_component_id) or I2C_DEFAULT_ADDRESSES.get(
            source_component_id
        )
        if addr:
            meta["address"] = addr
        meta["lines"] = ["SDA", "SCL"]
    elif bus == "spi":
        meta["lines"] = ["MOSI", "MISO", "SCK", "CS"]
    elif bus == "uart":
        meta["lines"] = ["TX", "RX"]
    return meta
