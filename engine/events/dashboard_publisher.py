"""Dashboard event publisher — real-time platform events for the research UI.

Publishes platform-level events to WebSocket subscribers without
modifying synchronization or device communication logic.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

logger = logging.getLogger("hhip.events.dashboard_publisher")


class DashboardEventType(str, Enum):
    """Platform events streamed to the research dashboard."""

    DEVICE_CONNECTED = "DEVICE_CONNECTED"
    DEVICE_DISCONNECTED = "DEVICE_DISCONNECTED"
    SYNC_STARTED = "SYNC_STARTED"
    SYNC_PROGRESS = "SYNC_PROGRESS"
    SYNC_COMPLETED = "SYNC_COMPLETED"
    CORRECTION_APPLIED = "CORRECTION_APPLIED"
    EXPERIMENT_COMPLETED = "EXPERIMENT_COMPLETED"


@dataclass
class DashboardEvent:
    """Serializable dashboard event payload."""

    event_type: DashboardEventType
    timestamp: int
    event_id: str = field(default_factory=lambda: f"DEV{uuid.uuid4().hex[:8].upper()}")
    device_id: Optional[str] = None
    experiment_id: Optional[str] = None
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["event_type"] = self.event_type.value
        return data


SubscriberCallback = Callable[[DashboardEvent], Any]


class DashboardEventPublisher:
    """In-process pub/sub bridge between platform services and WebSocket clients."""

    def __init__(self) -> None:
        self._subscribers: list[SubscriberCallback] = []
        self._history: list[DashboardEvent] = []
        self._max_history = 200
        self._lock = asyncio.Lock()

    @property
    def history(self) -> list[DashboardEvent]:
        return list(self._history)

    def subscribe(self, callback: SubscriberCallback) -> None:
        if callback not in self._subscribers:
            self._subscribers.append(callback)

    def unsubscribe(self, callback: SubscriberCallback) -> None:
        try:
            self._subscribers.remove(callback)
        except ValueError:
            pass

    def publish(
        self,
        event_type: DashboardEventType,
        *,
        device_id: Optional[str] = None,
        experiment_id: Optional[str] = None,
        payload: Optional[dict[str, Any]] = None,
        timestamp: Optional[int] = None,
    ) -> DashboardEvent:
        event = DashboardEvent(
            event_type=event_type,
            timestamp=timestamp or int(time.time() * 1000),
            device_id=device_id,
            experiment_id=experiment_id,
            payload=dict(payload or {}),
        )
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history :]

        for callback in list(self._subscribers):
            try:
                result = callback(event)
                if asyncio.iscoroutine(result):
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(result)
                    except RuntimeError:
                        asyncio.run(result)
            except Exception:
                logger.exception(
                    "[DASHBOARD PUBLISHER] subscriber failed for %s",
                    event.event_type.value,
                )

        logger.info(
            "[DASHBOARD PUBLISHER] %s experiment=%s device=%s",
            event.event_type.value,
            event.experiment_id,
            event.device_id,
        )
        return event

    def publish_device_connected(self, device_id: str, **payload: Any) -> DashboardEvent:
        return self.publish(
            DashboardEventType.DEVICE_CONNECTED,
            device_id=device_id,
            payload=payload,
        )

    def publish_device_disconnected(self, device_id: str, **payload: Any) -> DashboardEvent:
        return self.publish(
            DashboardEventType.DEVICE_DISCONNECTED,
            device_id=device_id,
            payload=payload,
        )

    def publish_sync_started(
        self, experiment_id: str, device_id: Optional[str] = None, **payload: Any
    ) -> DashboardEvent:
        return self.publish(
            DashboardEventType.SYNC_STARTED,
            experiment_id=experiment_id,
            device_id=device_id,
            payload=payload,
        )

    def publish_sync_progress(
        self,
        experiment_id: str,
        *,
        device_id: Optional[str] = None,
        progress: float = 0.0,
        **payload: Any,
    ) -> DashboardEvent:
        payload = {"progress": progress, **payload}
        return self.publish(
            DashboardEventType.SYNC_PROGRESS,
            experiment_id=experiment_id,
            device_id=device_id,
            payload=payload,
        )

    def publish_sync_completed(
        self, experiment_id: str, device_id: Optional[str] = None, **payload: Any
    ) -> DashboardEvent:
        return self.publish(
            DashboardEventType.SYNC_COMPLETED,
            experiment_id=experiment_id,
            device_id=device_id,
            payload=payload,
        )

    def publish_correction_applied(
        self, experiment_id: str, device_id: str, **payload: Any
    ) -> DashboardEvent:
        return self.publish(
            DashboardEventType.CORRECTION_APPLIED,
            experiment_id=experiment_id,
            device_id=device_id,
            payload=payload,
        )

    def publish_experiment_completed(
        self, experiment_id: str, **payload: Any
    ) -> DashboardEvent:
        return self.publish(
            DashboardEventType.EXPERIMENT_COMPLETED,
            experiment_id=experiment_id,
            payload=payload,
        )


# Module-level singleton for platform services and API layer.
dashboard_publisher = DashboardEventPublisher()
