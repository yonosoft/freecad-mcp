from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future

import pytest

from freecad_mcp.core.dispatch import (
    DispatchError,
    DispatchTimeoutError,
    MainThreadDispatcher,
)


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


class QueuedExecutor:
    def __init__(self, *, already_running: bool = False) -> None:
        self.future: Future[object] = Future()
        self.operation: Callable[[], object] | None = None
        self.already_running = already_running

    def is_target_thread(self) -> bool:
        return False

    def submit(self, operation: Callable[[], object]) -> Future[object]:
        self.operation = operation
        if self.already_running:
            assert self.future.set_running_or_notify_cancel()
        return self.future

    def execute_queued(self) -> None:
        assert self.operation is not None
        if not self.future.set_running_or_notify_cancel():
            return
        try:
            self.future.set_result(self.operation())
        except BaseException as exc:
            self.future.set_exception(exc)


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


def test_dispatcher_timeout_cancels_work_that_has_not_started() -> None:
    executor = QueuedExecutor()

    with pytest.raises(DispatchTimeoutError) as raised:
        MainThreadDispatcher(executor, timeout_seconds=0.001).call(lambda: None)

    assert raised.value.cancelled_before_start is True
    assert raised.value.operation_may_complete is False
    assert raised.value.details()["cancelled_before_start"] is True
    assert executor.future.cancelled() is True


def test_cancelled_queued_work_is_skipped_when_delivered_later() -> None:
    executor = QueuedExecutor()
    calls = 0

    def operation() -> None:
        nonlocal calls
        calls += 1

    with pytest.raises(DispatchTimeoutError):
        MainThreadDispatcher(executor, timeout_seconds=0.001).call(operation)

    executor.execute_queued()

    assert calls == 0


def test_dispatcher_reports_when_timed_out_work_already_started() -> None:
    executor = QueuedExecutor(already_running=True)

    with pytest.raises(DispatchTimeoutError) as raised:
        MainThreadDispatcher(executor, timeout_seconds=0.001).call(lambda: None)

    assert raised.value.cancelled_before_start is False
    assert raised.value.operation_may_complete is True
    assert raised.value.details()["operation_may_complete"] is True
    assert executor.future.cancelled() is False
