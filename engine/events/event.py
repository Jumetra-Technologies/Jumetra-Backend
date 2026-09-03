"""Central HHIP event representation.

Events are the internal currency of the engine. They are deliberately
independent of physical/virtual devices and of the wire protocol
``Message`` type: some future events (simulation ticks, clock drift
alerts, adapter lifecycle) will never appear on the serial line.

Phase 1.4.1A adds lifecycle status, priority, correlation ids, and
global sequence numbers so later phases (sync engine, replay, plugins)
can rely on a stable event shape.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Optional, Union


def _now_ms() -> int:
    """Wall-clock fallback; prefer TimestampService via get_timestamp_service()."""
    return int(time.time() * 1000)


def _service_now() -> int:
    from engine.time.timestamp_service import get_timestamp_service

    return get_timestamp_service().now()


def _new_event_id() -> str:
    return f"evt_{uuid.uuid4().hex[:12]}"


def _new_correlation_id() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Global event sequence (process-wide, synchronous)
# ---------------------------------------------------------------------------

_sequence_counter: int = 0


def _next_sequence_number() -> int:
    """Return the next globally increasing event sequence number."""
    global _sequence_counter
    _sequence_counter += 1
    return _sequence_counter


def reset_sequence_counter(value: int = 0) -> None:
    """Reset the global sequence counter (intended for tests)."""
    global _sequence_counter
    _sequence_counter = value


def peek_sequence_counter() -> int:
    """Return the current sequence counter without incrementing."""
    return _sequence_counter


class EventValidationError(ValueError):
    """Raised when an Event fails structural validation."""


class EventStatus(Enum):
    """Lifecycle stages of an HHIP event."""

    CREATED = "CREATED"
    QUEUED = "QUEUED"
    DISPATCHED = "DISPATCHED"
    HANDLED = "HANDLED"
    COMPLETED = "COMPLETED"
    ARCHIVED = "ARCHIVED"


class EventPriority(Enum):
    """Delivery priority hint for future schedulers / plugins."""

    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


DEFAULT_PROTOCOL_VERSION = "1.0"

# Valid forward transitions (ARCHITECTURE: allow same-status no-op skip;
# ARCHIVED is terminal).
_ALLOWED_TRANSITIONS: dict[EventStatus, set[EventStatus]] = {
    EventStatus.CREATED: {EventStatus.QUEUED, EventStatus.DISPATCHED},
    EventStatus.QUEUED: {EventStatus.DISPATCHED},
    EventStatus.DISPATCHED: {EventStatus.HANDLED, EventStatus.COMPLETED},
    EventStatus.HANDLED: {EventStatus.COMPLETED, EventStatus.ARCHIVED},
    EventStatus.COMPLETED: {EventStatus.ARCHIVED},
    EventStatus.ARCHIVED: set(),
}


@dataclass
class StatusTransition:
    """One recorded lifecycle transition."""

    status: EventStatus
    timestamp: int

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status.value, "timestamp": self.timestamp}


def _coerce_status(value: Union[EventStatus, str]) -> EventStatus:
    if isinstance(value, EventStatus):
        return value
    return EventStatus(str(value))


def _coerce_priority(value: Union[EventPriority, str, None]) -> EventPriority:
    if value is None:
        return EventPriority.NORMAL
    if isinstance(value, EventPriority):
        return value
    return EventPriority(str(value))


@dataclass
class Event:
    """A single event flowing through the HHIP event backbone.

    Attributes:
        event_id: Stable unique identifier (e.g. ``evt_a1b2c3d4e5f6``).
        event_type: Logical type (e.g. ``STATE_UPDATE``, ``HELLO``, ``HEARTBEAT``).
        source: Originating component or device id.
        target: Intended recipient (device id, ``hhip``, or empty).
        timestamp: Legacy epoch-ms field (mirrors created / wire time).
        payload: Event-specific data (JSON-serializable).
        metadata: Optional bookkeeping (wire message_id, origin, etc.).
        sequence_number: Process-global increasing integer.
        priority: Delivery priority (default NORMAL).
        protocol_version: Event schema / protocol version (default ``1.0``).
        correlation_id: UUID linking related events (child events may inherit).
        created_timestamp: When the event entered CREATED.
        processed_timestamp: When processing began (DISPATCHED), if any.
        completed_timestamp: When the event reached COMPLETED, if any.
    """

    event_id: str
    event_type: str
    source: str
    target: str = ""
    timestamp: int = field(default_factory=_now_ms)
    payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    sequence_number: int = 0
    priority: EventPriority = EventPriority.NORMAL
    protocol_version: str = DEFAULT_PROTOCOL_VERSION
    correlation_id: str = field(default_factory=_new_correlation_id)
    created_timestamp: int = 0
    processed_timestamp: Optional[int] = None
    completed_timestamp: Optional[int] = None
    timing: dict[str, Any] = field(default_factory=dict)
    _status_history: list[StatusTransition] = field(default_factory=list, repr=False)
    # Non-serialized attachment: original protocol message for engine handlers.
    _protocol_message: Optional[dict[str, Any]] = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if isinstance(self.priority, str):
            self.priority = _coerce_priority(self.priority)
        if self.created_timestamp <= 0:
            self.created_timestamp = self.timestamp if self.timestamp > 0 else _service_now()
        if self.sequence_number <= 0:
            self.sequence_number = _next_sequence_number()
        if not self.correlation_id:
            self.correlation_id = _new_correlation_id()
        if not self._status_history:
            self._status_history = [
                StatusTransition(status=EventStatus.CREATED, timestamp=self.created_timestamp)
            ]
        if not self.timing:
            self.timing = {}
        # Centralized stamp — do not duplicate time logic elsewhere.
        from engine.time.timestamp_service import get_timestamp_service

        get_timestamp_service().stamp_created(self, time_ms=self.created_timestamp)
        self.validate()

    # --- Lifecycle ---------------------------------------------------------

    @property
    def created_time(self) -> Optional[int]:
        return self.timing.get("created_time", self.created_timestamp)

    @property
    def queued_time(self) -> Optional[int]:
        return self.timing.get("queued_time")

    @property
    def dispatched_time(self) -> Optional[int]:
        return self.timing.get("dispatched_time")

    @property
    def processed_time(self) -> Optional[int]:
        return self.timing.get("processed_time")

    @property
    def completed_time(self) -> Optional[int]:
        return self.timing.get("completed_time", self.completed_timestamp)

    @property
    def current_status(self) -> EventStatus:
        """Return the most recent lifecycle status."""
        if not self._status_history:
            return EventStatus.CREATED
        return self._status_history[-1].status

    @property
    def status_history(self) -> list[dict[str, Any]]:
        """Return ``[{"status": "...", "timestamp": ...}, ...]``."""
        return [entry.to_dict() for entry in self._status_history]

    @property
    def history(self) -> list[str]:
        """Return status names only, e.g. ``["CREATED", "QUEUED", ...]``."""
        return [entry.status.value for entry in self._status_history]

    def set_status(
        self,
        status: Union[EventStatus, str],
        *,
        timestamp: Optional[int] = None,
        force: bool = False,
    ) -> None:
        """Transition the event to ``status`` and append to history.

        Args:
            status: Target :class:`EventStatus` (or its string value).
            timestamp: Optional epoch-ms; defaults to now.
            force: If True, skip transition-graph checks (deserialize / tests).

        Raises:
            EventValidationError: On invalid or illegal transition.
        """
        new_status = _coerce_status(status)
        ts = _service_now() if timestamp is None else timestamp

        if not force and self._status_history:
            current = self.current_status
            if new_status == current:
                return
            allowed = _ALLOWED_TRANSITIONS.get(current, set())
            if new_status not in allowed:
                raise EventValidationError(
                    f"illegal status transition {current.value} → {new_status.value}"
                )

        self._status_history.append(StatusTransition(status=new_status, timestamp=ts))

        from engine.time.timestamp_service import get_timestamp_service

        get_timestamp_service().stamp_status(self, new_status, time_ms=ts)

        if new_status == EventStatus.DISPATCHED and self.processed_timestamp is None:
            self.processed_timestamp = ts
        if new_status == EventStatus.COMPLETED:
            self.completed_timestamp = ts

    def attach_protocol_message(self, message: Mapping[str, Any]) -> None:
        """Attach the original wire message for protocol handlers (not serialized)."""
        self._protocol_message = dict(message)

    def protocol_message(self) -> Optional[dict[str, Any]]:
        """Return the attached wire message, if any."""
        return self._protocol_message

    def validate(self) -> None:
        """Validate required fields and basic types. Raises EventValidationError."""
        errors: list[str] = []

        if not isinstance(self.event_id, str) or not self.event_id.strip():
            errors.append("event_id must be a non-empty string")
        if not isinstance(self.event_type, str) or not self.event_type.strip():
            errors.append("event_type must be a non-empty string")
        if not isinstance(self.source, str) or not self.source.strip():
            errors.append("source must be a non-empty string")
        if not isinstance(self.target, str):
            errors.append("target must be a string")
        if not isinstance(self.timestamp, int) or isinstance(self.timestamp, bool):
            errors.append("timestamp must be an int (epoch milliseconds)")
        elif self.timestamp < 0:
            errors.append("timestamp must be non-negative")
        if not isinstance(self.payload, dict):
            errors.append("payload must be a dict")
        if not isinstance(self.metadata, dict):
            errors.append("metadata must be a dict")
        if not isinstance(self.sequence_number, int) or isinstance(self.sequence_number, bool):
            errors.append("sequence_number must be an int")
        elif self.sequence_number < 0:
            errors.append("sequence_number must be non-negative")
        if not isinstance(self.priority, EventPriority):
            errors.append("priority must be an EventPriority")
        if not isinstance(self.protocol_version, str) or not self.protocol_version.strip():
            errors.append("protocol_version must be a non-empty string")
        if not isinstance(self.correlation_id, str) or not self.correlation_id.strip():
            errors.append("correlation_id must be a non-empty string")

        if errors:
            raise EventValidationError("; ".join(errors))

    @classmethod
    def create(
        cls,
        event_type: str,
        source: str,
        *,
        target: str = "",
        payload: Optional[Mapping[str, Any]] = None,
        metadata: Optional[Mapping[str, Any]] = None,
        event_id: Optional[str] = None,
        timestamp: Optional[int] = None,
        priority: Union[EventPriority, str, None] = None,
        protocol_version: str = DEFAULT_PROTOCOL_VERSION,
        correlation_id: Optional[str] = None,
        sequence_number: Optional[int] = None,
    ) -> "Event":
        """Factory with defaults for id, timestamps, correlation, and sequence."""
        created = _service_now() if timestamp is None else timestamp
        return cls(
            event_id=event_id or _new_event_id(),
            event_type=event_type,
            source=source,
            target=target or "",
            timestamp=created,
            payload=dict(payload) if payload is not None else {},
            metadata=dict(metadata) if metadata is not None else {},
            sequence_number=sequence_number if sequence_number is not None else 0,
            priority=_coerce_priority(priority),
            protocol_version=protocol_version or DEFAULT_PROTOCOL_VERSION,
            correlation_id=correlation_id or _new_correlation_id(),
            created_timestamp=created,
        )

    @classmethod
    def from_message(cls, message: Mapping[str, Any]) -> "Event":
        """Adapt a decoded protocol message into an internal Event.

        Maps wire fields without importing device modules. Extra wire
        fields (version, message_id, sequence) are preserved in metadata
        so later phases can correlate Events back to the wire transcript.
        """
        payload = message.get("payload") or {}
        if not isinstance(payload, dict):
            payload = {"value": payload}

        metadata = {
            "version": message.get("version"),
            "message_id": message.get("message_id"),
            "sequence": message.get("sequence"),
            "origin": "protocol",
        }
        metadata = {k: v for k, v in metadata.items() if v is not None}

        wire_ts = message.get("timestamp")
        timestamp = wire_ts if isinstance(wire_ts, int) and not isinstance(wire_ts, bool) else _service_now()

        wire_version = message.get("version")
        if wire_version is None:
            protocol_version = DEFAULT_PROTOCOL_VERSION
        else:
            protocol_version = str(wire_version) if str(wire_version).count(".") else f"{wire_version}.0"

        event = cls.create(
            event_type=str(message.get("type", "UNKNOWN")),
            source=str(message.get("source", "")),
            target=str(message.get("target", "") or ""),
            payload=payload,
            metadata=metadata,
            timestamp=timestamp,
            protocol_version=protocol_version,
        )
        event.attach_protocol_message(message)
        return event

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain JSON-compatible dict."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "source": self.source,
            "target": self.target,
            "timestamp": self.timestamp,
            "payload": self.payload,
            "metadata": self.metadata,
            "sequence_number": self.sequence_number,
            "priority": self.priority.value,
            "protocol_version": self.protocol_version,
            "correlation_id": self.correlation_id,
            "created_timestamp": self.created_timestamp,
            "processed_timestamp": self.processed_timestamp,
            "completed_timestamp": self.completed_timestamp,
            "timing": dict(self.timing),
            "current_status": self.current_status.value,
            "status_history": self.status_history,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Event":
        """Deserialize from a dict produced by :meth:`to_dict`."""
        if not isinstance(data, Mapping):
            raise EventValidationError("from_dict expects a mapping")

        created = int(data["created_timestamp"]) if "created_timestamp" in data else (
            int(data["timestamp"]) if "timestamp" in data else _now_ms()
        )

        history_raw = data.get("status_history") or []
        history: list[StatusTransition] = []
        for entry in history_raw:
            if isinstance(entry, Mapping):
                history.append(
                    StatusTransition(
                        status=_coerce_status(entry["status"]),
                        timestamp=int(entry["timestamp"]),
                    )
                )
            else:
                history.append(StatusTransition(status=_coerce_status(entry), timestamp=created))

        event = cls(
            event_id=str(data.get("event_id", "")),
            event_type=str(data.get("event_type", "")),
            source=str(data.get("source", "")),
            target=str(data.get("target", "") or ""),
            timestamp=int(data["timestamp"]) if "timestamp" in data else created,
            payload=dict(data.get("payload") or {}),
            metadata=dict(data.get("metadata") or {}),
            sequence_number=int(data["sequence_number"]) if "sequence_number" in data else 0,
            priority=_coerce_priority(data.get("priority")),
            protocol_version=str(data.get("protocol_version") or DEFAULT_PROTOCOL_VERSION),
            correlation_id=str(data.get("correlation_id") or _new_correlation_id()),
            created_timestamp=created,
            processed_timestamp=(
                int(data["processed_timestamp"]) if data.get("processed_timestamp") is not None else None
            ),
            completed_timestamp=(
                int(data["completed_timestamp"]) if data.get("completed_timestamp") is not None else None
            ),
            timing=dict(data.get("timing") or {}),
            _status_history=history
            or [StatusTransition(status=EventStatus.CREATED, timestamp=created)],
        )
        return event

    def to_json(self) -> str:
        """Serialize to a JSON string (no trailing newline)."""
        return json.dumps(self.to_dict(), separators=(",", ":"), sort_keys=False)

    @classmethod
    def from_json(cls, raw: str) -> "Event":
        """Deserialize from a JSON string."""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise EventValidationError(f"invalid JSON: {exc}") from exc
        return cls.from_dict(data)
