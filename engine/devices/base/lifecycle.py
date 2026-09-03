"""Device lifecycle event types for the HHIP Event Bus."""

from __future__ import annotations

from typing import Any, Mapping, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ...events.event import Event
    from ...events.event_bus import EventBus
    from .device import Device


class DeviceLifecycleEvent:
    """Internal event_type values for device lifecycle (not wire protocol)."""

    REGISTERED = "DEVICE_REGISTERED"
    CONNECTED = "DEVICE_CONNECTED"
    DISCONNECTED = "DEVICE_DISCONNECTED"
    ERROR = "DEVICE_ERROR"
    HEALTH_CHANGED = "DEVICE_HEALTH_CHANGED"


def build_lifecycle_event(
    event_type: str,
    device: "Device",
    *,
    extra_payload: Optional[Mapping[str, Any]] = None,
) -> "Event":
    """Create an Event describing a device lifecycle transition."""
    from ...events.event import Event

    payload: dict[str, Any] = {
        "device_id": device.device_id,
        "device_type": device.device_type,
        "device_mode": device.device_mode.value,
        "status": device.status.value if hasattr(device.status, "value") else str(device.status),
    }
    if extra_payload:
        payload.update(dict(extra_payload))

    return Event.create(
        event_type=event_type,
        source=device.device_id,
        target="hhip",
        payload=payload,
        metadata={"origin": "device_lifecycle"},
    )


def publish_lifecycle(
    bus: Optional["EventBus"],
    event_type: str,
    device: "Device",
    *,
    extra_payload: Optional[Mapping[str, Any]] = None,
) -> Optional["Event"]:
    """Publish a lifecycle event on ``bus`` if one is configured."""
    if bus is None:
        return None
    event = build_lifecycle_event(event_type, device, extra_payload=extra_payload)
    # Lifecycle events skip the queue for now — direct bus publish keeps
    # registration synchronous and avoids nesting the engine drain loop.
    from ...events.event import EventStatus

    if event.current_status == EventStatus.CREATED:
        event.set_status(EventStatus.QUEUED)
    bus.publish(event)
    return event
