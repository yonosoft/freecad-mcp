"""Thread-safe lifecycle ownership for the embedded MCP server."""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum
from threading import RLock
from typing import Protocol

from freecad_mcp.core.result import CommandResult
from freecad_mcp.server.config import ServerConfig
from freecad_mcp.tool_registry import REGISTERED_TOOL_NAMES


class LifecycleState(StrEnum):
    """Public server lifecycle states."""

    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"


class ServerRunner(Protocol):
    """Background transport runner controlled by the lifecycle service."""

    def start(self, on_exit: Callable[[BaseException | None], None]) -> None:
        """Start and report unexpected or requested transport exit."""

    def stop(self) -> None:
        """Request graceful shutdown and wait for runner exit."""


RunnerFactory = Callable[[], ServerRunner]


class LifecycleService:
    """Own exactly one runner and expose structured lifecycle operations."""

    def __init__(self, config: ServerConfig, runner_factory: RunnerFactory) -> None:
        self._config = config
        self._runner_factory = runner_factory
        self._lock = RLock()
        self._state = LifecycleState.STOPPED
        self._runner: ServerRunner | None = None
        self._last_error: dict[str, object] | None = None

    @property
    def state(self) -> LifecycleState:
        """Return the current lifecycle state."""
        with self._lock:
            return self._state

    def can_start(self) -> bool:
        """Return whether a start attempt is currently safe."""
        with self._lock:
            return self._state is LifecycleState.STOPPED or (
                self._state is LifecycleState.ERROR and self._runner is None
            )

    def can_stop(self) -> bool:
        """Return whether the active runner can currently be stopped."""
        with self._lock:
            return self._state is LifecycleState.RUNNING

    def start(self) -> CommandResult:
        """Start one server runner, handling duplicate and failed starts."""
        with self._lock:
            if self._state is LifecycleState.RUNNING:
                return self._success("server_already_running", "The MCP server is already running.")
            if self._state is LifecycleState.STARTING:
                return self._success("server_starting", "The MCP server is already starting.")
            if self._state in (LifecycleState.STOPPING,):
                return self._failure(
                    "lifecycle_conflict", "The MCP server cannot start while it is stopping."
                )
            if self._state is LifecycleState.ERROR and self._runner is not None:
                return self._failure(
                    "server_not_recoverable",
                    "The MCP server still owns a failed runner and cannot restart safely.",
                )
            self._state = LifecycleState.STARTING
            self._last_error = None

        try:
            runner = self._runner_factory()
        except Exception as exc:
            return self._record_start_failure(exc)

        with self._lock:
            if self._state is not LifecycleState.STARTING:
                return self._failure("server_start_failed", "Server shutdown interrupted startup.")
            self._runner = runner

        try:
            runner.start(lambda error: self._on_runner_exit(runner, error))
        except Exception as exc:
            return self._record_start_failure(exc, runner)

        with self._lock:
            if self._runner is runner and self._state is LifecycleState.STARTING:
                self._state = LifecycleState.RUNNING
                return self._success("server_started", "The MCP server started.")
            return self._failure(
                "server_start_failed", "The MCP server exited before startup completed."
            )

    def stop(self) -> CommandResult:
        """Gracefully stop the active runner and handle duplicate stops."""
        with self._lock:
            if self._state is LifecycleState.STOPPED:
                return self._success("server_already_stopped", "The MCP server is already stopped.")
            if self._state is LifecycleState.STOPPING:
                return self._success("server_stopping", "The MCP server is already stopping.")
            if self._state is not LifecycleState.RUNNING or self._runner is None:
                return self._failure(
                    "lifecycle_conflict", f"The MCP server cannot stop from state '{self._state}'."
                )
            runner = self._runner
            self._state = LifecycleState.STOPPING

        return self._stop_owned_runner(runner)

    def shutdown(self) -> CommandResult:
        """Best-effort cleanup of any runner still owned during process exit."""
        with self._lock:
            runner = self._runner
            if runner is None:
                self._state = LifecycleState.STOPPED
                self._last_error = None
                return self._success("server_already_stopped", "The MCP server is stopped.")
            if self._state is LifecycleState.STOPPING:
                return self._success("server_stopping", "The MCP server is already stopping.")
            self._state = LifecycleState.STOPPING

        return self._stop_owned_runner(runner)

    def _stop_owned_runner(self, runner: ServerRunner) -> CommandResult:
        try:
            runner.stop()
        except Exception as exc:
            with self._lock:
                self._state = LifecycleState.ERROR
                self._last_error = {
                    "stage": "shutdown",
                    "type": type(exc).__name__,
                    "message": str(exc),
                }
            return self._failure("server_stop_failed", "The MCP server could not stop cleanly.")

        with self._lock:
            if self._runner is runner:
                self._runner = None
            self._state = LifecycleState.STOPPED
            self._last_error = None
            return self._success("server_stopped", "The MCP server stopped.")

    def status(self) -> CommandResult:
        """Return the current state and endpoint configuration."""
        with self._lock:
            return self._success("server_status", "MCP server status reported.")

    def _record_start_failure(
        self, exc: Exception, runner: ServerRunner | None = None
    ) -> CommandResult:
        cleanup_error: Exception | None = None
        if runner is not None:
            with self._lock:
                owns_runner = self._runner is runner
            if owns_runner:
                try:
                    runner.stop()
                except Exception as stop_exc:
                    cleanup_error = stop_exc

        with self._lock:
            if runner is None or (self._runner is runner and cleanup_error is None):
                self._runner = None
            self._state = LifecycleState.ERROR
            self._last_error = {
                "stage": "startup",
                "type": type(exc).__name__,
                "message": str(exc),
            }
            if cleanup_error is not None:
                self._last_error["cleanup_error"] = {
                    "type": type(cleanup_error).__name__,
                    "message": str(cleanup_error),
                }
            return self._failure("server_start_failed", "The MCP server could not start.")

    def _on_runner_exit(self, runner: ServerRunner, error: BaseException | None) -> None:
        with self._lock:
            if self._runner is not runner:
                return
            self._runner = None
            if self._state is LifecycleState.STOPPING:
                self._state = LifecycleState.STOPPED
                return

            self._state = LifecycleState.ERROR
            self._last_error = {
                "stage": "runtime",
                "type": type(error).__name__ if error is not None else "UnexpectedExit",
                "message": (
                    str(error) if error is not None else "Server runner exited unexpectedly."
                ),
            }

    def _data(self) -> dict[str, object]:
        data = {
            "state": self._state.value,
            **self._config.as_dict(),
            "tools": list(REGISTERED_TOOL_NAMES),
            "recoverable": self._state is not LifecycleState.ERROR or self._runner is None,
        }
        if self._last_error is not None:
            data["last_error"] = dict(self._last_error)
        return data

    def _success(self, code: str, message: str) -> CommandResult:
        return CommandResult.success(code=code, message=message, data=self._data())

    def _failure(self, code: str, message: str) -> CommandResult:
        return CommandResult.failure(code=code, message=message, data=self._data())
