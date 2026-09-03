"""Connection graph — traversal, path highlight, connected components."""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Iterable, Optional

from .pin_connection import PinConnection


class ConnectionGraph:
    """Undirected multigraph of pin endpoints linked by PinConnections."""

    def __init__(self) -> None:
        self._adj: dict[str, set[str]] = defaultdict(set)
        self._edge_ids: dict[tuple[str, str], set[str]] = defaultdict(set)
        self._connections: dict[str, PinConnection] = {}

    def clear(self) -> None:
        self._adj.clear()
        self._edge_ids.clear()
        self._connections.clear()

    def add_connection(self, conn: PinConnection) -> None:
        a, b = conn.endpoints()
        self._connections[conn.connection_id] = conn
        self._adj[a].add(b)
        self._adj[b].add(a)
        key = self._edge_key(a, b)
        self._edge_ids[key].add(conn.connection_id)

    def remove_connection(self, connection_id: str) -> Optional[PinConnection]:
        conn = self._connections.pop(connection_id, None)
        if conn is None:
            return None
        a, b = conn.endpoints()
        key = self._edge_key(a, b)
        ids = self._edge_ids.get(key)
        if ids:
            ids.discard(connection_id)
            if not ids:
                self._edge_ids.pop(key, None)
                self._adj[a].discard(b)
                self._adj[b].discard(a)
                if not self._adj[a]:
                    self._adj.pop(a, None)
                if not self._adj[b]:
                    self._adj.pop(b, None)
        return conn

    def get(self, connection_id: str) -> Optional[PinConnection]:
        return self._connections.get(connection_id)

    def all_connections(self) -> list[PinConnection]:
        return list(self._connections.values())

    def connections_for_device(self, device_id: str) -> list[PinConnection]:
        return [
            c
            for c in self._connections.values()
            if c.source_device == device_id or c.destination_device == device_id
        ]

    def connections_for_pin(self, device_id: str, pin: str) -> list[PinConnection]:
        key = f"{device_id}:{pin}"
        return [c for c in self._connections.values() if key in c.endpoints()]

    def neighbors(self, device_id: str, pin: str) -> list[str]:
        return sorted(self._adj.get(f"{device_id}:{pin}", set()))

    def find_connected_components(self) -> list[list[str]]:
        seen: set[str] = set()
        components: list[list[str]] = []
        for node in list(self._adj.keys()):
            if node in seen:
                continue
            comp: list[str] = []
            q = deque([node])
            seen.add(node)
            while q:
                cur = q.popleft()
                comp.append(cur)
                for nxt in self._adj.get(cur, set()):
                    if nxt not in seen:
                        seen.add(nxt)
                        q.append(nxt)
            components.append(sorted(comp))
        return components

    def trace_signal_path(
        self,
        start_device: str,
        start_pin: str,
        end_device: str = "",
        end_pin: str = "",
        *,
        max_depth: int = 32,
    ) -> list[str]:
        """BFS path of endpoint keys. If end omitted, returns BFS order from start."""
        start = f"{start_device}:{start_pin}"
        if start not in self._adj and not end_device:
            return [start] if start else []
        goal = f"{end_device}:{end_pin}" if end_device and end_pin else ""
        parent: dict[str, Optional[str]] = {start: None}
        q = deque([start])
        visited = {start}
        order: list[str] = []
        while q and len(order) < max_depth:
            cur = q.popleft()
            order.append(cur)
            if goal and cur == goal:
                return self._reconstruct(parent, goal)
            for nxt in self._adj.get(cur, set()):
                if nxt not in visited:
                    visited.add(nxt)
                    parent[nxt] = cur
                    q.append(nxt)
        if goal:
            return self._reconstruct(parent, goal) if goal in parent else []
        return order

    def highlight_path(
        self,
        start_device: str,
        start_pin: str,
        end_device: str,
        end_pin: str,
    ) -> dict:
        path = self.trace_signal_path(start_device, start_pin, end_device, end_pin)
        connection_ids: list[str] = []
        for i in range(len(path) - 1):
            key = self._edge_key(path[i], path[i + 1])
            connection_ids.extend(sorted(self._edge_ids.get(key, set())))
        return {
            "path": path,
            "connection_ids": connection_ids,
            "nodes": path,
            "wires": connection_ids,
        }

    def load(self, connections: Iterable[PinConnection]) -> None:
        self.clear()
        for c in connections:
            self.add_connection(c)

    @staticmethod
    def _edge_key(a: str, b: str) -> tuple[str, str]:
        return (a, b) if a <= b else (b, a)

    @staticmethod
    def _reconstruct(parent: dict[str, Optional[str]], goal: str) -> list[str]:
        if goal not in parent:
            return []
        path: list[str] = []
        cur: Optional[str] = goal
        while cur is not None:
            path.append(cur)
            cur = parent.get(cur)
        path.reverse()
        return path
