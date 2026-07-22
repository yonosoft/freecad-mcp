from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar, cast

import pytest

from freecad_mcp.commands.sketch_topology_editing import (
    ExtendSketchGeometryHandler,
    SplitSketchGeometryHandler,
    TrimSketchGeometryHandler,
)
from freecad_mcp.exceptions import SketchTopologyEditUnsafeError
from freecad_mcp.models import (
    SketchPoint2DInput,
    SketchTopologyEndpoint,
)
from freecad_mcp.protocols import SketchTopologyEditingAdapter

T = TypeVar("T")


class _Dispatcher:
    def call(self, operation: Callable[[], T]) -> T:
        return operation()


@dataclass(frozen=True)
class _Result:
    operation: str
    changed: bool = True

    def to_dict(self) -> dict[str, object]:
        return {
            "operation": self.operation,
            "changed": self.changed,
            "no_change": not self.changed,
        }


class _Adapter:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []
        self.error: Exception | None = None
        self.changed = True

    def _result(self, operation: str) -> _Result:
        if self.error is not None:
            raise self.error
        return _Result(operation, self.changed)

    def trim_sketch_geometry(
        self,
        document_name: str,
        sketch_name: str,
        geometry_index: int,
        pick_point: SketchPoint2DInput,
    ) -> _Result:
        self.calls.append(("trim", document_name, sketch_name, geometry_index, pick_point))
        return self._result("trim")

    def split_sketch_geometry(
        self,
        document_name: str,
        sketch_name: str,
        geometry_index: int,
        point: SketchPoint2DInput,
    ) -> _Result:
        self.calls.append(("split", document_name, sketch_name, geometry_index, point))
        return self._result("split")

    def extend_sketch_geometry(
        self,
        document_name: str,
        sketch_name: str,
        geometry_index: int,
        endpoint: SketchTopologyEndpoint,
        target_point: SketchPoint2DInput,
    ) -> _Result:
        self.calls.append(
            ("extend", document_name, sketch_name, geometry_index, endpoint, target_point)
        )
        return self._result("extend")


def test_handlers_dispatch_exact_typed_topology_requests() -> None:
    adapter = _Adapter()
    typed_adapter = cast(SketchTopologyEditingAdapter, adapter)
    dispatcher = _Dispatcher()

    trim = TrimSketchGeometryHandler(typed_adapter, dispatcher).execute(
        "Model", "Sketch", 2, {"x": 4.0, "y": 0.0}
    )
    split = SplitSketchGeometryHandler(typed_adapter, dispatcher).execute(
        "Model", "Sketch", 3, {"x": 5.0, "y": 1.0}
    )
    extend = ExtendSketchGeometryHandler(typed_adapter, dispatcher).execute(
        "Model", "Sketch", 4, "end", {"x": 12.0, "y": 2.0}
    )

    assert [trim.code, split.code, extend.code] == [
        "sketch_geometry_trimmed",
        "sketch_geometry_split",
        "sketch_geometry_extended",
    ]
    assert adapter.calls[0][:4] == ("trim", "Model", "Sketch", 2)
    assert adapter.calls[1][:4] == ("split", "Model", "Sketch", 3)
    assert adapter.calls[2][:5] == (
        "extend",
        "Model",
        "Sketch",
        4,
        SketchTopologyEndpoint.END,
    )
    assert isinstance(adapter.calls[0][4], SketchPoint2DInput)
    assert isinstance(adapter.calls[1][4], SketchPoint2DInput)
    assert isinstance(adapter.calls[2][5], SketchPoint2DInput)


@pytest.mark.parametrize(
    ("handler", "arguments", "field"),
    [
        (
            TrimSketchGeometryHandler,
            ("Model", "Sketch", True, {"x": 1.0, "y": 0.0}),
            "geometry_index",
        ),
        (
            SplitSketchGeometryHandler,
            ("Model", "Sketch", -1, {"x": 1.0, "y": 0.0}),
            "geometry_index",
        ),
        (
            TrimSketchGeometryHandler,
            ("Model", "Sketch", 0, {"x": "1", "y": 0.0}),
            "pick_point.x",
        ),
        (
            SplitSketchGeometryHandler,
            ("Model", "Sketch", 0, {"x": float("inf"), "y": 0.0}),
            "point.x",
        ),
        (
            ExtendSketchGeometryHandler,
            ("Model", "Sketch", 0, "middle", {"x": 2.0, "y": 0.0}),
            "endpoint",
        ),
        (
            ExtendSketchGeometryHandler,
            ("Model", "Sketch", 0, "start", {"x": 2.0, "y": 0.0, "z": 0.0}),
            "target_point.z",
        ),
    ],
)
def test_handlers_reject_invalid_requests_before_dispatch(
    handler: type[Any],
    arguments: tuple[object, ...],
    field: str,
) -> None:
    adapter = _Adapter()

    result = handler(adapter, _Dispatcher()).execute(*arguments)

    assert result.ok is False
    assert result.code == "validation_error"
    assert result.data["field"] == field
    assert adapter.calls == []


def test_no_change_uses_operation_specific_code() -> None:
    adapter = _Adapter()
    adapter.changed = False

    result = SplitSketchGeometryHandler(
        cast(SketchTopologyEditingAdapter, adapter), _Dispatcher()
    ).execute("Model", "Sketch", 0, {"x": 0.0, "y": 0.0})

    assert result.ok is True
    assert result.code == "sketch_geometry_split_unchanged"
    assert result.data["changed"] is False
    assert result.data["no_change"] is True


def test_unsafe_refusal_preserves_structured_public_reason() -> None:
    adapter = _Adapter()
    adapter.error = SketchTopologyEditUnsafeError(
        operation="trim",
        code="unsupported_geometry_type",
        reason="line_segment_required",
        geometry_index=7,
        details={"geometry_type": "circle"},
    )

    result = TrimSketchGeometryHandler(
        cast(SketchTopologyEditingAdapter, adapter), _Dispatcher()
    ).execute("Model", "Sketch", 7, {"x": 1.0, "y": 2.0})

    assert result.ok is False
    assert result.code == "unsupported_geometry_type"
    assert result.data == {
        "document_name": "Model",
        "sketch_name": "Sketch",
        "operation": "trim",
        "geometry_index": 7,
        "reason": "line_segment_required",
        "geometry_type": "circle",
    }


def test_unexpected_failure_does_not_leak_exception_text() -> None:
    adapter = _Adapter()
    adapter.error = RuntimeError("sensitive native detail")

    result = ExtendSketchGeometryHandler(
        cast(SketchTopologyEditingAdapter, adapter), _Dispatcher()
    ).execute("Model", "Sketch", 0, "end", {"x": 10.0, "y": 0.0})

    assert result.ok is False
    assert result.code == "internal_error"
    assert "sensitive" not in str(result.to_dict())
