"""Discovery service wrapper for the FastAPI layer."""

from __future__ import annotations

from typing import Any, Callable, Optional

from engine.discovery.models import DiscoveredDevice
from engine.discovery.service import HardwareDiscoveryService


class DiscoveryService:
    """Thin API-facing wrapper around :class:`HardwareDiscoveryService`."""

    def __init__(self, discovery: HardwareDiscoveryService) -> None:
        self._discovery = discovery
        self._ws_callbacks: list[Callable[[list[dict[str, Any]]], None]] = []
        self._discovery._on_change = self._broadcast  # noqa: SLF001

    @property
    def inner(self) -> HardwareDiscoveryService:
        return self._discovery

    def start(self) -> None:
        self._discovery.start()

    def stop(self) -> None:
        self._discovery.stop()

    def list_devices(self) -> list[dict[str, Any]]:
        return [d.to_dict() for d in self._discovery.list_devices()]

    def get_device(self, port: str) -> Optional[dict[str, Any]]:
        device = self._discovery.get_device(port)
        return device.to_dict() if device else None

    def scan_now(self) -> list[dict[str, Any]]:
        return [d.to_dict() for d in self._discovery.scan_once()]

    def subscribe_ws(self, callback: Callable[[list[dict[str, Any]]], None]) -> None:
        if callback not in self._ws_callbacks:
            self._ws_callbacks.append(callback)

    def unsubscribe_ws(self, callback: Callable[[list[dict[str, Any]]], None]) -> None:
        try:
            self._ws_callbacks.remove(callback)
        except ValueError:
            pass

    def _broadcast(self, devices: list[DiscoveredDevice]) -> None:
        payload = [d.to_dict() for d in devices]
        for cb in list(self._ws_callbacks):
            try:
                cb(payload)
            except Exception:
                pass
