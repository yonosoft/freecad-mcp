from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

import pytest

from freecad_mcp.commands.sketch_external_geometry import (
    AddExternalGeometryHandler,
    GetSketchDependenciesHandler,
    ListExternalGeometryHandler,
    RemoveExternalGeometryHandler,
)
from freecad_mcp.core.result import CommandResult
from freecad_mcp.exceptions import SketchExternalGeometryRemovalUnsafeError
from freecad_mcp.models import (
    DocumentSummary,
    ExternalGeometryListResult,
    ExternalGeometryMutationResult,
    ExternalGeometryReferenceData,
    ExternalGeometrySourceInput,
    SketchDependencyInspectionResult,
    SketchGeometryExternalGeometrySourceInput,
    SketchInspectionResult,
    SketchLineGeometry,
    SketchPoint2D,
    SketchSolverData,
)
from freecad_mcp.validation import (
    validate_add_external_geometry_request,
    validate_external_geometry_reference_request,
)

T = TypeVar("T")


class _Dispatcher:
    def call(self, operation: Callable[[], T]) -> T:
        return operation()


def _document() -> DocumentSummary:
    return DocumentSummary("Model", "Model", None, True, False, 3)


def _sketch() -> SketchInspectionResult:
    return SketchInspectionResult(
        name="TargetSketch",
        label="Target Sketch",
        body_name="Body",
        visibility=True,
        map_mode="deactivated",
        attachment=None,
        placement=None,
        geometry_count=0,
        external_geometry_count=1,
        constraint_count=0,
        geometry=(),
        constraints=(),
        solver=SketchSolverData(True, True, 0, True, (), (), (), ()),
    )


def _reference() -> ExternalGeometryReferenceData:
    return ExternalGeometryReferenceData(
        external_reference_number=0,
        source={
            "type": "sketch_geometry",
            "document_name": "Model",
            "sketch_name": "SourceSketch",
            "sketch_label": "Source Sketch",
            "geometry_index": 4,
        },
        reference_category="sketch_geometry",
        reference_mode="normal",
        resolved=True,
        broken_reason=None,
        geometry=SketchLineGeometry(
            0,
            True,
            SketchPoint2D(0.0, 0.0),
            SketchPoint2D(10.0, 0.0),
        ),
        used_by_constraint_indices=(),
    )


class _Adapter:
    def __init__(self) -> None:
        self.add_calls: list[tuple[str, str, ExternalGeometrySourceInput]] = []
        self.list_calls: list[tuple[str, str]] = []
        self.remove_calls: list[tuple[str, str, int]] = []
        self.dependency_calls: list[tuple[str, str]] = []
        self.unsafe_remove = False

    def add_external_geometry(
        self,
        document_name: str,
        sketch_name: str,
        source: ExternalGeometrySourceInput,
    ) -> ExternalGeometryMutationResult:
        self.add_calls.append((document_name, sketch_name, source))
        return ExternalGeometryMutationResult(
            "add",
            _reference(),
            (_reference(),),
            _sketch(),
            _document(),
        )

    def list_external_geometry(
        self,
        document_name: str,
        sketch_name: str,
    ) -> ExternalGeometryListResult:
        self.list_calls.append((document_name, sketch_name))
        return ExternalGeometryListResult(
            document_name,
            sketch_name,
            (_reference(),),
            _document(),
        )

    def remove_external_geometry(
        self,
        document_name: str,
        sketch_name: str,
        external_reference_number: int,
    ) -> ExternalGeometryMutationResult:
        self.remove_calls.append((document_name, sketch_name, external_reference_number))
        if self.unsafe_remove:
            raise SketchExternalGeometryRemovalUnsafeError(
                external_reference_number=external_reference_number,
                reason="dependent_constraints",
                constraint_indices=(4, 7),
            )
        return ExternalGeometryMutationResult(
            "remove",
            _reference(),
            (),
            _sketch(),
            _document(),
            {"dependent_constraint_indices": [], "other_relationships": []},
        )

    def get_sketch_dependencies(
        self,
        document_name: str,
        sketch_name: str,
    ) -> SketchDependencyInspectionResult:
        self.dependency_calls.append((document_name, sketch_name))
        return SketchDependencyInspectionResult(
            document_name,
            sketch_name,
            (_reference(),),
            (),
            (),
            (),
            (),
            (),
            (),
            _document(),
        )


def test_source_union_validation_is_strict_and_canonical() -> None:
    parsed = validate_add_external_geometry_request(
        "Model",
        "TargetSketch",
        {"type": "object_subelement", "object_name": "Pad", "subelement": "Edge3"},
    )
    assert not isinstance(parsed, CommandResult)

    sketch_source = validate_add_external_geometry_request(
        "Model",
        "TargetSketch",
        {"type": "sketch_geometry", "sketch_name": "SourceSketch", "geometry_index": 4},
    )
    assert isinstance(sketch_source, SketchGeometryExternalGeometrySourceInput)

    for invalid in (
        {"type": "object_subelement", "object_name": "Pad", "subelement": "edge3"},
        {"type": "object_subelement", "object_name": "Pad", "subelement": "Edge0"},
        {
            "type": "object_subelement",
            "object_name": "Pad",
            "subelement": "Edge3",
            "extra": True,
        },
        {"type": "sketch_geometry", "sketch_name": "TargetSketch", "geometry_index": 0},
    ):
        result = validate_add_external_geometry_request("Model", "TargetSketch", invalid)
        assert isinstance(result, CommandResult)
        assert result.code == "validation_error"


@pytest.mark.parametrize("value", [-1, True, 1.0, "0"])
def test_external_reference_number_rejects_negative_and_non_strict_integers(
    value: object,
) -> None:
    result = validate_external_geometry_reference_request("Model", "TargetSketch", value)
    assert isinstance(result, CommandResult)
    assert result.code == "validation_error"


def test_handlers_dispatch_all_four_controlled_operations() -> None:
    adapter = _Adapter()
    dispatcher = _Dispatcher()
    added = AddExternalGeometryHandler(adapter, dispatcher).execute(
        "Model",
        "TargetSketch",
        {"type": "sketch_geometry", "sketch_name": "SourceSketch", "geometry_index": 4},
    )
    listed = ListExternalGeometryHandler(adapter, dispatcher).execute("Model", "TargetSketch")
    removed = RemoveExternalGeometryHandler(adapter, dispatcher).execute("Model", "TargetSketch", 0)
    dependencies = GetSketchDependenciesHandler(adapter, dispatcher).execute(
        "Model", "TargetSketch"
    )

    assert added.code == "external_geometry_added"
    assert listed.code == "external_geometry_listed"
    assert removed.code == "external_geometry_removed"
    assert dependencies.code == "sketch_dependencies_retrieved"
    assert adapter.add_calls[0][2].geometry_index == 4  # type: ignore[union-attr]
    assert adapter.list_calls == [("Model", "TargetSketch")]
    assert adapter.remove_calls == [("Model", "TargetSketch", 0)]
    assert adapter.dependency_calls == [("Model", "TargetSketch")]


def test_remove_handler_reports_impact_and_refuses_native_cascade() -> None:
    adapter = _Adapter()
    adapter.unsafe_remove = True
    result = RemoveExternalGeometryHandler(adapter, _Dispatcher()).execute(
        "Model", "TargetSketch", 0
    )

    assert result.code == "external_geometry_removal_unsafe"
    assert result.data["reason"] == "dependent_constraints"
    assert result.data["dependent_constraint_indices"] == [4, 7]
