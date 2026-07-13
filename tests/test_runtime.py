from __future__ import annotations

from typing import cast
from weakref import WeakMethod

from freecad_mcp.application import Application
from freecad_mcp.core.result import CommandResult
from freecad_mcp.runtime import Runtime


def test_runtime_supports_weak_bound_method_used_by_qt_signals() -> None:
    runtime = Runtime(application=cast(Application, object()))

    callback = WeakMethod(runtime.shutdown)

    assert callback() is not None


def test_runtime_shutdown_delegates_to_lifecycle_cleanup() -> None:
    class LifecycleStub:
        def __init__(self) -> None:
            self.shutdown_calls = 0

        def shutdown(self) -> CommandResult:
            self.shutdown_calls += 1
            return CommandResult.success("server_stopped", "The MCP server stopped.")

    class ApplicationStub:
        def __init__(self, lifecycle: LifecycleStub) -> None:
            self.lifecycle = lifecycle

    lifecycle = LifecycleStub()
    application = cast(Application, ApplicationStub(lifecycle))

    Runtime(application).shutdown()

    assert lifecycle.shutdown_calls == 1
