"""Subscriber interface for the HHIP Event Bus.

Every future consumer (Router, Metrics, Storage, Dashboard, AI, …)
should implement :class:`EventSubscriber`. The bus knows only this
interface — never concrete device or transport types.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .event import Event


class EventSubscriber(ABC):
    """Abstract subscriber that receives events from :class:`EventBus`."""

    @abstractmethod
    def handle_event(self, event: "Event") -> None:
        """Handle a single event.

        Implementations must be synchronous and should not block the
        communication thread for long. Errors should be raised so the
        bus can record them; the bus continues notifying remaining
        subscribers unless configured otherwise.
        """
