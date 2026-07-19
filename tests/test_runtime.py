from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar, cast
from weakref import WeakMethod

import pytest

from freecad_mcp.application import Application
from freecad_mcp.commands import (
    AddSketchConstraintsHandler,
    AddSketchGeometryHandler,
    AnalyzeSketchHandler,
    CreateBodyHandler,
    CreateDocumentHandler,
    CreateSketchCenteredRectangleHandler,
    CreateSketchEquilateralTriangleHandler,
    CreateSketchHandler,
    CreateSketchRectangleHandler,
    CreateSketchRegularPolygonHandler,
    CreateSketchRoundedRectangleHandler,
    CreateSketchSlotHandler,
    GetDocumentHandler,
    GetDocumentHistoryHandler,
    GetObjectHandler,
    GetSketchHandler,
    ListDocumentsHandler,
    ListObjectsHandler,
    ListSketchOpenVerticesHandler,
    RecomputeDocumentHandler,
    RedoDocumentHandler,
    SaveDocumentHandler,
    UndoDocumentHandler,
    ValidateSketchProfileHandler,
)
from freecad_mcp.core.result import CommandResult
from freecad_mcp.runtime import Runtime, _build_runtime

T = TypeVar("T")


class DispatcherStub:
    def call(self, operation: Callable[[], T]) -> T:
        return operation()


def test_build_runtime_wires_create_sketch_handler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify runtime owns one adapter and dispatcher shared by every handler."""

    created_adapters: list[object] = []

    class AdapterStub:
        def __init__(self) -> None:
            created_adapters.append(self)

    monkeypatch.setattr("freecad_mcp.runtime.FreeCADDocumentAdapter", AdapterStub)

    # Prevent real Qt dispatcher creation.
    dispatcher_stub = DispatcherStub()
    dispatcher_factory_calls = 0

    def _fake_dispatcher() -> DispatcherStub:
        nonlocal dispatcher_factory_calls
        dispatcher_factory_calls += 1
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
    expected_handler_types = {
        "create": CreateDocumentHandler,
        "list": ListDocumentsHandler,
        "get": GetDocumentHandler,
        "get_history": GetDocumentHistoryHandler,
        "undo": UndoDocumentHandler,
        "redo": RedoDocumentHandler,
        "save": SaveDocumentHandler,
        "object_query": ListObjectsHandler,
        "get_object": GetObjectHandler,
        "create_body": CreateBodyHandler,
        "create_sketch": CreateSketchHandler,
        "get_sketch": GetSketchHandler,
        "analyze_sketch": AnalyzeSketchHandler,
        "validate_sketch_profile": ValidateSketchProfileHandler,
        "list_sketch_open_vertices": ListSketchOpenVerticesHandler,
        "add_sketch_geometry": AddSketchGeometryHandler,
        "add_sketch_constraints": AddSketchConstraintsHandler,
        "create_sketch_rectangle": CreateSketchRectangleHandler,
        "create_sketch_centered_rectangle": CreateSketchCenteredRectangleHandler,
        "create_sketch_equilateral_triangle": CreateSketchEquilateralTriangleHandler,
        "create_sketch_regular_polygon": CreateSketchRegularPolygonHandler,
        "create_sketch_slot": CreateSketchSlotHandler,
        "create_sketch_rounded_rectangle": CreateSketchRoundedRectangleHandler,
        "recompute": RecomputeDocumentHandler,
    }

    assert len(created_adapters) == 1
    assert dispatcher_factory_calls == 1
    for name, expected_type in expected_handler_types.items():
        handler = getattr(handlers, name)
        assert isinstance(handler, expected_type)
        assert cast(Any, handler).adapter is created_adapters[0]
        assert cast(Any, handler).dispatcher is dispatcher_stub


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
