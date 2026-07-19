"""Direct FreeCAD 1.1 smoke campaign for semantic polygon profiles."""

from __future__ import annotations

import json
import math
import sys
import tempfile
from pathlib import Path
from typing import Any, Literal

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
    SketchPolygonCreationError,
    SketchPolygonVerificationError,
)
from freecad_mcp.freecad import sketch_polygon_creation  # noqa: E402
from freecad_mcp.freecad.document import FreeCADDocumentAdapter  # noqa: E402
from freecad_mcp.mcp.sketch_centered_rectangle_tools import (  # noqa: E402
    CREATE_SKETCH_CENTERED_RECTANGLE_DESCRIPTION,
)
from freecad_mcp.mcp.sketch_polygon_tools import (  # noqa: E402
    CREATE_SKETCH_EQUILATERAL_TRIANGLE_DESCRIPTION,
    CREATE_SKETCH_REGULAR_POLYGON_DESCRIPTION,
)
from freecad_mcp.mcp.sketch_rectangle_tools import (  # noqa: E402
    CREATE_SKETCH_RECTANGLE_DESCRIPTION,
)
from freecad_mcp.models import (  # noqa: E402
    MAX_REGULAR_POLYGON_SIDE_COUNT,
    OriginPlane,
    SketchCenteredRectangleRequestInput,
    SketchCenterPointInput,
    SketchRectangleRequestInput,
    SketchSemanticPolygonRequest,
)
from freecad_mcp.transaction_names import (  # noqa: E402
    CREATE_SKETCH_EQUILATERAL_TRIANGLE_TRANSACTION_NAME,
    CREATE_SKETCH_REGULAR_POLYGON_TRANSACTION_NAME,
)
from freecad_mcp.validation import (  # noqa: E402
    validate_add_sketch_geometry_request,
    validate_create_sketch_equilateral_triangle_request,
    validate_create_sketch_regular_polygon_request,
)

_TOLERANCE = 1.0e-6
ProfileType = Literal["equilateral_triangle", "regular_polygon"]


def _request(
    document: Any,
    sketch: Any,
    *,
    side_count: int = 6,
    radius: float = 20.0,
    x: float = 0.0,
    y: float = 0.0,
    angle: float = 0.0,
    profile_type: ProfileType = "regular_polygon",
) -> SketchSemanticPolygonRequest:
    return SketchSemanticPolygonRequest(
        document_name=str(document.Name),
        sketch_name=str(sketch.Name),
        side_count=side_count,
        circumradius=radius,
        center=SketchCenterPointInput(x=x, y=y),
        first_vertex_angle_degrees=angle,
        profile_type=profile_type,
    )


def _constraint_count(side_count: int, x: float, y: float) -> int:
    return 3 * side_count + (3 if x == 0.0 and y == 0.0 else 4)


def _point(value: Any) -> tuple[float, float]:
    return float(value.x), float(value.y)


def _same(first: tuple[float, float], second: tuple[float, float]) -> bool:
    return math.isclose(first[0], second[0], abs_tol=_TOLERANCE) and math.isclose(
        first[1], second[1], abs_tol=_TOLERANCE
    )


def _edge_length(item: Any) -> float:
    return math.hypot(
        float(item.EndPoint.x) - float(item.StartPoint.x),
        float(item.EndPoint.y) - float(item.StartPoint.y),
    )


def _basic_assertions(
    sketch: Any,
    result: Any,
    *,
    side_count: int,
    radius: float,
    x: float,
    y: float,
    angle: float,
    first_geometry_index: int = 0,
) -> None:
    profile = result.profile
    assert profile.geometry_indices == tuple(
        range(first_geometry_index, first_geometry_index + side_count)
    )
    assert profile.reference_geometry_indices == (
        first_geometry_index + side_count,
        first_geometry_index + side_count + 1,
    )
    assert len(profile.edges) == side_count and len(profile.vertices) == side_count
    assert int(sketch.GeometryCount) == first_geometry_index + side_count + 2
    assert int(sketch.ConstraintCount) >= _constraint_count(side_count, x, y)
    assert int(sketch.DoF) == 0 and bool(sketch.FullyConstrained)
    assert not sketch.ConflictingConstraints
    assert not sketch.RedundantConstraints
    assert not sketch.PartiallyRedundantConstraints
    assert not sketch.MalformedConstraints
    assert bool(sketch.getConstruction(first_geometry_index + side_count))
    assert bool(sketch.getConstruction(first_geometry_index + side_count + 1))
    expected_angle = angle % 360.0
    assert math.isclose(profile.first_vertex_angle_degrees, expected_angle, abs_tol=_TOLERANCE)
    expected_vertices = tuple(
        (
            x + radius * math.cos(math.radians(expected_angle + index * 360.0 / side_count)),
            y + radius * math.sin(math.radians(expected_angle + index * 360.0 / side_count)),
        )
        for index in range(side_count)
    )
    for index, expected in enumerate(expected_vertices):
        edge = sketch.Geometry[first_geometry_index + index]
        assert _same(_point(edge.StartPoint), expected)
        assert _same(_point(edge.EndPoint), expected_vertices[(index + 1) % side_count])
        assert not bool(sketch.getConstruction(first_geometry_index + index))
    lengths = [
        _edge_length(sketch.Geometry[first_geometry_index + index]) for index in range(side_count)
    ]
    assert all(math.isclose(item, lengths[0], abs_tol=_TOLERANCE) for item in lengths)
    centre = sketch.Geometry[first_geometry_index + side_count]
    circle = sketch.Geometry[first_geometry_index + side_count + 1]
    assert _same((float(centre.X), float(centre.Y)), (x, y))
    assert _same(_point(circle.Center), (x, y))
    assert math.isclose(float(circle.Radius), radius, abs_tol=_TOLERANCE)


def _new_profile(
    adapter: FreeCADDocumentAdapter,
    name: str,
    *,
    side_count: int = 6,
    radius: float = 20.0,
    x: float = 0.0,
    y: float = 0.0,
    angle: float = 0.0,
    profile_type: ProfileType = "regular_polygon",
) -> tuple[Any, Any, Any]:
    document, sketch = rectangle_smoke._new_sketch(name)
    result = adapter.create_sketch_polygon(
        _request(
            document,
            sketch,
            side_count=side_count,
            radius=radius,
            x=x,
            y=y,
            angle=angle,
            profile_type=profile_type,
        )
    )
    _basic_assertions(
        sketch,
        result,
        side_count=side_count,
        radius=radius,
        x=x,
        y=y,
        angle=angle,
    )
    return document, sketch, result


def _triangle_cases(adapter: FreeCADDocumentAdapter, scenarios: dict[str, object]) -> None:
    document, sketch, result = _new_profile(
        adapter,
        "PolygonTriangleOrigin",
        side_count=3,
        angle=90.0,
        profile_type="equilateral_triangle",
    )
    try:
        expected = ((0.0, 20.0), (-17.32050807568877, -10.0), (17.32050807568877, -10.0))
        actual = tuple(_point(sketch.Geometry[index].StartPoint) for index in range(3))
        assert all(_same(first, second) for first, second in zip(actual, expected, strict=True))
        scenarios["01_triangle_origin_upright"] = actual
        scenarios["06_triangle_exact_edge_order"] = result.profile.geometry_indices
        scenarios["07_triangle_exact_vertex_order"] = actual
        scenarios["08_triangle_center_after_edges"] = result.profile.center.reference.geometry_index
        scenarios["09_triangle_center_construction"] = sketch.getConstruction(3)
        scenarios["10_triangle_equal_sides"] = [
            _edge_length(sketch.Geometry[index]) for index in range(3)
        ]
        scenarios["11_triangle_exact_circumradius"] = result.profile.circumradius
        scenarios["12_triangle_zero_dof"] = int(sketch.DoF)
        scenarios["13_triangle_clean_diagnostics"] = True
    finally:
        rectangle_smoke._close(document)

    for name, x, y, angle, key in (
        ("PolygonTriangleArbitrary", 12.0, -7.0, 30.0, "02_triangle_arbitrary_center"),
        ("PolygonTrianglePositive", 0.0, 0.0, 35.0, "03_triangle_positive_orientation"),
        ("PolygonTriangleNegative", 0.0, 0.0, -30.0, "04_triangle_negative_orientation"),
        ("PolygonTriangleWrapped", 0.0, 0.0, 390.0, "05_triangle_wrapped_orientation"),
    ):
        document, _, result = _new_profile(
            adapter,
            name,
            side_count=3,
            radius=15.0 if x else 20.0,
            x=x,
            y=y,
            angle=angle,
            profile_type="equilateral_triangle",
        )
        try:
            scenarios[key] = result.profile.first_vertex_angle_degrees
        finally:
            rectangle_smoke._close(document)

    document, sketch = rectangle_smoke._new_sketch("PolygonTriangleExisting")
    try:
        sketch.addGeometry(Part.LineSegment(App.Vector(-2, 30, 0), App.Vector(2, 30, 0)), False)
        sketch.addGeometry(Part.Point(App.Vector(7, 8, 0)), True)
        sketch.addConstraint(Sketcher.Constraint("Horizontal", 0))
        sketch.addConstraint(Sketcher.Constraint("DistanceX", 0, 1, -2.0))
        sketch.addConstraint(Sketcher.Constraint("DistanceY", 0, 1, 30.0))
        sketch.addConstraint(Sketcher.Constraint("Distance", 0, 4.0))
        sketch.addConstraint(Sketcher.Constraint("DistanceX", 1, 1, 7.0))
        sketch.addConstraint(Sketcher.Constraint("DistanceY", 1, 1, 8.0))
        document.recompute()
        document.clearUndos()
        before = (_point(sketch.Geometry[0].StartPoint), _point(sketch.Geometry[0].EndPoint))
        result = adapter.create_sketch_polygon(
            _request(
                document,
                sketch,
                side_count=3,
                angle=90.0,
                profile_type="equilateral_triangle",
            )
        )
        _basic_assertions(
            sketch,
            result,
            side_count=3,
            radius=20.0,
            x=0.0,
            y=0.0,
            angle=90.0,
            first_geometry_index=2,
        )
        assert before == (
            _point(sketch.Geometry[0].StartPoint),
            _point(sketch.Geometry[0].EndPoint),
        )
        scenarios["14_triangle_existing_non_empty_sketch"] = result.profile.geometry_indices
    finally:
        rectangle_smoke._close(document)

    for attached, key in (
        (False, "15_triangle_body_owned_sketch"),
        (True, "16_triangle_xy_attached_sketch"),
    ):
        document = rectangle_smoke._new_document(f"PolygonTriangleBody{attached}")
        try:
            body = document.addObject("PartDesign::Body", "Body")
            document.recompute()
            adapter.create_sketch(
                str(document.Name),
                str(body.Name),
                "Sketch",
                None,
                OriginPlane.XY if attached else None,
            )
            sketch = document.getObject("Sketch")
            assert sketch is not None
            document.clearUndos()
            parent = sketch.getParentGeoFeatureGroup()
            support = sketch.AttachmentSupport
            map_mode = str(sketch.MapMode)
            adapter.create_sketch_polygon(
                _request(
                    document,
                    sketch,
                    side_count=3,
                    angle=90.0,
                    profile_type="equilateral_triangle",
                )
            )
            assert sketch.getParentGeoFeatureGroup() is parent
            assert sketch.AttachmentSupport == support and str(sketch.MapMode) == map_mode
            scenarios[key] = map_mode
        finally:
            rectangle_smoke._close(document)

    document, sketch, _ = _new_profile(
        adapter,
        "PolygonTriangleHistory",
        side_count=3,
        angle=90.0,
        profile_type="equilateral_triangle",
    )
    try:
        history = adapter.get_document_history(str(document.Name)).history
        assert history.next_undo_name == CREATE_SKETCH_EQUILATERAL_TRIANGLE_TRANSACTION_NAME
        adapter.undo_document(
            str(document.Name), CREATE_SKETCH_EQUILATERAL_TRIANGLE_TRANSACTION_NAME
        )
        document.recompute()
        assert int(sketch.GeometryCount) == 0 and int(sketch.ConstraintCount) == 0
        scenarios["17_triangle_one_step_undo"] = True
        adapter.redo_document(
            str(document.Name), CREATE_SKETCH_EQUILATERAL_TRIANGLE_TRANSACTION_NAME
        )
        document.recompute()
        assert int(sketch.GeometryCount) == 5 and int(sketch.DoF) == 0
        scenarios["18_triangle_one_step_redo"] = True
        assert sketch.getConstruction(3) and sketch.getConstruction(4)
        scenarios["19_triangle_construction_restoration"] = [3, 4]
    finally:
        rectangle_smoke._close(document)

    document, sketch = rectangle_smoke._new_sketch("PolygonTriangleValidation")
    try:
        before = adapter.get_document_history(str(document.Name)).history
        invalid = validate_create_sketch_equilateral_triangle_request(
            str(document.Name), str(sketch.Name), 0.0, {"x": 0.0, "y": 0.0}
        )
        assert not hasattr(invalid, "circumradius")
        assert before == adapter.get_document_history(str(document.Name)).history
        assert int(sketch.GeometryCount) == 0
        scenarios["20_triangle_failed_validation_no_transaction"] = True
    finally:
        rectangle_smoke._close(document)

    scenarios["21_triangle_geometry_failure_rollback"] = _injected_failure(
        adapter, "TriangleGeometry", "geometry", 2, triangle=True
    )
    scenarios["22_triangle_constraint_failure_rollback"] = _injected_failure(
        adapter, "TriangleConstraint", "constraint", 3, triangle=True
    )
    scenarios["23_triangle_verification_failure_rollback"] = _verification_failure(
        adapter, "TriangleVerification", triangle=True
    )


def _polygon_geometry_cases(adapter: FreeCADDocumentAdapter, scenarios: dict[str, object]) -> None:
    cases = (
        (3, 20.0, 0.0, 0.0, 0.0, "24_polygon_generic_triangle"),
        (4, 20.0, 0.0, 0.0, 45.0, "25_polygon_axis_aligned_square"),
        (5, 20.0, 0.0, 0.0, 90.0, "26_polygon_pentagon"),
        (6, 20.0, 10.0, -5.0, 0.0, "27_polygon_hexagon"),
        (12, 20.0, 0.0, 0.0, 15.0, "28_polygon_twelve_sides"),
        (MAX_REGULAR_POLYGON_SIDE_COUNT, 20.0, 0.0, 0.0, 0.0, "29_polygon_maximum"),
    )
    for side_count, radius, x, y, angle, key in cases:
        document, sketch, result = _new_profile(
            adapter,
            f"PolygonN{side_count}{key[-2:]}",
            side_count=side_count,
            radius=radius,
            x=x,
            y=y,
            angle=angle,
        )
        try:
            scenarios[key] = {
                "geometry": int(sketch.GeometryCount),
                "constraints": int(sketch.ConstraintCount),
                "first": result.profile.vertices[0].to_dict(),
            }
            if side_count == 3:
                scenarios["30_polygon_minimum"] = True
            if side_count == 6:
                scenarios["38_polygon_deterministic_edge_order"] = [
                    edge.to_dict() for edge in result.profile.edges
                ]
                scenarios["39_polygon_deterministic_vertex_order"] = [
                    vertex.to_dict() for vertex in result.profile.vertices
                ]
                scenarios["40_polygon_equal_side_lengths"] = True
                scenarios["41_polygon_exact_circumradius"] = radius
                scenarios["42_polygon_zero_dof"] = int(sketch.DoF)
                scenarios["43_polygon_clean_diagnostics"] = True
        finally:
            rectangle_smoke._close(document)

    for value, key in (
        (2, "31_polygon_below_minimum_rejection"),
        (MAX_REGULAR_POLYGON_SIDE_COUNT + 1, "32_polygon_above_maximum_rejection"),
        (True, "33_polygon_boolean_side_count_rejection"),
    ):
        invalid = validate_create_sketch_regular_polygon_request(
            "Model", "Sketch", value, 20.0, {"x": 0.0, "y": 0.0}
        )
        assert not hasattr(invalid, "side_count")
        scenarios[key] = True

    document, _, result = _new_profile(adapter, "PolygonArbitrary", x=12.0, y=-7.0, angle=30.0)
    try:
        scenarios["34_polygon_arbitrary_center"] = result.profile.center.to_dict()
    finally:
        rectangle_smoke._close(document)

    branches: dict[str, int] = {}
    for name, x, y in (
        ("origin", 0.0, 0.0),
        ("vertical", 0.0, 9.0),
        ("horizontal", 8.0, 0.0),
        ("free", 8.0, -6.0),
    ):
        document, sketch, _ = _new_profile(adapter, f"PolygonBranch{name}", x=x, y=y)
        try:
            branches[name] = int(sketch.ConstraintCount)
        finally:
            rectangle_smoke._close(document)
    assert branches == {"origin": 21, "vertical": 22, "horizontal": 22, "free": 22}
    scenarios["35_polygon_all_center_placement_branches"] = branches

    for angle, key in (
        (-30.0, "36_polygon_negative_orientation"),
        (390.0, "37_polygon_wrapped_orientation"),
    ):
        document, _, result = _new_profile(adapter, f"PolygonAngle{key[-2:]}", angle=angle)
        try:
            scenarios[key] = result.profile.first_vertex_angle_degrees
        finally:
            rectangle_smoke._close(document)


def _polygon_context_cases(adapter: FreeCADDocumentAdapter, scenarios: dict[str, object]) -> None:
    document, sketch = rectangle_smoke._new_sketch("PolygonExisting")
    try:
        sketch.addGeometry(Part.LineSegment(App.Vector(-5, 40, 0), App.Vector(5, 40, 0)), False)
        sketch.addGeometry(Part.Point(App.Vector(8, 9, 0)), True)
        sketch.addConstraint(Sketcher.Constraint("Horizontal", 0))
        sketch.addConstraint(Sketcher.Constraint("DistanceX", 0, 1, -5.0))
        sketch.addConstraint(Sketcher.Constraint("DistanceY", 0, 1, 40.0))
        sketch.addConstraint(Sketcher.Constraint("Distance", 0, 10.0))
        sketch.addConstraint(Sketcher.Constraint("DistanceX", 1, 1, 8.0))
        sketch.addConstraint(Sketcher.Constraint("DistanceY", 1, 1, 9.0))
        document.recompute()
        document.clearUndos()
        old_line = (_point(sketch.Geometry[0].StartPoint), _point(sketch.Geometry[0].EndPoint))
        old_flag = bool(sketch.getConstruction(1))
        result = adapter.create_sketch_polygon(_request(document, sketch, side_count=5, angle=90.0))
        _basic_assertions(
            sketch,
            result,
            side_count=5,
            radius=20.0,
            x=0.0,
            y=0.0,
            angle=90.0,
            first_geometry_index=2,
        )
        assert old_line == (
            _point(sketch.Geometry[0].StartPoint),
            _point(sketch.Geometry[0].EndPoint),
        )
        assert old_flag and sketch.getConstruction(1)
        scenarios["44_polygon_existing_non_empty_sketch"] = result.profile.geometry_indices
        scenarios["45_polygon_existing_construction_preservation"] = True
    finally:
        rectangle_smoke._close(document)

    for attached, key in (
        (False, "46_polygon_body_owned_sketch"),
        (True, "47_polygon_xy_attached_sketch"),
    ):
        document = rectangle_smoke._new_document(f"PolygonBody{attached}")
        try:
            body = document.addObject("PartDesign::Body", "Body")
            document.recompute()
            adapter.create_sketch(
                str(document.Name),
                str(body.Name),
                "Sketch",
                None,
                OriginPlane.XY if attached else None,
            )
            sketch = document.getObject("Sketch")
            assert sketch is not None
            document.clearUndos()
            parent = sketch.getParentGeoFeatureGroup()
            support = sketch.AttachmentSupport
            map_mode = str(sketch.MapMode)
            adapter.create_sketch_polygon(_request(document, sketch, side_count=5, angle=90.0))
            assert sketch.getParentGeoFeatureGroup() is parent
            assert sketch.AttachmentSupport == support and str(sketch.MapMode) == map_mode
            scenarios[key] = map_mode
        finally:
            rectangle_smoke._close(document)

    document, sketch, _ = _new_profile(adapter, "PolygonUnsaved")
    try:
        assert str(document.FileName) == ""
        scenarios["48_polygon_unsaved_document"] = True
    finally:
        rectangle_smoke._close(document)

    with tempfile.TemporaryDirectory(prefix="freecad-mcp-polygon-") as directory:
        document, sketch = rectangle_smoke._new_sketch("PolygonSaved")
        path = Path(directory) / "polygon.FCStd"
        try:
            document.saveAs(str(path))
            before = (path.stat().st_size, path.stat().st_mtime_ns, rectangle_smoke._digest(path))
            adapter.create_sketch_polygon(_request(document, sketch))
            adapter.undo_document(
                str(document.Name), CREATE_SKETCH_REGULAR_POLYGON_TRANSACTION_NAME
            )
            adapter.redo_document(
                str(document.Name), CREATE_SKETCH_REGULAR_POLYGON_TRANSACTION_NAME
            )
            after = (path.stat().st_size, path.stat().st_mtime_ns, rectangle_smoke._digest(path))
            assert before == after
            scenarios["49_polygon_saved_file_preservation"] = before
        finally:
            rectangle_smoke._close(document)


def _polygon_history_and_failures(
    adapter: FreeCADDocumentAdapter, scenarios: dict[str, object]
) -> None:
    document, sketch, _ = _new_profile(adapter, "PolygonHistory", side_count=12)
    try:
        before = (int(sketch.GeometryCount), int(sketch.ConstraintCount), int(document.UndoCount))
        try:
            adapter.undo_document(str(document.Name), "Wrong polygon name")
            raise AssertionError("expected history-name mismatch")
        except DocumentHistoryTransactionMismatchError:
            pass
        assert before == (
            int(sketch.GeometryCount),
            int(sketch.ConstraintCount),
            int(document.UndoCount),
        )
        scenarios["52_polygon_expected_name_mismatch"] = True
        adapter.undo_document(str(document.Name), CREATE_SKETCH_REGULAR_POLYGON_TRANSACTION_NAME)
        document.recompute()
        assert int(sketch.GeometryCount) == 0 and int(sketch.ConstraintCount) == 0
        scenarios["50_polygon_one_step_undo"] = True
        adapter.redo_document(str(document.Name), CREATE_SKETCH_REGULAR_POLYGON_TRANSACTION_NAME)
        document.recompute()
        assert int(sketch.GeometryCount) == 14 and int(sketch.DoF) == 0
        scenarios["51_polygon_one_step_redo"] = True
        adapter.undo_document(str(document.Name), CREATE_SKETCH_REGULAR_POLYGON_TRANSACTION_NAME)
        payload = validate_add_sketch_geometry_request(
            str(document.Name),
            str(sketch.Name),
            [{"type": "point", "position": {"x": 1.0, "y": 2.0}, "construction": False}],
        )
        assert isinstance(payload, tuple)
        adapter.add_sketch_geometry(str(document.Name), str(sketch.Name), payload)
        assert not adapter.get_document_history(str(document.Name)).history.can_redo
        scenarios["53_polygon_redo_invalidation"] = True
    finally:
        rectangle_smoke._close(document)

    document, sketch = rectangle_smoke._new_sketch("PolygonValidation")
    try:
        before = adapter.get_document_history(str(document.Name)).history
        invalid = validate_create_sketch_regular_polygon_request(
            str(document.Name), str(sketch.Name), 2, 20.0, {"x": 0.0, "y": 0.0}
        )
        assert not hasattr(invalid, "side_count")
        assert before == adapter.get_document_history(str(document.Name)).history
        assert int(sketch.GeometryCount) == 0
        scenarios["54_polygon_failed_validation_no_transaction"] = True
    finally:
        rectangle_smoke._close(document)

    scenarios["55_polygon_geometry_failure_rollback"] = _injected_failure(
        adapter, "PolygonGeometry", "geometry", 3
    )
    scenarios["56_polygon_reference_failure_rollback"] = _injected_failure(
        adapter, "PolygonReference", "reference", 1
    )
    scenarios["57_polygon_constraint_failure_rollback"] = _injected_failure(
        adapter, "PolygonConstraint", "constraint", 7
    )
    scenarios["58_polygon_verification_failure_rollback"] = _verification_failure(
        adapter, "PolygonVerification"
    )

    first, first_sketch = rectangle_smoke._new_sketch("PolygonIsolationA")
    second, second_sketch = rectangle_smoke._new_sketch("PolygonIsolationB")
    try:
        adapter.create_sketch_polygon(_request(first, first_sketch))
        assert int(second_sketch.GeometryCount) == 0
        assert int(second_sketch.ConstraintCount) == 0 and int(second.UndoCount) == 0
        scenarios["59_polygon_cross_document_isolation"] = True
    finally:
        rectangle_smoke._close(second)
        rectangle_smoke._close(first)


def _injected_failure(
    adapter: FreeCADDocumentAdapter,
    name: str,
    target_phase: str,
    target_call: int,
    *,
    triangle: bool = False,
) -> bool:
    document, sketch = rectangle_smoke._new_sketch(name)
    original = sketch_polygon_creation._verify_assigned_index
    calls = {"geometry": 0, "reference": 0, "constraint": 0}

    def verifier(value: object, expected: int, phase: str) -> None:
        original(value, expected, phase)
        calls[phase] += 1
        if phase == target_phase and calls[phase] == target_call:
            raise SketchPolygonCreationError(phase=phase, reason="injected_index_failure")

    sketch_polygon_creation._verify_assigned_index = verifier
    try:
        try:
            adapter.create_sketch_polygon(
                _request(
                    document,
                    sketch,
                    side_count=3 if triangle else 6,
                    angle=90.0 if triangle else 0.0,
                    profile_type="equilateral_triangle" if triangle else "regular_polygon",
                )
            )
            raise AssertionError("injected polygon failure was not raised")
        except SketchPolygonCreationError:
            pass
        assert int(sketch.GeometryCount) == 0 and int(sketch.ConstraintCount) == 0
        assert int(document.UndoCount) == 0
        return True
    finally:
        sketch_polygon_creation._verify_assigned_index = original
        rectangle_smoke._close(document)


def _verification_failure(
    adapter: FreeCADDocumentAdapter, name: str, *, triangle: bool = False
) -> bool:
    document, sketch = rectangle_smoke._new_sketch(name)
    original = sketch_polygon_creation._verify_polygon

    def verifier(**kwargs: object) -> None:
        raise SketchPolygonVerificationError("injected_verification_failure")

    sketch_polygon_creation._verify_polygon = verifier
    try:
        try:
            adapter.create_sketch_polygon(
                _request(
                    document,
                    sketch,
                    side_count=3 if triangle else 6,
                    angle=90.0 if triangle else 0.0,
                    profile_type="equilateral_triangle" if triangle else "regular_polygon",
                )
            )
            raise AssertionError("injected polygon verification failure was not raised")
        except SketchPolygonVerificationError:
            pass
        assert int(sketch.GeometryCount) == 0 and int(sketch.ConstraintCount) == 0
        assert int(document.UndoCount) == 0
        return True
    finally:
        sketch_polygon_creation._verify_polygon = original
        rectangle_smoke._close(document)


def _selection_and_regressions(
    adapter: FreeCADDocumentAdapter, scenarios: dict[str, object]
) -> None:
    assert (
        "explicitly requests an equilateral triangle"
        in CREATE_SKETCH_EQUILATERAL_TRIANGLE_DESCRIPTION
    )
    assert (
        "generic request for a regular polygon with three sides"
        in CREATE_SKETCH_REGULAR_POLYGON_DESCRIPTION
    )
    assert (
        "create_sketch_rectangle for lower-left placement"
        in CREATE_SKETCH_REGULAR_POLYGON_DESCRIPTION
    )
    assert (
        "create_sketch_centered_rectangle for centre placement"
        in CREATE_SKETCH_REGULAR_POLYGON_DESCRIPTION
    )
    scenarios["60_triangle_vs_polygon_tool_selection"] = {
        "explicit_triangle": "create_sketch_equilateral_triangle",
        "generic_three_sides": "create_sketch_regular_polygon",
        "irregular_triangle": "add_sketch_geometry",
        "relationships": "add_sketch_constraints",
    }

    document, sketch = rectangle_smoke._new_sketch("PolygonRectangleRegression")
    try:
        result = adapter.create_sketch_rectangle(
            SketchRectangleRequestInput.model_validate(
                {
                    "document_name": str(document.Name),
                    "sketch_name": str(sketch.Name),
                    "width": 30.0,
                    "height": 20.0,
                    "placement": {"type": "lower_left", "x": -15.0, "y": -10.0},
                }
            )
        )
        assert result.profile.geometry_indices == (0, 1, 2, 3) and int(sketch.DoF) == 0
        assert "lower-left placement" in CREATE_SKETCH_RECTANGLE_DESCRIPTION
        scenarios["61_rectangle_tool_regression"] = True
    finally:
        rectangle_smoke._close(document)

    document, sketch = rectangle_smoke._new_sketch("PolygonCenteredRegression")
    try:
        result = adapter.create_sketch_centered_rectangle(
            SketchCenteredRectangleRequestInput.model_validate(
                {
                    "document_name": str(document.Name),
                    "sketch_name": str(sketch.Name),
                    "width": 30.0,
                    "height": 20.0,
                    "center": {"x": 0.0, "y": 0.0},
                }
            )
        )
        assert result.profile.geometry_indices == (0, 1, 2, 3) and int(sketch.DoF) == 0
        assert "centre intent" in CREATE_SKETCH_CENTERED_RECTANGLE_DESCRIPTION
        scenarios["62_centered_rectangle_regression"] = True
    finally:
        rectangle_smoke._close(document)

    tangent = smoke_sketch_tangent._combined_regression(adapter)
    assert (
        tangent["32_symmetry_point_relationship_tangent_regression"]["solver"]["degrees_of_freedom"]
        == 0
    )
    scenarios["63_tangency_regression"] = True
    symmetric = smoke_sketch_symmetric._centred_rectangle(adapter)
    assert symmetric["solver"]["degrees_of_freedom"] == 0
    scenarios["64_symmetry_regression"] = True
    cardinal = smoke_sketch_point_relationships._cardinal_regression(adapter)
    assert cardinal["24_circle_cardinal_point_regression"]["degrees_of_freedom"] == 0
    scenarios["65_point_relationship_regression"] = True
    assert smoke_document_history._workflow_cases(adapter)
    scenarios["66_document_history_regression"] = True


def _recovery_cases(adapter: FreeCADDocumentAdapter, scenarios: dict[str, object]) -> None:
    document, sketch, _ = _new_profile(
        adapter,
        "PolygonTriangleRecovery",
        side_count=3,
        x=40.0,
        y=30.0,
        angle=0.0,
        profile_type="equilateral_triangle",
    )
    try:
        adapter.undo_document(
            str(document.Name), CREATE_SKETCH_EQUILATERAL_TRIANGLE_TRANSACTION_NAME
        )
        adapter.create_sketch_polygon(
            _request(
                document,
                sketch,
                side_count=3,
                angle=90.0,
                profile_type="equilateral_triangle",
            )
        )
        document.recompute()
        assert _same(_point(sketch.Geometry[0].StartPoint), (0.0, 20.0))
        assert not adapter.get_document_history(str(document.Name)).history.can_redo
        assert len([item for item in document.Objects if str(item.Name) == "Sketch"]) == 1
        scenarios["67_same_sketch_triangle_correction"] = True
    finally:
        rectangle_smoke._close(document)

    document, sketch, _ = _new_profile(
        adapter, "PolygonRecovery", side_count=5, radius=12.0, x=30.0, y=25.0, angle=45.0
    )
    try:
        adapter.undo_document(str(document.Name), CREATE_SKETCH_REGULAR_POLYGON_TRANSACTION_NAME)
        adapter.create_sketch_polygon(
            _request(document, sketch, side_count=6, radius=20.0, x=10.0, y=-5.0)
        )
        document.recompute()
        assert int(sketch.GeometryCount) == 8 and int(sketch.DoF) == 0
        assert _same(_point(sketch.Geometry[0].StartPoint), (30.0, -5.0))
        assert not adapter.get_document_history(str(document.Name)).history.can_redo
        assert len([item for item in document.Objects if str(item.Name) == "Sketch"]) == 1
        scenarios["68_same_sketch_polygon_correction"] = True
    finally:
        rectangle_smoke._close(document)


def main() -> int:
    adapter = FreeCADDocumentAdapter()
    scenarios: dict[str, object] = {}
    _triangle_cases(adapter, scenarios)
    _polygon_geometry_cases(adapter, scenarios)
    _polygon_context_cases(adapter, scenarios)
    _polygon_history_and_failures(adapter, scenarios)
    _selection_and_regressions(adapter, scenarios)
    _recovery_cases(adapter, scenarios)
    expected = [f"{index:02d}_" for index in range(1, 69)]
    assert len(scenarios) == 68
    assert all(any(key.startswith(prefix) for key in scenarios) for prefix in expected)
    version = App.Version()
    report = {
        "freecad_version": ".".join(str(item) for item in version[:3]),
        "freecad_build": str(version[3]),
        "freecad_revision": str(version[7]),
        "embedded_python": sys.version.split()[0],
        "scenario_count": 68,
        "pass_count": len(scenarios),
        "constraint_formula": {"origin": "3N+3", "non_origin": "3N+4"},
        "scenarios": scenarios,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    print("Polygon profile smoke passed: 68/68")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
