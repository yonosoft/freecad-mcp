from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar, cast

import pytest

from freecad_mcp.commands.sketch_query import GetSketchHandler
from freecad_mcp.exceptions import (
    DispatchError,
    DocumentNotFoundError,
    ObjectNotFoundError,
    SketchConstraintMalformedError,
    SketchGeometryMalformedError,
    SketchInspectionError,
    SketchTypeMismatchError,
)
from freecad_mcp.models import SketchInspectionResult, SketchSolverData
from freecad_mcp.protocols import Dispatcher, DocumentAdapter

T = TypeVar("T")


def _result() -> SketchInspectionResult:
    return SketchInspectionResult(
        name="BaseSketch",
        label="Base Sketch",
        body_name="Body",
        visibility=True,
        map_mode="deactivated",
        attachment=None,
        placement=None,
        geometry_count=0,
        external_geometry_count=0,
        constraint_count=0,
        geometry=(),
        constraints=(),
        solver=SketchSolverData(
            available=True,
            fresh=False,
            degrees_of_freedom=None,
            fully_constrained=None,
            conflicting_constraint_indices=None,
            redundant_constraint_indices=None,
            partially_redundant_constraint_indices=None,
            malformed_constraint_indices=None,
        ),
    )


class AdapterStub:
    def __init__(self, error: BaseException | None = None) -> None:
        self.error = error
        self.calls: list[tuple[str, str]] = []

    def get_sketch(self, document_name: str, sketch_name: str) -> SketchInspectionResult:
        self.calls.append((document_name, sketch_name))
        if self.error is not None:
            raise self.error
        return _result()


class DispatcherStub:
    def __init__(self, error: BaseException | None = None) -> None:
        self.error = error
        self.calls = 0

    def call(self, operation: Callable[[], T]) -> T:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return operation()


def _handler(
    *, adapter_error: BaseException | None = None, dispatch_error: BaseException | None = None
) -> tuple[GetSketchHandler, AdapterStub, DispatcherStub]:
    adapter = AdapterStub(adapter_error)
    dispatcher = DispatcherStub(dispatch_error)
    return (
        GetSketchHandler(
            adapter=cast(DocumentAdapter, adapter),
            dispatcher=cast(Dispatcher, dispatcher),
        ),
        adapter,
        dispatcher,
    )


def test_get_sketch_returns_approved_outer_shape() -> None:
    handler, adapter, dispatcher = _handler()

    result = handler.execute("TestDocument", "BaseSketch")

    assert result.to_dict() == {
        "ok": True,
        "code": "sketch_retrieved",
        "document_name": "TestDocument",
        "sketch": {
            "name": "BaseSketch",
            "label": "Base Sketch",
            "body_name": "Body",
            "visibility": True,
            "units": {"length": "millimeter", "angle": "degree"},
            "map_mode": "deactivated",
            "attachment": None,
            "placement": None,
            "geometry_count": 0,
            "external_geometry_count": 0,
            "unsupported_geometry_count": 0,
            "constraint_count": 0,
            "unsupported_constraint_count": 0,
            "geometry": [],
            "constraints": [],
            "solver": {
                "available": True,
                "fresh": False,
                "degrees_of_freedom": None,
                "fully_constrained": None,
                "conflicting_constraint_indices": None,
                "redundant_constraint_indices": None,
                "partially_redundant_constraint_indices": None,
                "malformed_constraint_indices": None,
            },
        },
        "message": "FreeCAD sketch retrieved.",
    }
    assert adapter.calls == [("TestDocument", "BaseSketch")]
    assert dispatcher.calls == 1


@pytest.mark.parametrize(
    ("error", "expected_code", "index_field", "index_value"),
    [
        (DocumentNotFoundError(), "document_not_found", None, None),
        (ObjectNotFoundError(), "sketch_not_found", None, None),
        (SketchTypeMismatchError(), "sketch_type_mismatch", None, None),
        (
            SketchGeometryMalformedError(index=2, reason="invalid_radius"),
            "sketch_geometry_malformed",
            "geometry_index",
            2,
        ),
        (
            SketchConstraintMalformedError(index=3, reason="reference_unreadable"),
            "sketch_constraint_malformed",
            "constraint_index",
            3,
        ),
        (SketchInspectionError("freecad_api_failure"), "sketch_inspection_failed", None, None),
    ],
)
def test_get_sketch_maps_controlled_adapter_errors(
    error: BaseException,
    expected_code: str,
    index_field: str | None,
    index_value: int | None,
) -> None:
    handler, _, _ = _handler(adapter_error=error)

    result = handler.execute("TestDocument", "BaseSketch")

    assert result.ok is False
    assert result.code == expected_code
    if index_field is not None:
        assert result.data[index_field] == index_value


def test_get_sketch_maps_dispatch_failure_to_public_inspection_code() -> None:
    handler, adapter, _ = _handler(dispatch_error=DispatchError("queue unavailable"))

    result = handler.execute("TestDocument", "BaseSketch")

    assert result.ok is False
    assert result.code == "sketch_inspection_failed"
    assert adapter.calls == []


def test_get_sketch_reuses_exact_name_validation_before_dispatch() -> None:
    handler, adapter, dispatcher = _handler()

    result = handler.execute("TestDocument", "Base Sketch")

    assert result.ok is False
    assert result.code == "validation_error"
    assert adapter.calls == []
    assert dispatcher.calls == 0
