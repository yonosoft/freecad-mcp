"""Pure-Python boundary for executing work on a target thread."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import TimeoutError
from typing import TypeVar, cast

from freecad_mcp.exceptions import DispatchError as DispatchError
from freecad_mcp.exceptions import DispatchTimeoutError as DispatchTimeoutError
from freecad_mcp.protocols import TaskExecutor as TaskExecutor

T = TypeVar("T")


class MainThreadDispatcher:
    """Execute directly on the target thread or wait for queued execution."""

    def __init__(self, executor: TaskExecutor, timeout_seconds: float = 30.0) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._executor = executor
        self._timeout_seconds = timeout_seconds

    def call(self, operation: Callable[[], T]) -> T:
        """Run an operation on the configured target thread."""
        if self._executor.is_target_thread():
            return operation()

        try:
            future = self._executor.submit(cast(Callable[[], object], operation))
        except Exception as exc:
            raise DispatchError(f"Could not queue work on the FreeCAD main thread: {exc}") from exc

        try:
            return cast(T, future.result(timeout=self._timeout_seconds))
        except TimeoutError as exc:
            if future.done():
                return cast(T, future.result())
            raise DispatchTimeoutError(cancelled_before_start=future.cancel()) from exc


__all__ = [
    "DispatchError",
    "DispatchTimeoutError",
    "MainThreadDispatcher",
    "TaskExecutor",
]
