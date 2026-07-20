from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

import pytest

from freecad_mcp.commands.sketch_removal import (
    RemoveSketchConstraintsHandler,
    RemoveSketchGeometryHandler,
    SetSketchGeometryConstructionHandler,
)
from freecad_mcp.core.result import CommandResult
from freecad_mcp.exceptions import (
    SketchConstraintRemovalUnsafeError,
    SketchGeometryRemovalUnsafeError,
)
from freecad_mcp.models import (
    DocumentSummary,
    SketchConstraintData,
    SketchConstraintRemovalResult,
    SketchGeometryConstructionResult,
    SketchGeometryRemovalResult,
    SketchIndexChange,
    SketchInspectionResult,
    SketchLineGeometry,
    SketchPoint2D,
    SketchSolverData,
)
from freecad_mcp.validation import (
    validate_set_sketch_geometry_construction_request,
    validate_sketch_mutation_selection_request,
)

T = TypeVar("T")


class _Dispatcher:
    def call(self, operation: Callable[[], T]) -> T:
        return operation()


def _document() -> DocumentSummary:
    return DocumentSummary("Model", "Model", None, True, False, 2)


def _line(index: int, construction: bool = False) -> SketchLineGeometry:
    return SketchLineGeometry(
        index,
        construction,
        SketchPoint2D(float(index), 0.0),
        SketchPoint2D(float(index + 1), 0.0),
    )


def _constraint(index: int) -> SketchConstraintData:
    return SketchConstraintData(index, "horizontal", None, True, False, True, (), None)


def _sketch(*, construction: bool = False) -> SketchInspectionResult:
    return SketchInspectionResult(
        name="Sketch",
        label="Sketch",
        body_name="Body",
        visibility=True,
        map_mode="deactivated",
        attachment=None,
        placement=None,
        geometry_count=2,
        external_geometry_count=0,
        constraint_count=1,
        geometry=(_line(0, construction), _line(1, construction)),
        constraints=(_constraint(0),),
        solver=SketchSolverData(True, True, 4, False, (), (), (), ()),
    )


class _Adapter:
    def __init__(self) -> None:
        self.constraint_calls: list[tuple[str, str, tuple[int, ...]]] = []
        self.geometry_calls: list[tuple[str, str, tuple[int, ...]]] = []
        self.construction_calls: list[tuple[str, str, tuple[int, ...], bool]] = []
        self.constraint_unsafe = False
        self.geometry_unsafe = False
        self.no_change = False

    def remove_sketch_constraints(
        self,
        document_name: str,
        sketch_name: str,
        constraint_indices: tuple[int, ...],
    ) -> SketchConstraintRemovalResult:
        self.constraint_calls.append((document_name, sketch_name, constraint_indices))
        if self.constraint_unsafe:
            raise SketchConstraintRemovalUnsafeError(
                reason="expression_dependency",
                constraint_indices=constraint_indices,
                dependencies=(
                    {
                        "constraint_index": constraint_indices[0],
                        "constraint_name": "Width",
                    },
                ),
            )
        return SketchConstraintRemovalResult(
            constraint_indices,
            tuple(_constraint(index) for index in constraint_indices),
            (SketchIndexChange(1, 0),),
            _sketch(),
            _document(),
        )

    def remove_sketch_geometry(
        self,
        document_name: str,
        sketch_name: str,
        geometry_indices: tuple[int, ...],
    ) -> SketchGeometryRemovalResult:
        self.geometry_calls.append((document_name, sketch_name, geometry_indices))
        if self.geometry_unsafe:
            raise SketchGeometryRemovalUnsafeError(
                reason="dependent_constraints",
                dependencies=(
                    {
                        "geometry_index": geometry_indices[0],
                        "dependent_constraint_indices": [2, 4],
                    },
                ),
            )
        return SketchGeometryRemovalResult(
            geometry_indices,
            tuple(_line(index) for index in geometry_indices),
            (SketchIndexChange(1, 0),),
            (SketchIndexChange(0, 0),),
            {"before": {}, "after": {}},
            _sketch(),
            _document(),
        )

    def set_sketch_geometry_construction(
        self,
        document_name: str,
        sketch_name: str,
        geometry_indices: tuple[int, ...],
        construction: bool,
    ) -> SketchGeometryConstructionResult:
        self.construction_calls.append((document_name, sketch_name, geometry_indices, construction))
        changed = () if self.no_change else geometry_indices
        unchanged = geometry_indices if self.no_change else ()
        return SketchGeometryConstructionResult(
            construction,
            geometry_indices,
            changed,
            unchanged,
            tuple(_line(index, not construction) for index in geometry_indices),
            tuple(_line(index, construction) for index in geometry_indices),
            {"before": {}, "after": {}},
            _sketch(construction=construction),
            _document(),
        )


@pytest.mark.parametrize(
    "indices",
    [None, (), [], [True], [1.0], ["1"], [-1], [2, 2]],
)
def test_mutation_selection_rejects_empty_duplicate_and_non_strict_indices(
    indices: object,
) -> None:
    result = validate_sketch_mutation_selection_request(
        "Model",
        "Sketch",
        indices,
        field="geometry_indices",
    )

    assert isinstance(result, CommandResult)
    assert result.code == "validation_error"


def test_selection_validation_is_deterministic_and_canonical() -> None:
    name_error = validate_sketch_mutation_selection_request(
        "bad name",
        "Sketch",
        [True, -1],
        field="constraint_indices",
    )
    assert isinstance(name_error, CommandResult)
    assert name_error.data["field"] == "name"

    canonical = validate_sketch_mutation_selection_request(
        "Model",
        "Sketch",
        [5, 1, 3],
        field="constraint_indices",
    )
    assert canonical == (1, 3, 5)


@pytest.mark.parametrize("construction", [0, 1, "true", None, 1.0])
def test_construction_request_requires_strict_boolean(construction: object) -> None:
    result = validate_set_sketch_geometry_construction_request(
        "Model",
        "Sketch",
        [0],
        construction,
    )

    assert isinstance(result, CommandResult)
    assert result.code == "validation_error"
    assert result.data["field"] == "construction"


def test_handlers_dispatch_all_three_canonical_operations() -> None:
    adapter = _Adapter()
    dispatcher = _Dispatcher()

    constraints = RemoveSketchConstraintsHandler(adapter, dispatcher).execute(
        "Model", "Sketch", [5, 1]
    )
    geometry = RemoveSketchGeometryHandler(adapter, dispatcher).execute("Model", "Sketch", [4, 2])
    construction = SetSketchGeometryConstructionHandler(adapter, dispatcher).execute(
        "Model", "Sketch", [3, 0], True
    )

    assert constraints.code == "sketch_constraints_removed"
    assert geometry.code == "sketch_geometry_removed"
    assert construction.code == "sketch_geometry_construction_set"
    assert adapter.constraint_calls == [("Model", "Sketch", (1, 5))]
    assert adapter.geometry_calls == [("Model", "Sketch", (2, 4))]
    assert adapter.construction_calls == [("Model", "Sketch", (0, 3), True)]


def test_constraint_handler_reports_expression_dependency_without_dispatch_retry() -> None:
    adapter = _Adapter()
    adapter.constraint_unsafe = True

    result = RemoveSketchConstraintsHandler(adapter, _Dispatcher()).execute("Model", "Sketch", [2])

    assert result.code == "sketch_constraint_removal_unsafe"
    assert result.data["reason"] == "expression_dependency"
    assert result.data["dependencies"] == [{"constraint_index": 2, "constraint_name": "Width"}]
    assert adapter.constraint_calls == [("Model", "Sketch", (2,))]


def test_geometry_handler_reports_exact_dependency_refusal() -> None:
    adapter = _Adapter()
    adapter.geometry_unsafe = True

    result = RemoveSketchGeometryHandler(adapter, _Dispatcher()).execute("Model", "Sketch", [1])

    assert result.code == "sketch_geometry_removal_unsafe"
    assert result.data["reason"] == "dependent_constraints"
    assert result.data["geometry_constraint_dependencies"] == [
        {"geometry_index": 1, "dependent_constraint_indices": [2, 4]}
    ]


def test_all_already_correct_construction_returns_no_change_success() -> None:
    adapter = _Adapter()
    adapter.no_change = True

    result = SetSketchGeometryConstructionHandler(adapter, _Dispatcher()).execute(
        "Model", "Sketch", [0, 1], False
    )

    assert result.ok is True
    assert result.code == "sketch_geometry_construction_unchanged"
    assert result.data["no_change"] is True
