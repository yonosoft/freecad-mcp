"""Process-local guard for re-entrant FreeCAD history activity."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, Literal

HistoryActivity = Literal["undo", "redo", "rollback"]

_ACTIVITIES: dict[int, HistoryActivity] = {}


def active_history_activity(document: Any) -> HistoryActivity | None:
    """Return MCP-owned history activity currently running for a document."""
    return _ACTIVITIES.get(id(document))


@contextmanager
def history_activity(document: Any, activity: HistoryActivity) -> Iterator[None]:
    """Make a native undo, redo, or rollback visible to re-entrant MCP calls."""
    document_key = id(document)
    previous = _ACTIVITIES.get(document_key)
    _ACTIVITIES[document_key] = activity
    try:
        yield
    finally:
        if previous is None:
            _ACTIVITIES.pop(document_key, None)
        else:
            _ACTIVITIES[document_key] = previous


__all__ = ["active_history_activity", "history_activity"]
