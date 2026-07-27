"""Thread-safe lifecycle ownership for the embedded MCP server."""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum
from threading import RLock

from freecad_mcp.core.logging import get_logger
from freecad_mcp.core.result import CommandResult
from freecad_mcp.protocols import RunnerFactory as RunnerFactory
from freecad_mcp.protocols import ServerRunner as ServerRunner
from freecad_mcp.server.config import ServerConfig
from freecad_mcp.tool_registry import REGISTERED_TOOL_NAMES

_LOGGER = get_logger("server.lifecycle")


class LifecycleState(StrEnum):
    """Public server lifecycle states."""

    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"


class LifecycleService:
    """Own exactly one runner and expose structured lifecycle operations."""

    def __init__(
        self,
        config: ServerConfig,
        runner_factory: RunnerFactory,
        state_callback: Callable[[LifecycleState], None] | None = None,
    ) -> None:
        self._config = config
        self._runner_factory = runner_factory
        self._state_callback = state_callback
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
        self._notify_state(LifecycleState.STARTING)

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
                result = self._success("server_started", "The MCP server started.")
                notify_running = True
            else:
                result = self._failure(
                    "server_start_failed", "The MCP server exited before startup completed."
                )
                notify_running = False
        if notify_running:
            self._notify_state(LifecycleState.RUNNING)
        return result

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

        self._notify_state(LifecycleState.STOPPING)
        return self._stop_owned_runner(runner)

    def shutdown(self) -> CommandResult:
        """Best-effort cleanup of any runner still owned during process exit."""
        with self._lock:
            runner = self._runner
            if runner is None:
                changed = self._state is not LifecycleState.STOPPED
                self._state = LifecycleState.STOPPED
                self._last_error = None
                result = self._success("server_already_stopped", "The MCP server is stopped.")
                if not changed:
                    return result
            else:
                if self._state is LifecycleState.STOPPING:
                    return self._success("server_stopping", "The MCP server is already stopping.")
                self._state = LifecycleState.STOPPING
                result = None

        if runner is None:
            self._notify_state(LifecycleState.STOPPED)
            assert result is not None
            return result
        self._notify_state(LifecycleState.STOPPING)
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
                result = self._failure(
                    "server_stop_failed", "The MCP server could not stop cleanly."
                )
            self._notify_state(LifecycleState.ERROR)
            return result

        with self._lock:
            changed = self._state is not LifecycleState.STOPPED
            if self._runner is runner:
                self._runner = None
            self._state = LifecycleState.STOPPED
            self._last_error = None
            result = self._success("server_stopped", "The MCP server stopped.")
        if changed:
            self._notify_state(LifecycleState.STOPPED)
        return result

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
            result = self._failure("server_start_failed", "The MCP server could not start.")
        self._notify_state(LifecycleState.ERROR)
        return result

    def _on_runner_exit(self, runner: ServerRunner, error: BaseException | None) -> None:
        with self._lock:
            if self._runner is not runner:
                return
            self._runner = None
            if self._state is LifecycleState.STOPPING:
                self._state = LifecycleState.STOPPED
                state = LifecycleState.STOPPED
            else:
                self._state = LifecycleState.ERROR
                self._last_error = {
                    "stage": "runtime",
                    "type": type(error).__name__ if error is not None else "UnexpectedExit",
                    "message": (
                        str(error) if error is not None else "Server runner exited unexpectedly."
                    ),
                }
                state = LifecycleState.ERROR
        self._notify_state(state)

    def _notify_state(self, state: LifecycleState) -> None:
        callback = self._state_callback
        if callback is None:
            return
        try:
            callback(state)
        except Exception:
            _LOGGER.exception("MCP lifecycle state callback failed.")

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


__all__ = [
    "LifecycleService",
    "LifecycleState",
    "RunnerFactory",
    "ServerRunner",
]
