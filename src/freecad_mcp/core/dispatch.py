"""Pure-Python boundary for executing work on a target thread."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future, TimeoutError
from typing import Protocol, TypeVar, cast

T = TypeVar("T")


class DispatchError(RuntimeError):
    """Raised when work cannot be delivered to the target thread."""


class TaskExecutor(Protocol):
    """Supplies thread detection and queued task submission."""

    def is_target_thread(self) -> bool:
        """Return whether the caller already runs on the target thread."""

    def submit(self, operation: Callable[[], object]) -> Future[object]:
        """Queue an operation for execution on the target thread."""


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
            raise DispatchError(
                "Timed out waiting for the FreeCAD main thread to execute the operation."
            ) from exc
