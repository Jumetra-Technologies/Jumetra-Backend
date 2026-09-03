"""Serial transport for physical hybrid devices with heartbeat monitoring.

Sprint 28: re-exports :class:`SerialHardwareTransport` from
``engine.hybrid.transports`` for backward compatibility with Sprint 27.
"""

from __future__ import annotations

from engine.hybrid.transports.serial_transport import (  # noqa: F401
    SerialHardwareTransport,
    SerialTransport,
)

__all__ = ["SerialTransport", "SerialHardwareTransport"]
