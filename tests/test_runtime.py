from __future__ import annotations

from typing import cast
from weakref import WeakMethod

from freecad_mcp.application import Application
from freecad_mcp.runtime import Runtime


def test_runtime_supports_weak_bound_method_used_by_qt_signals() -> None:
    runtime = Runtime(application=cast(Application, object()))

    callback = WeakMethod(runtime.shutdown)

    assert callback() is not None
