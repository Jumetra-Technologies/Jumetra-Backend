"""In-process FIFO event queue for the HHIP event backbone.

Uses only the Python standard library. No external brokers. Thread-safe
so the serial read loop and future consumers (State Manager, Metrics,
Storage, Router) can run on different threads.

Architectural role::

    Communication → Event Creator → EventQueue → Subscribers
"""

from __future__ import annotations

import queue
from typing import Optional

from .event import Event, EventStatus


class EventQueue:
    """Ordered store of :class:`~engine.events.event.Event` instances.

    Required surface for Phase 1.4.1:

    - :meth:`add_event` — enqueue
    - :meth:`get_event` — dequeue (FIFO)
    - :meth:`size` — approximate length
    - :meth:`clear` — drop all pending events
    """

    def __init__(self, maxsize: int = 0) -> None:
        """Create a queue.

        Args:
            maxsize: Maximum pending events. ``0`` means unbounded
                (``queue.Queue`` convention).
        """
        self._queue: queue.Queue[Event] = queue.Queue(maxsize=maxsize)

    def add_event(self, event: Event) -> None:
        """Append an event, preserving insertion order.

        Marks the event as :attr:`~engine.events.event.EventStatus.QUEUED`.
        """
        if not isinstance(event, Event):
            raise TypeError(f"add_event expects Event, got {type(event).__name__}")
        event.set_status(EventStatus.QUEUED)
        self._queue.put(event)

    def get_event(self, block: bool = True, timeout: Optional[float] = None) -> Optional[Event]:
        """Remove and return the next event in FIFO order.

        Args:
            block: If True, wait until an event is available (or timeout).
            timeout: Seconds to wait when ``block`` is True. ``None`` waits forever.

        Returns:
            The next :class:`Event`, or ``None`` if the queue is empty and
            ``block`` is False, or if a timeout expires.
        """
        try:
            return self._queue.get(block=block, timeout=timeout)
        except queue.Empty:
            return None

    def size(self) -> int:
        """Return the approximate number of pending events."""
        return self._queue.qsize()

    def clear(self) -> None:
        """Discard all pending events without processing them."""
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break

    # --- Compatibility aliases (Phase 1.3 stub API) -------------------

    def put(self, event: Event) -> None:
        """Alias for :meth:`add_event` (Phase 1.3 name)."""
        self.add_event(event)

    def get(self, block: bool = True, timeout: Optional[float] = None) -> Event:
        """Blocking get that raises ``queue.Empty`` on timeout (Phase 1.3)."""
        return self._queue.get(block=block, timeout=timeout)

    def get_nowait(self) -> Optional[Event]:
        """Non-blocking get; returns ``None`` if empty (Phase 1.3)."""
        return self.get_event(block=False)

    def empty(self) -> bool:
        return self._queue.empty()

    def qsize(self) -> int:
        """Alias for :meth:`size` (Phase 1.3 name)."""
        return self.size()
