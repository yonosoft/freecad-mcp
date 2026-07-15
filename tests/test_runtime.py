from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar, cast
from weakref import WeakMethod

import pytest

from freecad_mcp.application import Application
from freecad_mcp.commands.sketch import CreateSketchHandler
from freecad_mcp.core.result import CommandResult
from freecad_mcp.runtime import Runtime, _build_runtime

T = TypeVar("T")


class DispatcherStub:
    def call(self, operation: Callable[[], T]) -> T:
        return operation()


def test_build_runtime_wires_create_sketch_handler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Call _build_runtime with patched FreeCAD boundary dependencies and
    verify the resulting runtime includes a CreateSketchHandler."""

    # Prevent creation of real FreeCAD adapter.
    class AdapterStub:
        pass

    monkeypatch.setattr("freecad_mcp.runtime.FreeCADDocumentAdapter", AdapterStub)

    # Prevent real Qt dispatcher creation.
    dispatcher_stub = DispatcherStub()

    def _fake_dispatcher() -> DispatcherStub:
        return dispatcher_stub

    monkeypatch.setattr("freecad_mcp.runtime.create_qt_main_thread_dispatcher", _fake_dispatcher)

    # Prevent LifecycleService from needing a real MCP runner.
    # The runner_factory lambda is never called during _build_runtime.
    monkeypatch.setattr("freecad_mcp.runtime.UvicornMCPRunner", object)

    # Prevent _connect_shutdown from importing PySide.
    def _noop_shutdown(runtime: Any) -> None:
        pass

    monkeypatch.setattr("freecad_mcp.runtime._connect_shutdown", _noop_shutdown)

    runtime = _build_runtime()

    handlers = runtime.application.documents
    assert isinstance(handlers.create_sketch, CreateSketchHandler)
    assert handlers.create_sketch is not None


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
