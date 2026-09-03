"""In-process synchronous Event Bus for HHIP.

Owns the subscriber list and delivers events to them. Knows nothing
about devices, transports, or protocols — only
:class:`~engine.events.subscriber.EventSubscriber` and
:class:`~engine.events.event.Event`.

Architectural role::

    Communication → Event → EventQueue → EventBus → Subscribers
"""

from __future__ import annotations

import logging
from typing import Optional

from .event import Event, EventStatus
from .subscriber import EventSubscriber

logger = logging.getLogger("hhip.events.bus")


class EventBus:
    """Synchronous publish/subscribe bus.

    Methods:

    - :meth:`register_subscriber`
    - :meth:`unregister_subscriber`
    - :meth:`publish`
    - :meth:`broadcast`
    - :meth:`subscriber_count`
    """

    def __init__(self) -> None:
        self._subscribers: list[EventSubscriber] = []

    def register_subscriber(self, subscriber: EventSubscriber) -> None:
        """Register a subscriber. Duplicate registration is ignored."""
        if not isinstance(subscriber, EventSubscriber):
            raise TypeError(
                f"register_subscriber expects EventSubscriber, got {type(subscriber).__name__}"
            )
        if subscriber in self._subscribers:
            return
        self._subscribers.append(subscriber)
        logger.debug(
            "[EVENT BUS] Registered subscriber %s (count=%d)",
            type(subscriber).__name__,
            self.subscriber_count(),
        )

    def unregister_subscriber(self, subscriber: EventSubscriber) -> bool:
        """Remove a subscriber. Returns True if it was registered."""
        try:
            self._subscribers.remove(subscriber)
        except ValueError:
            return False
        logger.debug(
            "[EVENT BUS] Unregistered subscriber %s (count=%d)",
            type(subscriber).__name__,
            self.subscriber_count(),
        )
        return True

    def subscriber_count(self) -> int:
        """Return the number of registered subscribers."""
        return len(self._subscribers)

    def publish(self, event: Event) -> None:
        """Dispatch ``event`` to every registered subscriber (in order).

        Lifecycle side effects on ``event``:

        - ``DISPATCHED`` before notifying subscribers
        - ``HANDLED`` after all subscribers return
        - ``COMPLETED`` when delivery finishes successfully

        Subscriber errors are logged; remaining subscribers still run.
        If any subscriber raises, the event still moves to COMPLETED
        after HANDLED so the pipeline does not stall — metrics can
        observe errors separately.
        """
        if not isinstance(event, Event):
            raise TypeError(f"publish expects Event, got {type(event).__name__}")

        event.set_status(EventStatus.DISPATCHED)
        self._log_lifecycle(event, "DISPATCHED")

        errors: list[BaseException] = []
        for subscriber in list(self._subscribers):
            try:
                subscriber.handle_event(event)
            except Exception as exc:  # noqa: BLE001 — isolate subscriber faults
                errors.append(exc)
                logger.exception(
                    "[EVENT BUS] Subscriber %s failed on %s",
                    type(subscriber).__name__,
                    event.event_id,
                )

        event.set_status(EventStatus.HANDLED)
        self._log_lifecycle(event, "HANDLED")

        event.set_status(EventStatus.COMPLETED)
        self._log_lifecycle(event, "COMPLETED")

        event.set_status(EventStatus.ARCHIVED)
        self._log_lifecycle(event, "ARCHIVED")

        if errors:
            logger.warning(
                "[EVENT BUS] publish completed with %d subscriber error(s) for %s",
                len(errors),
                event.event_id,
            )

    def broadcast(self, event: Event) -> None:
        """Deliver ``event`` to all subscribers.

        For Phase 1.4.1A this is equivalent to :meth:`publish`. Kept as
        a distinct API so later phases can add topic filters or
        priority-based fan-out without renaming call sites.
        """
        self.publish(event)

    @staticmethod
    def _log_lifecycle(event: Event, status_label: str) -> None:
        logger.info(
            "[%s] id=%s type=%s corr=%s seq=%s priority=%s status=%s",
            status_label,
            event.event_id,
            event.event_type,
            event.correlation_id,
            event.sequence_number,
            event.priority.value,
            event.current_status.value,
        )
