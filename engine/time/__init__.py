"""HHIP time package — clocks, domains, models, and timestamp recording."""

from .clock import Clock, DeviceClock, SimulationClock, SystemClock
from .clock_domain import ClockDomain, ClockDomainRegistry
from .clock_model import ClockModel
from .timestamp_service import (
    TimestampService,
    get_timestamp_service,
    set_timestamp_service,
)

__all__ = [
    "Clock",
    "ClockDomain",
    "ClockDomainRegistry",
    "ClockModel",
    "DeviceClock",
    "SimulationClock",
    "SystemClock",
    "TimestampService",
    "get_timestamp_service",
    "set_timestamp_service",
]
