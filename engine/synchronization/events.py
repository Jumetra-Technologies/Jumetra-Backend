"""Synchronization protocol event types (internal EventBus, not wire protocol)."""

from __future__ import annotations


class SyncEventType:
    """Event.event_type values for the sync measurement protocol."""

    SYNC_REQUEST = "SYNC_REQUEST"
    SYNC_RESPONSE = "SYNC_RESPONSE"
    SYNC_CORRECTION_REQUEST = "SYNC_CORRECTION_REQUEST"
    SYNC_CORRECTION_RESPONSE = "SYNC_CORRECTION_RESPONSE"
    CLOCK_SAMPLE = "CLOCK_SAMPLE"
    SYNC_MEASUREMENT = "SYNC_MEASUREMENT"


SYNC_EVENT_TYPES = {
    SyncEventType.SYNC_REQUEST,
    SyncEventType.SYNC_RESPONSE,
    SyncEventType.SYNC_CORRECTION_REQUEST,
    SyncEventType.SYNC_CORRECTION_RESPONSE,
    SyncEventType.CLOCK_SAMPLE,
    SyncEventType.SYNC_MEASUREMENT,
}
