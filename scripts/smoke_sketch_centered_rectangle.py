"""Direct FreeCAD 1.1 smoke campaign for semantic centred rectangles."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

import FreeCAD as App  # type: ignore[import-not-found]  # noqa: E402
import Part  # type: ignore[import-not-found]  # noqa: E402
import Sketcher  # type: ignore[import-not-found]  # noqa: E402
import smoke_document_history  # noqa: E402
import smoke_sketch_point_relationships  # noqa: E402
import smoke_sketch_rectangle as rectangle_smoke  # noqa: E402
import smoke_sketch_symmetric  # noqa: E402
import smoke_sketch_tangent  # noqa: E402

from freecad_mcp.exceptions import (  # noqa: E402
    DocumentHistoryTransactionMismatchError,
    SketchCenteredRectangleCreationError,
    SketchCenteredRectangleVerificationError,
)
from freecad_mcp.freecad import sketch_centered_rectangle_creation  # noqa: E402
from freecad_mcp.freecad.document import FreeCADDocumentAdapter  # noqa: E402
from freecad_mcp.mcp.sketch_centered_rectangle_tools import (  # noqa: E402
    CREATE_SKETCH_CENTERED_RECTANGLE_DESCRIPTION,
)
from freecad_mcp.mcp.sketch_rectangle_tools import (  # noqa: E402
    CREATE_SKETCH_RECTANGLE_DESCRIPTION,
)
from freecad_mcp.models import (  # noqa: E402
    OriginPlane,
    SketchCenteredRectangleRequestInput,
    SketchRectangleRequestInput,
)
from freecad_mcp.transaction_names import (  # noqa: E402
    CREATE_SKETCH_CENTERED_RECTANGLE_TRANSACTION_NAME,
)
from freecad_mcp.validation import (  # noqa: E402
    validate_add_sketch_geometry_request,
    validate_create_sketch_centered_rectangle_request,
)


def _request(
    document: Any,
    sketch: Any,
    *,
    width: float = 30.0,
    height: float = 20.0,
    x: float = 0.0,
    y: float = 0.0,
) -> SketchCenteredRectangleRequestInput:
    return SketchCenteredRectangleRequestInput.model_validate(
        {
            "document_name": str(document.Name),
            "sketch_name": str(sketch.Name),
            "width": width,
            "height": height,
            "center": {"x": x, "y": y},
        }
    )


def _center(point: Any) -> tuple[float, float]:
    return float(point.X), float(point.Y)


def _basic_cases(adapter: FreeCADDocumentAdapter, scenarios: dict[str, object]) -> None:
    cases = (
        ("CenteredOrigin", 0.0, 0.0, "01_origin_center"),
        ("CenteredArbitrary", 12.0, -7.0, "02_arbitrary_center"),
        ("CenteredAxisY", 0.0, 9.0, "03_center_x_zero"),
        ("CenteredAxisX", 8.0, 0.0, "04_center_y_zero"),
        ("CenteredBoth", 6.0, 4.0, "05_both_center_coordinates_nonzero"),
        ("CenteredNegative", -12.0, -7.0, "06_negative_center"),
        ("CenteredMixed", -12.0, 7.0, "07_mixed_sign_center"),
    )
    arbitrary: tuple[Any, Any] | None = None
    for name, x, y, key in cases:
        document, sketch = rectangle_smoke._new_sketch(name)
        try:
            created = adapter.create_sketch_centered_rectangle(_request(document, sketch, x=x, y=y))
            profile = created.profile.to_dict()
            assert int(sketch.GeometryCount) == 5
            assert int(sketch.ConstraintCount) == (12 if x == 0.0 and y == 0.0 else 13)
            assert int(sketch.DoF) == 0 and bool(sketch.FullyConstrained)
            assert list(sketch.ConflictingConstraints) == []
            assert list(sketch.RedundantConstraints) == []
            assert list(sketch.PartiallyRedundantConstraints) == []
            assert list(sketch.MalformedConstraints) == []
            assert str(document.FileName) == ""
            scenarios[key] = {
                "center": [x, y],
                "constraint_count": int(sketch.ConstraintCount),
                "degrees_of_freedom": int(sketch.DoF),
            }
            if name == "CenteredArbitrary":
                arbitrary = sketch, profile
        finally:
            if name != "CenteredArbitrary":
                rectangle_smoke._close(document)

    assert arbitrary is not None
    sketch, profile = arbitrary
    document = sketch.Document
    try:
        edges = list(sketch.Geometry[:4])
        center = sketch.Geometry[4]
        expected = [
            (-3.0, -17.0, 27.0, -17.0),
            (27.0, -17.0, 27.0, 3.0),
            (27.0, 3.0, -3.0, 3.0),
            (-3.0, 3.0, -3.0, -17.0),
        ]
        actual = [
            (
                float(edge.StartPoint.x),
                float(edge.StartPoint.y),
                float(edge.EndPoint.x),
                float(edge.EndPoint.y),
            )
            for edge in edges
        ]
        assert actual == expected
        assert profile["geometry_indices"] == [0, 1, 2, 3]
        scenarios["08_four_deterministic_edge_indices"] = profile["geometry_indices"]
        scenarios["09_deterministic_corner_mapping"] = profile["corners"]
        assert profile["reference_geometry_indices"] == [4]
        scenarios["10_center_point_appended_fifth"] = profile["reference_geometry_indices"]
        assert bool(sketch.getConstruction(4))
        scenarios["11_center_point_is_construction"] = True
        assert int(sketch.GeometryCount) == 5
        scenarios["12_no_diagonal_helper_geometry"] = True
        assert float(profile["width"]) == 30.0
        scenarios["13_exact_width"] = 30.0
        assert float(profile["height"]) == 20.0
        scenarios["14_exact_height"] = 20.0
        assert _center(center) == (12.0, -7.0)
        scenarios["15_exact_center"] = [12.0, -7.0]
        scenarios["16_exact_corner_coordinates"] = expected
        assert bool(profile["closed"])
        scenarios["17_closed_profile"] = True
        assert bool(profile["axis_aligned"])
        scenarios["18_axis_aligned_profile"] = True
        lower_left = rectangle_smoke._point(edges[0].StartPoint)
        upper_right = rectangle_smoke._point(edges[1].EndPoint)
        midpoint = (
            (lower_left[0] + upper_right[0]) / 2.0,
            (lower_left[1] + upper_right[1]) / 2.0,
        )
        assert midpoint == _center(center)
        symmetry = sketch.Constraints[10]
        assert str(symmetry.Type) == "Symmetric"
        assert (
            int(symmetry.First),
            int(symmetry.FirstPos),
            int(symmetry.Second),
            int(symmetry.SecondPos),
            int(symmetry.Third),
            int(symmetry.ThirdPos),
        ) == (0, 1, 1, 2, 4, 1)
        scenarios["19_midpoint_and_symmetry"] = True
        assert int(sketch.DoF) == 0
        scenarios["20_zero_degrees_of_freedom"] = True
        assert not any(
            (
                list(sketch.ConflictingConstraints),
                list(sketch.RedundantConstraints),
                list(sketch.PartiallyRedundantConstraints),
                list(sketch.MalformedConstraints),
            )
        )
        scenarios["21_clean_diagnostics"] = True
        scenarios["22_origin_branch_constraint_count"] = 12
        scenarios["23_non_origin_branch_constraint_count"] = 13
    finally:
        rectangle_smoke._close(document)


def _preservation_cases(
    adapter: FreeCADDocumentAdapter,
    scenarios: dict[str, object],
) -> None:
    document, sketch = rectangle_smoke._new_sketch("CenteredExisting")
    try:
        normal = sketch.addGeometry(
            Part.LineSegment(App.Vector(-5.0, 40.0, 0.0), App.Vector(5.0, 40.0, 0.0)),
            False,
        )
        construction = sketch.addGeometry(Part.Point(App.Vector(0.0, 50.0, 0.0)), True)
        sketch.addConstraint(Sketcher.Constraint("Block", normal))
        sketch.addConstraint(Sketcher.Constraint("DistanceX", construction, 1, 0.0))
        sketch.addConstraint(Sketcher.Constraint("DistanceY", construction, 1, 50.0))
        document.recompute()
        document.clearUndos()
        before = (
            rectangle_smoke._point(sketch.Geometry[0].StartPoint),
            rectangle_smoke._point(sketch.Geometry[0].EndPoint),
            _center(sketch.Geometry[1]),
            bool(sketch.getConstruction(0)),
            bool(sketch.getConstruction(1)),
            tuple(str(item.Type) for item in sketch.Constraints),
        )
        result = adapter.create_sketch_centered_rectangle(_request(document, sketch, x=4.0, y=-3.0))
        after = (
            rectangle_smoke._point(sketch.Geometry[0].StartPoint),
            rectangle_smoke._point(sketch.Geometry[0].EndPoint),
            _center(sketch.Geometry[1]),
            bool(sketch.getConstruction(0)),
            bool(sketch.getConstruction(1)),
            tuple(str(item.Type) for item in sketch.Constraints[:3]),
        )
        assert before == after
        assert result.profile.geometry_indices == (2, 3, 4, 5)
        assert result.profile.reference_geometry_indices == (6,)
        scenarios["24_existing_non_empty_sketch"] = {
            "profile_indices": [2, 3, 4, 5],
            "reference_indices": [6],
        }
        scenarios["25_existing_construction_preservation"] = before == after
    finally:
        rectangle_smoke._close(document)

    document = rectangle_smoke._new_document("CenteredAttached")
    try:
        body = document.addObject("PartDesign::Body", "Body")
        document.recompute()
        adapter.create_sketch(str(document.Name), str(body.Name), "Sketch", None, OriginPlane.XY)
        sketch = document.getObject("Sketch")
        assert sketch is not None
        document.clearUndos()
        parent = sketch.getParentGeoFeatureGroup()
        support = sketch.AttachmentSupport
        map_mode = str(sketch.MapMode)
        placement = sketch.Placement
        adapter.create_sketch_centered_rectangle(_request(document, sketch, x=3.0, y=4.0))
        assert sketch.getParentGeoFeatureGroup() is parent
        assert sketch.AttachmentSupport == support
        assert str(sketch.MapMode) == map_mode
        assert sketch.Placement == placement
        scenarios["26_body_owned_sketch"] = str(parent.Name)
        scenarios["27_xy_plane_attached_sketch"] = map_mode
    finally:
        rectangle_smoke._close(document)


def _saved_and_history_cases(
    adapter: FreeCADDocumentAdapter,
    scenarios: dict[str, object],
) -> None:
    document, sketch = rectangle_smoke._new_sketch("CenteredUnsaved")
    try:
        adapter.create_sketch_centered_rectangle(_request(document, sketch))
        adapter.undo_document(str(document.Name), CREATE_SKETCH_CENTERED_RECTANGLE_TRANSACTION_NAME)
        adapter.redo_document(str(document.Name), CREATE_SKETCH_CENTERED_RECTANGLE_TRANSACTION_NAME)
        assert str(document.FileName) == ""
        scenarios["28_unsaved_document"] = True
    finally:
        rectangle_smoke._close(document)

    with tempfile.TemporaryDirectory(prefix="freecad_mcp_centered_rectangle_") as directory:
        document, sketch = rectangle_smoke._new_sketch("CenteredSaved")
        try:
            path = Path(directory) / "centered.FCStd"
            document.saveAs(str(path))
            before = (path.stat().st_size, path.stat().st_mtime_ns, rectangle_smoke._digest(path))
            adapter.create_sketch_centered_rectangle(_request(document, sketch, x=-2.0, y=5.0))
            adapter.undo_document(
                str(document.Name), CREATE_SKETCH_CENTERED_RECTANGLE_TRANSACTION_NAME
            )
            adapter.redo_document(
                str(document.Name), CREATE_SKETCH_CENTERED_RECTANGLE_TRANSACTION_NAME
            )
            after = (path.stat().st_size, path.stat().st_mtime_ns, rectangle_smoke._digest(path))
            assert before == after
            scenarios["29_saved_file_byte_timestamp_preservation"] = {
                "size": before[0],
                "timestamp": before[1],
                "sha256": before[2],
            }
        finally:
            rectangle_smoke._close(document)

    document, sketch = rectangle_smoke._new_sketch("CenteredHistory")
    try:
        adapter.create_sketch_centered_rectangle(_request(document, sketch, x=12.0, y=-7.0))
        history = adapter.get_document_history(str(document.Name)).history
        assert history.next_undo_name == CREATE_SKETCH_CENTERED_RECTANGLE_TRANSACTION_NAME
        adapter.undo_document(str(document.Name), CREATE_SKETCH_CENTERED_RECTANGLE_TRANSACTION_NAME)
        document.recompute()
        assert int(sketch.GeometryCount) == 0 and int(sketch.ConstraintCount) == 0
        scenarios["30_one_step_undo"] = True
        adapter.redo_document(str(document.Name), CREATE_SKETCH_CENTERED_RECTANGLE_TRANSACTION_NAME)
        document.recompute()
        assert int(sketch.GeometryCount) == 5 and int(sketch.ConstraintCount) == 13
        assert int(sketch.DoF) == 0
        scenarios["31_one_step_redo"] = True
        assert bool(sketch.getConstruction(4)) and _center(sketch.Geometry[4]) == (12.0, -7.0)
        scenarios["32_construction_point_restoration"] = True
        try:
            adapter.undo_document(str(document.Name), "Wrong centered transaction")
            raise AssertionError("name mismatch was not rejected")
        except DocumentHistoryTransactionMismatchError:
            pass
        assert int(sketch.GeometryCount) == 5
        scenarios["33_expected_name_mismatch"] = True

        adapter.undo_document(str(document.Name), CREATE_SKETCH_CENTERED_RECTANGLE_TRANSACTION_NAME)
        payload = validate_add_sketch_geometry_request(
            str(document.Name),
            str(sketch.Name),
            [{"type": "point", "position": {"x": 1.0, "y": 2.0}, "construction": False}],
        )
        assert isinstance(payload, tuple)
        adapter.add_sketch_geometry(str(document.Name), str(sketch.Name), payload)
        assert not adapter.get_document_history(str(document.Name)).history.can_redo
        scenarios["34_redo_invalidation"] = True
    finally:
        rectangle_smoke._close(document)


def _failure_cases(adapter: FreeCADDocumentAdapter, scenarios: dict[str, object]) -> None:
    document, sketch = rectangle_smoke._new_sketch("CenteredValidationFailure")
    try:
        history = adapter.get_document_history(str(document.Name)).history
        validation = validate_create_sketch_centered_rectangle_request(
            str(document.Name), str(sketch.Name), 0.0, 20.0, {"x": 0.0, "y": 0.0}
        )
        assert not isinstance(validation, SketchCenteredRectangleRequestInput)
        assert history == adapter.get_document_history(str(document.Name)).history
        assert int(sketch.GeometryCount) == 0 and int(document.UndoCount) == 0
        scenarios["35_failed_validation_zero_transaction"] = True
    finally:
        rectangle_smoke._close(document)

    original_index_verifier = sketch_centered_rectangle_creation._verify_assigned_index

    def inject_index_failure(target_phase: str, target_call: int) -> bool:
        document, sketch = rectangle_smoke._new_sketch(
            f"CenteredInjected{target_phase.title()}{target_call}"
        )
        calls = {"geometry": 0, "center": 0, "constraint": 0}

        def verifier(value: object, expected: int, phase: str) -> None:
            original_index_verifier(value, expected, phase)
            calls[phase] += 1
            if phase == target_phase and calls[phase] == target_call:
                raise SketchCenteredRectangleCreationError(
                    phase=phase,
                    reason="injected_index_failure",
                )

        sketch_centered_rectangle_creation._verify_assigned_index = verifier
        try:
            try:
                adapter.create_sketch_centered_rectangle(_request(document, sketch, x=2.0, y=3.0))
                raise AssertionError("injected centred rectangle failure was not raised")
            except SketchCenteredRectangleCreationError:
                pass
            assert int(sketch.GeometryCount) == 0
            assert int(sketch.ConstraintCount) == 0
            assert int(document.UndoCount) == 0
            return True
        finally:
            sketch_centered_rectangle_creation._verify_assigned_index = original_index_verifier
            rectangle_smoke._close(document)

    scenarios["36_injected_edge_failure_rollback"] = inject_index_failure("geometry", 2)
    scenarios["37_injected_center_point_failure_rollback"] = inject_index_failure("center", 1)
    scenarios["38_injected_symmetry_failure_rollback"] = inject_index_failure("constraint", 11)

    document, sketch = rectangle_smoke._new_sketch("CenteredVerificationFailure")
    original_verifier = sketch_centered_rectangle_creation._verify_centered_rectangle

    def verification_failure(**kwargs: object) -> None:
        raise SketchCenteredRectangleVerificationError("injected_verification_failure")

    sketch_centered_rectangle_creation._verify_centered_rectangle = verification_failure
    try:
        try:
            adapter.create_sketch_centered_rectangle(_request(document, sketch, x=4.0, y=-2.0))
            raise AssertionError("injected verification failure was not raised")
        except SketchCenteredRectangleVerificationError:
            pass
        assert int(sketch.GeometryCount) == 0
        assert int(sketch.ConstraintCount) == 0
        assert int(document.UndoCount) == 0
        scenarios["39_verification_failure_rollback"] = True
    finally:
        sketch_centered_rectangle_creation._verify_centered_rectangle = original_verifier
        rectangle_smoke._close(document)


def _isolation_and_regressions(
    adapter: FreeCADDocumentAdapter,
    scenarios: dict[str, object],
) -> None:
    first, first_sketch = rectangle_smoke._new_sketch("CenteredIsolationA")
    second, second_sketch = rectangle_smoke._new_sketch("CenteredIsolationB")
    try:
        adapter.create_sketch_centered_rectangle(_request(first, first_sketch, x=1.0, y=1.0))
        assert int(second_sketch.GeometryCount) == 0
        assert int(second_sketch.ConstraintCount) == 0
        assert int(second.UndoCount) == 0
        scenarios["40_cross_document_isolation"] = True
    finally:
        rectangle_smoke._close(second)
        rectangle_smoke._close(first)

    document, sketch = rectangle_smoke._new_sketch("CenteredLowerLeftRegression")
    try:
        lower_request = SketchRectangleRequestInput.model_validate(
            {
                "document_name": str(document.Name),
                "sketch_name": str(sketch.Name),
                "width": 30.0,
                "height": 20.0,
                "placement": {"type": "lower_left", "x": -15.0, "y": -10.0},
            }
        )
        result = adapter.create_sketch_rectangle(lower_request)
        assert result.profile.geometry_indices == (0, 1, 2, 3)
        assert int(sketch.GeometryCount) == 4 and int(sketch.DoF) == 0
        scenarios["41_lower_left_rectangle_regression"] = True
    finally:
        rectangle_smoke._close(document)

    tangent = smoke_sketch_tangent._combined_regression(adapter)
    assert (
        tangent["32_symmetry_point_relationship_tangent_regression"]["solver"]["degrees_of_freedom"]
        == 0
    )
    scenarios["42_tangency_regression"] = True

    symmetric = smoke_sketch_symmetric._centred_rectangle(adapter)
    assert symmetric["solver"]["degrees_of_freedom"] == 0
    scenarios["43_symmetry_regression"] = True

    cardinal = smoke_sketch_point_relationships._cardinal_regression(adapter)
    assert cardinal["24_circle_cardinal_point_regression"]["degrees_of_freedom"] == 0
    scenarios["44_point_relationship_regression"] = True

    history = smoke_document_history._workflow_cases(adapter)
    assert history
    scenarios["45_document_history_regression"] = True


def _recovery_and_selection(
    adapter: FreeCADDocumentAdapter,
    scenarios: dict[str, object],
) -> None:
    document, sketch = rectangle_smoke._new_sketch("CenteredRecovery")
    try:
        adapter.create_sketch_centered_rectangle(_request(document, sketch, x=40.0, y=30.0))
        assert _center(sketch.Geometry[4]) == (40.0, 30.0)
        history = adapter.get_document_history(str(document.Name)).history
        assert history.next_undo_name == CREATE_SKETCH_CENTERED_RECTANGLE_TRANSACTION_NAME
        adapter.undo_document(str(document.Name), CREATE_SKETCH_CENTERED_RECTANGLE_TRANSACTION_NAME)
        assert int(sketch.GeometryCount) == 0 and int(sketch.ConstraintCount) == 0
        adapter.create_sketch_centered_rectangle(_request(document, sketch, x=12.0, y=-7.0))
        document.recompute()
        assert _center(sketch.Geometry[4]) == (12.0, -7.0)
        assert int(sketch.GeometryCount) == 5 and int(sketch.DoF) == 0
        assert len([obj for obj in document.Objects if str(obj.Name) == "Sketch"]) == 1
        assert not adapter.get_document_history(str(document.Name)).history.can_redo
        scenarios["46_same_sketch_recovery_from_wrong_center"] = {
            "corrected_center": [12.0, -7.0],
            "redo_invalidated": True,
            "replacement_sketches": 0,
        }
    finally:
        rectangle_smoke._close(document)

    centered_schema = SketchCenteredRectangleRequestInput.model_json_schema()
    lower_left_schema = SketchRectangleRequestInput.model_json_schema()
    assert centered_schema["required"][-1] == "center"
    assert "placement" not in centered_schema["properties"]
    assert lower_left_schema["required"][-1] == "placement"
    assert "center" not in lower_left_schema["properties"]
    assert "Do not translate centre intent" in CREATE_SKETCH_CENTERED_RECTANGLE_DESCRIPTION
    assert "lower-left placement" in CREATE_SKETCH_RECTANGLE_DESCRIPTION
    scenarios["47_tool_selection_distinction"] = {
        "center_defined": "create_sketch_centered_rectangle",
        "lower_left_defined": "create_sketch_rectangle",
        "custom_geometry": "add_sketch_geometry",
        "relationship_modification": "add_sketch_constraints",
    }


def main() -> int:
    adapter = FreeCADDocumentAdapter()
    scenarios: dict[str, object] = {}
    _basic_cases(adapter, scenarios)
    _preservation_cases(adapter, scenarios)
    _saved_and_history_cases(adapter, scenarios)
    _failure_cases(adapter, scenarios)
    _isolation_and_regressions(adapter, scenarios)
    _recovery_and_selection(adapter, scenarios)
    assert len(scenarios) == 47

    version = App.Version()
    result = {
        "freecad_version": version,
        "freecad_revision": version[-1],
        "python_executable": sys.executable,
        "python_version": sys.version,
        "scenario_count": len(scenarios),
        "pass_count": len(scenarios),
        "incidental_helper_geometry_count": 0,
        "scenarios": scenarios,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
