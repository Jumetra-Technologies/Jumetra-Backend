"""Device state tracking for the HHIP engine.

Maintains the latest known state of every device (physical or virtual)
whose transitions flow through the event backbone / Router.

Phase 1.4.1 keeps one record per device_id (not a full history log).
The record shape (previous + current + source + timestamp) is what
later phases need for event replay and synchronization.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger("hhip.state.manager")


def _now_ms() -> int:
    return int(time.time() * 1000)


@dataclass
class StateRecord:
    """Latest state transition for a single device."""

    device_id: str
    previous_state: Any
    current_state: Any
    source: str
    timestamp: int = field(default_factory=_now_ms)

    def to_dict(self) -> dict:
        return {
            "device_id": self.device_id,
            "previous_state": self.previous_state,
            "current_state": self.current_state,
            "source": self.source,
            "timestamp": self.timestamp,
        }


class StateManager:
    """Tracks the current state of all known devices."""

    def __init__(self) -> None:
        self._states: dict[str, StateRecord] = {}

    def update_state(
        self,
        device: str,
        new_state: Any,
        *,
        source: str = "",
        previous_state: Any = ...,
        timestamp: Optional[int] = None,
    ) -> dict:
        """Update a device's state and return the transition summary.

        Args:
            device: Device id (e.g. ``virtual_led_01``).
            new_state: New state value (e.g. ``"ON"``).
            source: Originating device or component id.
            previous_state: Explicit previous value. If omitted (sentinel),
                uses the stored current state, or ``None`` if unknown.
            timestamp: Optional epoch-ms; defaults to now.

        Returns:
            ``{"device", "previous", "current", "timestamp", "source"}``.
        """
        if previous_state is ...:
            existing = self._states.get(device)
            previous = existing.current_state if existing is not None else None
        else:
            previous = previous_state

        ts = _now_ms() if timestamp is None else timestamp
        record = StateRecord(
            device_id=device,
            previous_state=previous,
            current_state=new_state,
            source=source,
            timestamp=ts,
        )
        self._states[device] = record

        logger.info("[STATE] %s: %s → %s", device, previous, new_state)

        return {
            "device": device,
            "previous": previous,
            "current": new_state,
            "timestamp": ts,
            "source": source,
        }

    def get_state(self, device: str) -> Any:
        """Return the current state value for ``device``, or ``None`` if unknown."""
        record = self._states.get(device)
        return record.current_state if record is not None else None

    def get_all_states(self) -> dict[str, Any]:
        """Return ``{device_id: current_state}`` for every tracked device."""
        return {device_id: record.current_state for device_id, record in self._states.items()}

    # --- Phase 1.4 API (kept for Router and existing tests) -----------

    def record(
        self, device_id: str, previous_state: Any, current_state: Any, source: str
    ) -> StateRecord:
        """Record a state transition (Phase 1.4 name). Returns the StateRecord."""
        self.update_state(
            device_id,
            current_state,
            source=source,
            previous_state=previous_state,
        )
        return self._states[device_id]

    def get(self, device_id: str) -> Optional[StateRecord]:
        """Return the full :class:`StateRecord` for ``device_id``, if any."""
        return self._states.get(device_id)

    def all_states(self) -> list[StateRecord]:
        """Return all :class:`StateRecord` instances."""
        return list(self._states.values())
