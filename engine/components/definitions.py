"""Shared vocabulary for external component definitions."""

from __future__ import annotations

from .models import ComponentCategory, InterfaceType
from .v2.pin_model import PinType

SUPPORTED_CATEGORIES = {
    ComponentCategory.SENSOR.value,
    ComponentCategory.ACTUATOR.value,
    ComponentCategory.DISPLAY.value,
    "communication",
    "controller",
    "mcu",
    "module",
    "power",
    "robotics",
}

SUPPORTED_INTERFACES = {
    "gpio",
    "digital",
    "analog",
    "adc",
    "dac",
    "i2c",
    "spi",
    "uart",
    "onewire",
    "pwm",
    "wifi",
    "bluetooth",
}

SUPPORTED_PIN_TYPES = {
    PinType.POWER.value,
    PinType.GROUND.value,
    PinType.GPIO.value,
    PinType.PWM.value,
    PinType.ADC.value,
    PinType.DAC.value,
    PinType.UART_TX.value,
    PinType.UART_RX.value,
    PinType.I2C_SDA.value,
    PinType.I2C_SCL.value,
    PinType.SPI_MOSI.value,
    PinType.SPI_MISO.value,
    PinType.SPI_CLK.value,
    PinType.SPI_CS.value,
    "I2C",
    "SPI",
    "UART",
}

__all__ = [
    "ComponentCategory",
    "InterfaceType",
    "PinType",
    "SUPPORTED_CATEGORIES",
    "SUPPORTED_INTERFACES",
    "SUPPORTED_PIN_TYPES",
]