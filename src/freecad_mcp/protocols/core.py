"""Coherent core protocols definitions."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future
from typing import Protocol, TypeVar

T = TypeVar("T")


class Dispatcher(Protocol):
    """Execution boundary used to reach FreeCAD's main thread."""

    def call(self, operation: Callable[[], T]) -> T:
        """Execute a document operation on the target thread."""


class TaskExecutor(Protocol):
    """Supplies thread detection and queued task submission."""

    def is_target_thread(self) -> bool:
        """Return whether the caller already runs on the target thread."""

    def submit(self, operation: Callable[[], object]) -> Future[object]:
        """Queue an operation for execution on the target thread."""
