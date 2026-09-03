"""Undo/redo history stack for engineering workspace canvas."""

from __future__ import annotations

from typing import Optional

from .models import WorkspaceSnapshot


class HistoryStack:
    """Bounded undo/redo stack for canvas snapshots."""

    def __init__(self, *, limit: int = 100) -> None:
        self._limit = limit
        self._undo: list[WorkspaceSnapshot] = []
        self._redo: list[WorkspaceSnapshot] = []

    def push(self, snapshot: WorkspaceSnapshot) -> None:
        self._undo.append(snapshot)
        if len(self._undo) > self._limit:
            self._undo.pop(0)
        self._redo.clear()

    def undo(self, current: WorkspaceSnapshot) -> Optional[WorkspaceSnapshot]:
        if not self._undo:
            return None
        self._redo.append(current)
        return self._undo.pop()

    def redo(self, current: WorkspaceSnapshot) -> Optional[WorkspaceSnapshot]:
        if not self._redo:
            return None
        self._undo.append(current)
        return self._redo.pop()

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)
