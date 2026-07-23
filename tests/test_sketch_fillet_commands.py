"""Focused tests for the fillet command handler and validation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar, cast

from freecad_mcp.commands.sketch_fillet import FilletSketchGeometryHandler
from freecad_mcp.exceptions import (
    DocumentNotFoundError,
    ObjectNotFoundError,
    SketchControlledMutationError,
    SketchControlledMutationRollbackError,
    SketchFilletCreationError,
    SketchFilletUnsafeError,
    SketchMutationIndexNotFoundError,
    SketchTypeMismatchError,
)
from freecad_mcp.protocols import SketchTopologyEditingAdapter

T = TypeVar("T")


class _Dispatcher:
    def call(self, operation: Callable[[], T]) -> T:
        return operation()


@dataclass(frozen=True)
class _Result:
    def to_dict(self) -> dict[str, object]:
        return {
            "first_geometry_index": 0,
            "second_geometry_index": 2,
            "created_arc_index": 3,
            "removed_coincident_index": 0,
            "created_tangent_indices": [1, 2],
            "geometry_mappings": [],
            "constraint_mappings": [],
            "created_geometry": [],
            "removed_geometry": [],
            "created_constraints": [],
            "removed_constraints": [],
            "modified_geometry_indices": [0, 2],
            "modified_constraint_indices": [],
            "transaction_name": "Fillet sketch geometry",
            "transaction_committed": True,
            "tangency_details": {},
            "solver": {},
            "dependency_summary": {},
            "sketch": {},
            "document": {},
        }


class _Adapter:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []
        self.error: Exception | None = None

    def fillet_sketch_geometry(
        self,
        document_name: str,
        sketch_name: str,
        first_geometry_index: int,
        radius: float,
    ) -> _Result:
        self.calls.append(("fillet", document_name, sketch_name, first_geometry_index, radius))
        if self.error is not None:
            raise self.error
        return _Result()


def _make_handler() -> tuple[FilletSketchGeometryHandler, _Adapter, _Dispatcher]:
    adapter = _Adapter()
    dispatcher = _Dispatcher()
    handler = FilletSketchGeometryHandler(
        adapter=cast(SketchTopologyEditingAdapter, adapter),
        dispatcher=dispatcher,
    )
    return handler, adapter, dispatcher


def test_validation_rejects_invalid_radius() -> None:
    handler, _, _ = _make_handler()
    result = handler.execute("Doc", "Sketch", 0, -1)
    assert not result.ok
    assert result.code == "validation_error"


def test_validation_rejects_non_finite_radius() -> None:
    handler, _, _ = _make_handler()
    result = handler.execute("Doc", "Sketch", 0, float("inf"))
    assert not result.ok
    assert result.code == "validation_error"


def test_validation_rejects_bool_radius() -> None:
    handler, _, _ = _make_handler()
    result = handler.execute("Doc", "Sketch", 0, True)
    assert not result.ok
    assert result.code == "validation_error"


def test_validation_rejects_zero_radius() -> None:
    handler, _, _ = _make_handler()
    result = handler.execute("Doc", "Sketch", 0, 0.0)
    assert not result.ok
    assert result.code == "validation_error"


def test_validation_rejects_negative_index() -> None:
    handler, _, _ = _make_handler()
    result = handler.execute("Doc", "Sketch", -1, 5.0)
    assert not result.ok


def test_validation_accepts_valid_request() -> None:
    handler, adapter, _ = _make_handler()
    result = handler.execute("Doc", "Sketch", 0, 5.0)
    assert result.ok
    assert result.code == "sketch_geometry_filleted"
    assert len(adapter.calls) == 1


def test_handler_returns_preflight_refusal() -> None:
    handler, adapter, _ = _make_handler()
    adapter.error = SketchFilletUnsafeError(
        operation="fillet",
        code="unsupported_geometry_type",
        reason="line_segment_required",
        first_geometry_index=0,
    )
    result = handler.execute("Doc", "Sketch", 0, 5.0)
    assert not result.ok
    assert result.code == "fillet_preflight_refused"


def test_handler_returns_creation_error() -> None:
    handler, adapter, _ = _make_handler()
    adapter.error = SketchFilletCreationError(
        operation="fillet",
        phase="mutation",
        reason="native_fillet_returned_nonzero",
    )
    result = handler.execute("Doc", "Sketch", 0, 5.0)
    assert not result.ok
    assert result.code == "native_fillet_failed"


def test_handler_returns_index_not_found() -> None:
    handler, adapter, _ = _make_handler()
    adapter.error = SketchMutationIndexNotFoundError(selection="geometry", index=0)
    result = handler.execute("Doc", "Sketch", 0, 5.0)
    assert not result.ok
    assert result.code == "index_not_found"


def test_handler_returns_document_not_found() -> None:
    handler, adapter, _ = _make_handler()
    adapter.error = DocumentNotFoundError()
    result = handler.execute("Doc", "Sketch", 0, 5.0)
    assert not result.ok
    assert result.code == "document_not_found"


def test_handler_returns_object_not_found() -> None:
    handler, adapter, _ = _make_handler()
    adapter.error = ObjectNotFoundError()
    result = handler.execute("Doc", "Sketch", 0, 5.0)
    assert not result.ok
    assert result.code == "object_not_found"


def test_handler_returns_sketch_type_mismatch() -> None:
    handler, adapter, _ = _make_handler()
    adapter.error = SketchTypeMismatchError()
    result = handler.execute("Doc", "Sketch", 0, 5.0)
    assert not result.ok
    assert result.code == "sketch_type_mismatch"


def test_handler_returns_rollback_error() -> None:
    handler, adapter, _ = _make_handler()
    adapter.error = SketchControlledMutationRollbackError(
        operation="fillet", reason="rollback_failed"
    )
    result = handler.execute("Doc", "Sketch", 0, 5.0)
    assert not result.ok
    assert result.code == "rollback_executed"


def test_handler_returns_controlled_mutation_error() -> None:
    handler, adapter, _ = _make_handler()
    adapter.error = SketchControlledMutationError(
        operation="fillet_geometry",
        phase="mutation",
        reason="native_error",
    )
    result = handler.execute("Doc", "Sketch", 0, 5.0)
    assert not result.ok
    assert result.code == "controlled_mutation_error"
