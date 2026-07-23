"""Qt queued-signal adapter for FreeCAD main-thread execution."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future
from typing import Any

from freecad_mcp.core.dispatch import MainThreadDispatcher


def create_qt_main_thread_dispatcher() -> MainThreadDispatcher:
    """Create a dispatcher owned by the current FreeCAD GUI thread."""
    from PySide import QtCore  # type: ignore[import-not-found]

    application = QtCore.QCoreApplication.instance()
    if application is None:
        raise RuntimeError("FreeCAD's Qt application is not available.")
    if QtCore.QThread.currentThread() != application.thread():
        raise RuntimeError("The MCP runtime must be initialized on FreeCAD's main Qt thread.")

    executor = _create_qt_executor(QtCore, application)
    return MainThreadDispatcher(executor)


def _create_qt_executor(QtCore: Any, application: Any) -> Any:
    class QtTaskExecutor(QtCore.QObject):  # type: ignore[misc]
        dispatch_requested = QtCore.Signal(object)

        def __init__(self) -> None:
            super().__init__(application)
            connection_type = QtCore.Qt.ConnectionType.QueuedConnection
            self.dispatch_requested.connect(self._execute, connection_type)

        def is_target_thread(self) -> bool:
            return bool(QtCore.QThread.currentThread() == self.thread())

        def submit(self, operation: Callable[[], object]) -> Future[object]:
            future: Future[object] = Future()
            self.dispatch_requested.emit((operation, future))
            return future

        @QtCore.Slot(object)  # type: ignore[misc]
        def _execute(self, payload: tuple[Callable[[], object], Future[object]]) -> None:
            operation, future = payload
            if not future.set_running_or_notify_cancel():
                return
            try:
                future.set_result(operation())
            except BaseException as exc:
                future.set_exception(exc)

    return QtTaskExecutor()
