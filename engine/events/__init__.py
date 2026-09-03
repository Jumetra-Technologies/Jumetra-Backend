"""HHIP event package — Event model, queue, bus, and subscriber interface."""

from .correction_bridge import CorrectionTransportSubscriber
from .dashboard_publisher import (
    DashboardEvent,
    DashboardEventPublisher,
    DashboardEventType,
    dashboard_publisher,
)
from .event import (
    Event,
    EventPriority,
    EventStatus,
    EventValidationError,
    reset_sequence_counter,
)
from .event_bus import EventBus
from .event_queue import EventQueue
from .subscriber import EventSubscriber

__all__ = [
    "CorrectionTransportSubscriber",
    "DashboardEvent",
    "DashboardEventPublisher",
    "DashboardEventType",
    "Event",
    "EventBus",
    "EventPriority",
    "EventQueue",
    "EventStatus",
    "EventSubscriber",
    "EventValidationError",
    "dashboard_publisher",
    "reset_sequence_counter",
]
