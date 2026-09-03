"""Undo/redo history for wire connections."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Optional

ActionKind = Literal["create", "delete", "update"]


@dataclass
class HistoryEntry:
    action: ActionKind
    connection: dict[str, Any]
    previous: Optional[dict[str, Any]] = None


@dataclass
class ConnectionHistory:
    """Simple stack-based history for wire create/delete/update."""

    max_size: int = 100
    _undo: list[HistoryEntry] = field(default_factory=list)
    _redo: list[HistoryEntry] = field(default_factory=list)

    def record_create(self, connection: dict[str, Any]) -> None:
        self._undo.append(HistoryEntry(action="create", connection=dict(connection)))
        self._redo.clear()
        self._trim()

    def record_delete(self, connection: dict[str, Any]) -> None:
        self._undo.append(HistoryEntry(action="delete", connection=dict(connection)))
        self._redo.clear()
        self._trim()

    def record_update(self, before: dict[str, Any], after: dict[str, Any]) -> None:
        self._undo.append(
            HistoryEntry(action="update", connection=dict(after), previous=dict(before))
        )
        self._redo.clear()
        self._trim()

    def pop_undo(self) -> Optional[HistoryEntry]:
        if not self._undo:
            return None
        entry = self._undo.pop()
        self._redo.append(entry)
        return entry

    def pop_redo(self) -> Optional[HistoryEntry]:
        if not self._redo:
            return None
        entry = self._redo.pop()
        self._undo.append(entry)
        return entry

    def clear(self) -> None:
        self._undo.clear()
        self._redo.clear()

    def _trim(self) -> None:
        if len(self._undo) > self.max_size:
            self._undo = self._undo[-self.max_size :]
