"""Serial port enumeration via pyserial."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional


@dataclass
class PortInfo:
    device: str
    vid: Optional[int]
    pid: Optional[int]
    manufacturer: Optional[str]
    description: Optional[str]
    serial_number: Optional[str]
    hwid: Optional[str] = None


PortLister = Callable[[], list[PortInfo]]


def default_port_lister() -> list[PortInfo]:
    """List serial ports using pyserial."""
    try:
        from serial.tools import list_ports
    except ImportError:
        return []

    results: list[PortInfo] = []
    for p in list_ports.comports():
        serial = getattr(p, "serial_number", None) or getattr(p, "serialnumber", None)
        results.append(
            PortInfo(
                device=p.device,
                vid=p.vid,
                pid=p.pid,
                manufacturer=p.manufacturer,
                description=p.description,
                serial_number=serial,
                hwid=p.hwid,
            )
        )
    return results
