from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future

import pytest

from freecad_mcp.core.dispatch import DispatchError, MainThreadDispatcher


class FakeExecutor:
    def __init__(self, on_target_thread: bool) -> None:
        self.on_target_thread = on_target_thread
        self.submissions = 0

    def is_target_thread(self) -> bool:
        return self.on_target_thread

    def submit(self, operation: Callable[[], object]) -> Future[object]:
        self.submissions += 1
        future: Future[object] = Future()
        try:
            future.set_result(operation())
        except BaseException as exc:
            future.set_exception(exc)
        return future


class FailingExecutor(FakeExecutor):
    def submit(self, operation: Callable[[], object]) -> Future[object]:
        raise RuntimeError("queue unavailable")


def test_dispatcher_executes_directly_on_target_thread() -> None:
    executor = FakeExecutor(on_target_thread=True)

    result = MainThreadDispatcher(executor).call(lambda: "direct")

    assert result == "direct"
    assert executor.submissions == 0


def test_dispatcher_delegates_from_another_thread_boundary() -> None:
    executor = FakeExecutor(on_target_thread=False)

    result = MainThreadDispatcher(executor).call(lambda: 42)

    assert result == 42
    assert executor.submissions == 1


def test_dispatcher_propagates_operation_exceptions() -> None:
    executor = FakeExecutor(on_target_thread=False)

    def fail() -> object:
        raise ValueError("operation failed")

    with pytest.raises(ValueError, match="operation failed"):
        MainThreadDispatcher(executor).call(fail)


def test_dispatcher_converts_submission_failure() -> None:
    with pytest.raises(DispatchError, match="queue unavailable"):
        MainThreadDispatcher(FailingExecutor(False)).call(lambda: None)
