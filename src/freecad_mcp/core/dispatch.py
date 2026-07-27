"""Pure-Python boundary for executing work on a target thread."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import CancelledError, Future, TimeoutError
from typing import TypeVar, cast

from freecad_mcp.core.logging import get_logger
from freecad_mcp.exceptions import DispatchError as DispatchError
from freecad_mcp.exceptions import DispatchTimeoutError as DispatchTimeoutError
from freecad_mcp.protocols import TaskExecutor as TaskExecutor

T = TypeVar("T")
_LOGGER = get_logger("core.dispatch")


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

    def post(self, operation: Callable[[], object]) -> None:
        """Run directly on the target thread or queue without waiting."""
        if self._executor.is_target_thread():
            self._run_posted(operation)
            return

        try:
            future = self._executor.submit(operation)
        except Exception as exc:
            raise DispatchError(f"Could not queue work on the FreeCAD main thread: {exc}") from exc
        future.add_done_callback(self._observe_posted_future)

    @staticmethod
    def _run_posted(operation: Callable[[], object]) -> None:
        try:
            operation()
        except BaseException as exc:
            _LOGGER.error(
                "Posted FreeCAD main-thread operation failed.",
                exc_info=(type(exc), exc, exc.__traceback__),
            )

    @staticmethod
    def _observe_posted_future(future: Future[object]) -> None:
        try:
            error = future.exception()
        except CancelledError:
            _LOGGER.error("Posted FreeCAD main-thread operation was cancelled.")
            return
        if error is not None:
            _LOGGER.error(
                "Posted FreeCAD main-thread operation failed.",
                exc_info=(type(error), error, error.__traceback__),
            )


__all__ = [
    "DispatchError",
    "DispatchTimeoutError",
    "MainThreadDispatcher",
    "TaskExecutor",
]
