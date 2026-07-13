from __future__ import annotations

from collections.abc import Callable

from freecad_mcp.server.config import ServerConfig
from freecad_mcp.server.lifecycle import LifecycleService, LifecycleState


class FakeRunner:
    def __init__(
        self,
        start_error: Exception | None = None,
        stop_error: Exception | None = None,
    ) -> None:
        self.start_error = start_error
        self.stop_error = stop_error
        self.start_calls = 0
        self.stop_calls = 0
        self._on_exit: Callable[[BaseException | None], None] | None = None

    def start(self, on_exit: Callable[[BaseException | None], None]) -> None:
        self.start_calls += 1
        if self.start_error is not None:
            raise self.start_error
        self._on_exit = on_exit

    def stop(self) -> None:
        self.stop_calls += 1
        if self.stop_error is not None:
            raise self.stop_error
        if self._on_exit is not None:
            self._on_exit(None)

    def exit(self, error: BaseException | None = None) -> None:
        assert self._on_exit is not None
        self._on_exit(error)


class FakeRunnerFactory:
    def __init__(self, runners: list[FakeRunner] | None = None) -> None:
        self.runners = runners or []
        self.created: list[FakeRunner] = []

    def __call__(self) -> FakeRunner:
        runner = self.runners.pop(0) if self.runners else FakeRunner()
        self.created.append(runner)
        return runner


def test_lifecycle_initial_status_is_stopped_and_structured() -> None:
    lifecycle = LifecycleService(ServerConfig(), FakeRunnerFactory())

    result = lifecycle.status()

    assert result.ok is True
    assert result.data["state"] == "stopped"
    assert result.data["url"] == "http://127.0.0.1:8765/mcp"
    assert result.data["transport"] == "streamable_http"
    assert result.data["tools"] == [
        "create_document",
        "list_documents",
        "get_document",
        "save_document",
    ]
    assert lifecycle.can_start() is True
    assert lifecycle.can_stop() is False


def test_lifecycle_starts_and_stops_one_runner() -> None:
    factory = FakeRunnerFactory()
    lifecycle = LifecycleService(ServerConfig(), factory)

    started = lifecycle.start()
    stopped = lifecycle.stop()

    assert started.ok is True
    assert started.data["state"] == "running"
    assert stopped.ok is True
    assert stopped.data["state"] == "stopped"
    assert len(factory.created) == 1
    assert factory.created[0].start_calls == 1
    assert factory.created[0].stop_calls == 1


def test_duplicate_start_does_not_create_another_runner() -> None:
    factory = FakeRunnerFactory()
    lifecycle = LifecycleService(ServerConfig(), factory)

    lifecycle.start()
    duplicate = lifecycle.start()

    assert duplicate.ok is True
    assert duplicate.code == "server_already_running"
    assert len(factory.created) == 1


def test_duplicate_stop_is_non_fatal() -> None:
    lifecycle = LifecycleService(ServerConfig(), FakeRunnerFactory())

    result = lifecycle.stop()

    assert result.ok is True
    assert result.code == "server_already_stopped"
    assert result.data["state"] == "stopped"


def test_startup_failure_is_structured_and_recoverable() -> None:
    failed = FakeRunner(start_error=RuntimeError("port is busy"))
    recovered = FakeRunner()
    lifecycle = LifecycleService(ServerConfig(), FakeRunnerFactory([failed, recovered]))

    failure = lifecycle.start()
    success = lifecycle.start()

    assert failure.ok is False
    assert failure.code == "server_start_failed"
    assert failure.data["state"] == "error"
    assert failure.data["recoverable"] is True
    assert failure.data["last_error"] == {
        "stage": "startup",
        "type": "RuntimeError",
        "message": "port is busy",
    }
    assert success.ok is True
    assert success.data["state"] == "running"


def test_shutdown_failure_retains_non_recoverable_runner() -> None:
    runner = FakeRunner(stop_error=RuntimeError("shutdown timed out"))
    lifecycle = LifecycleService(ServerConfig(), FakeRunnerFactory([runner]))
    lifecycle.start()

    result = lifecycle.stop()

    assert result.ok is False
    assert result.code == "server_stop_failed"
    assert result.data["state"] == "error"
    assert result.data["recoverable"] is False
    assert lifecycle.can_start() is False


def test_unexpected_runner_exit_moves_lifecycle_to_recoverable_error() -> None:
    runner = FakeRunner()
    lifecycle = LifecycleService(ServerConfig(), FakeRunnerFactory([runner]))
    lifecycle.start()

    runner.exit(RuntimeError("event loop failed"))
    status = lifecycle.status()

    assert lifecycle.state is LifecycleState.ERROR
    assert status.data["recoverable"] is True
    assert status.data["last_error"] == {
        "stage": "runtime",
        "type": "RuntimeError",
        "message": "event loop failed",
    }
