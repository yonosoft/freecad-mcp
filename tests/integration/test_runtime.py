from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future
from threading import Lock, Thread, get_ident
from typing import Any, TypeVar, cast
from weakref import WeakMethod

import pytest

from freecad_mcp.application import Application
from freecad_mcp.commands import (
    AddExternalGeometryHandler,
    AddSketchConstraintsHandler,
    AddSketchGeometryHandler,
    AnalyzeSketchHandler,
    ClearSketchConstraintExpressionHandler,
    CreateBodyHandler,
    CreateDocumentHandler,
    CreateSketchCenteredRectangleHandler,
    CreateSketchEquilateralTriangleHandler,
    CreateSketchHandler,
    CreateSketchRectangleHandler,
    CreateSketchRegularPolygonHandler,
    CreateSketchRoundedRectangleHandler,
    CreateSketchSlotHandler,
    ExtendSketchGeometryHandler,
    GetDocumentHandler,
    GetDocumentHistoryHandler,
    GetObjectHandler,
    GetSketchDependenciesHandler,
    GetSketchHandler,
    ListDocumentsHandler,
    ListExternalGeometryHandler,
    ListObjectsHandler,
    ListSketchConstraintExpressionsHandler,
    ListSketchOpenVerticesHandler,
    MirrorSketchHandler,
    RecomputeDocumentHandler,
    RedoDocumentHandler,
    RemoveExternalGeometryHandler,
    RemoveSketchConstraintsHandler,
    RemoveSketchGeometryHandler,
    ReplaceSketchConstraintHandler,
    RotateSketchHandler,
    SaveDocumentHandler,
    ScaleSketchHandler,
    SetSketchConstraintExpressionHandler,
    SetSketchConstraintNameHandler,
    SetSketchGeometryConstructionHandler,
    SplitSketchGeometryHandler,
    TranslateSketchHandler,
    TrimSketchGeometryHandler,
    UndoDocumentHandler,
    UpdateSketchConstraintValueHandler,
    UpdateSketchGeometryHandler,
    ValidateSketchProfileHandler,
)
from freecad_mcp.core.dispatch import MainThreadDispatcher
from freecad_mcp.core.result import CommandResult
from freecad_mcp.runtime import (
    Runtime,
    _build_runtime,
    _post_lifecycle_state,
    get_application,
    get_tool_visibility_controller,
)
from freecad_mcp.server.config import ServerConfig
from freecad_mcp.server.lifecycle import LifecycleService, LifecycleState
from freecad_mcp.visibility.controller import ToolVisibilityController
from tests.support.preference_stubs import InMemoryStringPreferenceStore

T = TypeVar("T")


class DispatcherStub:
    def __init__(self) -> None:
        self.post_calls = 0

    def call(self, operation: Callable[[], T]) -> T:
        return operation()

    def post(self, operation: Callable[[], object]) -> None:
        self.post_calls += 1
        operation()


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
    preference_store = InMemoryStringPreferenceStore()
    monkeypatch.setattr(
        "freecad_mcp.runtime.create_freecad_string_preference_store",
        lambda: preference_store,
    )

    # Prevent LifecycleService from needing a real MCP runner.
    # The runner_factory lambda is never called during _build_runtime.
    monkeypatch.setattr("freecad_mcp.runtime.UvicornMCPRunner", object)

    # Prevent _connect_shutdown from importing PySide.
    def _noop_shutdown(runtime: Any) -> None:
        pass

    monkeypatch.setattr("freecad_mcp.runtime._connect_shutdown", _noop_shutdown)

    runtime = _build_runtime()

    handlers = runtime.application.handlers
    expected_handler_types: dict[str, dict[str, type[object]]] = {
        "document": {
            "create": CreateDocumentHandler,
            "list": ListDocumentsHandler,
            "get": GetDocumentHandler,
            "get_history": GetDocumentHistoryHandler,
            "undo": UndoDocumentHandler,
            "redo": RedoDocumentHandler,
            "save": SaveDocumentHandler,
            "object_query": ListObjectsHandler,
            "get_object": GetObjectHandler,
            "recompute": RecomputeDocumentHandler,
        },
        "part_design": {
            "create_body": CreateBodyHandler,
        },
        "sketcher": {
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
            "add_external_geometry": AddExternalGeometryHandler,
            "list_external_geometry": ListExternalGeometryHandler,
            "remove_external_geometry": RemoveExternalGeometryHandler,
            "get_sketch_dependencies": GetSketchDependenciesHandler,
            "remove_sketch_constraints": RemoveSketchConstraintsHandler,
            "remove_sketch_geometry": RemoveSketchGeometryHandler,
            "set_sketch_geometry_construction": SetSketchGeometryConstructionHandler,
            "update_sketch_geometry": UpdateSketchGeometryHandler,
            "replace_sketch_constraint": ReplaceSketchConstraintHandler,
            "update_sketch_constraint_value": UpdateSketchConstraintValueHandler,
            "trim_sketch_geometry": TrimSketchGeometryHandler,
            "split_sketch_geometry": SplitSketchGeometryHandler,
            "extend_sketch_geometry": ExtendSketchGeometryHandler,
            "set_sketch_constraint_name": SetSketchConstraintNameHandler,
            "set_sketch_constraint_expression": SetSketchConstraintExpressionHandler,
            "clear_sketch_constraint_expression": ClearSketchConstraintExpressionHandler,
            "list_sketch_constraint_expressions": ListSketchConstraintExpressionsHandler,
            "translate_sketch": TranslateSketchHandler,
            "rotate_sketch": RotateSketchHandler,
            "scale_sketch": ScaleSketchHandler,
            "mirror_sketch": MirrorSketchHandler,
        },
    }

    assert len(created_adapters) == 1
    assert dispatcher_factory_calls == 1
    assert isinstance(runtime.tool_visibility, ToolVisibilityController)
    for group_name, expected_group_types in expected_handler_types.items():
        group = getattr(handlers, group_name)
        for name, expected_type in expected_group_types.items():
            handler = getattr(group, name)
            assert isinstance(handler, expected_type)
            assert cast(Any, handler).adapter is created_adapters[0]
            assert cast(Any, handler).dispatcher is dispatcher_stub


def test_runtime_supports_weak_bound_method_used_by_qt_signals() -> None:
    runtime = Runtime(
        application=cast(Application, object()),
        tool_visibility=cast(ToolVisibilityController, object()),
    )

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

    class VisibilityStub:
        def __init__(self) -> None:
            self.shutdown_calls = 0

        def shutdown(self) -> None:
            self.shutdown_calls += 1

    lifecycle = LifecycleStub()
    visibility = VisibilityStub()
    application = cast(Application, ApplicationStub(lifecycle))

    Runtime(application, cast(ToolVisibilityController, visibility)).shutdown()

    assert lifecycle.shutdown_calls == 1
    assert visibility.shutdown_calls == 1


def test_repeated_runtime_access_returns_one_process_owned_controller(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lifecycle = cast(Any, object())
    application = cast(Application, type("ApplicationStub", (), {"lifecycle": lifecycle})())
    controller = cast(ToolVisibilityController, object())
    runtime = Runtime(application, controller)
    monkeypatch.setattr("freecad_mcp.runtime._runtime", runtime)

    assert get_application() is application
    assert get_application() is application
    assert get_tool_visibility_controller() is controller
    assert get_tool_visibility_controller() is controller


class MainThreadQueueExecutor:
    def __init__(self) -> None:
        self.owner_thread_id = get_ident()
        self._lock = Lock()
        self.queued: list[tuple[Callable[[], object], Future[object]]] = []

    def is_target_thread(self) -> bool:
        return get_ident() == self.owner_thread_id

    def submit(self, operation: Callable[[], object]) -> Future[object]:
        future: Future[object] = Future()
        with self._lock:
            self.queued.append((operation, future))
        return future

    def execute_queued(self) -> None:
        assert self.is_target_thread()
        with self._lock:
            queued = tuple(self.queued)
            self.queued.clear()
        for operation, future in queued:
            if not future.set_running_or_notify_cancel():
                continue
            try:
                future.set_result(operation())
            except BaseException as exc:
                future.set_exception(exc)


class VisibilityStateRecorder:
    def __init__(self) -> None:
        self.owner_thread_id = get_ident()
        self.states: list[str] = []

    def on_server_state_changed(self, state: str) -> object:
        assert get_ident() == self.owner_thread_id
        self.states.append(state)
        return object()


class ThreadedExitRunner:
    def __init__(self) -> None:
        self._on_exit: Callable[[BaseException | None], None] | None = None
        self.worker_completed = False

    def start(self, on_exit: Callable[[BaseException | None], None]) -> None:
        self._on_exit = on_exit

    def stop(self) -> None:
        on_exit = self._on_exit
        assert on_exit is not None
        worker = Thread(target=lambda: on_exit(None), daemon=True)
        worker.start()
        worker.join(timeout=0.1)
        self.worker_completed = not worker.is_alive()
        if not self.worker_completed:
            raise RuntimeError("server worker could not finish")

    def exit_from_worker(self, error: BaseException) -> None:
        on_exit = self._on_exit
        assert on_exit is not None
        worker = Thread(target=lambda: on_exit(error), daemon=True)
        worker.start()
        worker.join(timeout=0.1)
        self.worker_completed = not worker.is_alive()


def _threaded_lifecycle_fixture() -> tuple[
    LifecycleService,
    ThreadedExitRunner,
    MainThreadQueueExecutor,
    VisibilityStateRecorder,
]:
    runner = ThreadedExitRunner()
    executor = MainThreadQueueExecutor()
    dispatcher = MainThreadDispatcher(executor, timeout_seconds=1.0)
    recorder = VisibilityStateRecorder()
    lifecycle = LifecycleService(
        ServerConfig(),
        lambda: runner,
        state_callback=lambda state: _post_lifecycle_state(
            dispatcher,
            cast(ToolVisibilityController, recorder),
            state,
        ),
    )
    return lifecycle, runner, executor, recorder


def test_server_thread_exit_during_stop_queues_visibility_without_deadlock() -> None:
    lifecycle, runner, executor, recorder = _threaded_lifecycle_fixture()
    lifecycle.start()

    stopped = lifecycle.stop()

    assert stopped.ok is True
    assert runner.worker_completed is True
    assert lifecycle.state is LifecycleState.STOPPED
    assert recorder.states == ["starting", "running", "stopping"]
    assert len(executor.queued) == 1

    executor.execute_queued()

    assert recorder.states == ["starting", "running", "stopping", "stopped"]
    assert executor.queued == []


def test_unexpected_server_thread_exit_queues_error_without_blocking() -> None:
    lifecycle, runner, executor, recorder = _threaded_lifecycle_fixture()
    lifecycle.start()

    runner.exit_from_worker(RuntimeError("server failed"))

    assert runner.worker_completed is True
    assert lifecycle.state is LifecycleState.ERROR
    assert recorder.states == ["starting", "running"]
    assert len(executor.queued) == 1

    executor.execute_queued()

    assert recorder.states == ["starting", "running", "error"]
