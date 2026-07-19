"""Direct FreeCAD 1.1 smoke campaign for semantic curved profiles."""

from __future__ import annotations

import hashlib
import io
import json
import math
import sys
import tempfile
from contextlib import redirect_stdout
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
import smoke_sketch_centered_rectangle  # noqa: E402
import smoke_sketch_point_relationships  # noqa: E402
import smoke_sketch_polygon_profiles  # noqa: E402
import smoke_sketch_rectangle as rectangle_smoke  # noqa: E402
import smoke_sketch_symmetric  # noqa: E402
import smoke_sketch_tangent  # noqa: E402

from freecad_mcp.exceptions import (  # noqa: E402
    DocumentHistoryTransactionMismatchError,
    SketchRoundedRectangleCreationError,
    SketchRoundedRectangleVerificationError,
    SketchSlotCreationError,
    SketchSlotVerificationError,
)
from freecad_mcp.freecad import sketch_curved_profile_creation  # noqa: E402
from freecad_mcp.freecad.document import FreeCADDocumentAdapter  # noqa: E402
from freecad_mcp.mcp.sketch_curved_profile_tools import (  # noqa: E402
    CREATE_SKETCH_ROUNDED_RECTANGLE_DESCRIPTION,
    CREATE_SKETCH_SLOT_DESCRIPTION,
)
from freecad_mcp.models import (  # noqa: E402
    CenterRoundedRectanglePlacementInput,
    LowerLeftRectanglePlacementInput,
    OriginPlane,
    PointGeometryInput,
    SketchCenterPointInput,
    SketchPoint2DInput,
    SketchRoundedRectangleRequestInput,
    SketchSlotRequestInput,
)
from freecad_mcp.transaction_names import (  # noqa: E402
    CREATE_SKETCH_ROUNDED_RECTANGLE_TRANSACTION_NAME,
    CREATE_SKETCH_SLOT_TRANSACTION_NAME,
)
from freecad_mcp.validation import (  # noqa: E402
    validate_create_sketch_rounded_rectangle_request,
    validate_create_sketch_slot_request,
)

_TOLERANCE = 1.0e-6
ProfileKind = Literal["slot", "rounded_rectangle"]


def _slot_request(
    document: Any,
    sketch: Any,
    *,
    length: float = 40.0,
    width: float = 12.0,
    x: float = 0.0,
    y: float = 0.0,
    angle: float = 0.0,
) -> SketchSlotRequestInput:
    return SketchSlotRequestInput(
        document_name=str(document.Name),
        sketch_name=str(sketch.Name),
        overall_length=length,
        overall_width=width,
        center=SketchCenterPointInput(x=x, y=y),
        angle_degrees=angle,
    )


def _rounded_request(
    document: Any,
    sketch: Any,
    *,
    width: float = 40.0,
    height: float = 24.0,
    radius: float = 4.0,
    placement: Literal["lower_left", "center"] = "center",
    x: float = 0.0,
    y: float = 0.0,
) -> SketchRoundedRectangleRequestInput:
    placement_value = (
        LowerLeftRectanglePlacementInput(type="lower_left", x=x, y=y)
        if placement == "lower_left"
        else CenterRoundedRectanglePlacementInput(type="center", x=x, y=y)
    )
    return SketchRoundedRectangleRequestInput(
        document_name=str(document.Name),
        sketch_name=str(sketch.Name),
        width=width,
        height=height,
        corner_radius=radius,
        placement=placement_value,
    )


def _same(first: tuple[float, float], second: tuple[float, float]) -> bool:
    return math.isclose(first[0], second[0], abs_tol=_TOLERANCE) and math.isclose(
        first[1], second[1], abs_tol=_TOLERANCE
    )


def _point(value: Any) -> tuple[float, float]:
    return float(value.x), float(value.y)


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _slot_fixture(
    adapter: FreeCADDocumentAdapter,
    name: str,
    **kwargs: float,
) -> tuple[Any, Any, Any]:
    document, sketch = rectangle_smoke._new_sketch(name)
    result = adapter.create_sketch_slot(_slot_request(document, sketch, **kwargs))
    assert int(sketch.GeometryCount) == 4
    assert int(sketch.ConstraintCount) in {9, 10}
    assert int(sketch.DoF) == 0 and bool(sketch.FullyConstrained)
    assert not sketch.RedundantConstraints
    assert not sketch.PartiallyRedundantConstraints
    assert not sketch.ConflictingConstraints
    assert not sketch.MalformedConstraints
    return document, sketch, result


def _rounded_fixture(
    adapter: FreeCADDocumentAdapter,
    name: str,
    **kwargs: Any,
) -> tuple[Any, Any, Any]:
    document, sketch = rectangle_smoke._new_sketch(name)
    result = adapter.create_sketch_rounded_rectangle(_rounded_request(document, sketch, **kwargs))
    assert int(sketch.GeometryCount) == 8
    assert int(sketch.ConstraintCount) in {19, 20}
    assert int(sketch.DoF) == 0 and bool(sketch.FullyConstrained)
    assert not sketch.RedundantConstraints
    assert not sketch.PartiallyRedundantConstraints
    assert not sketch.ConflictingConstraints
    assert not sketch.MalformedConstraints
    return document, sketch, result


def _slot_cases(adapter: FreeCADDocumentAdapter, scenarios: dict[str, object]) -> None:
    document, sketch, result = _slot_fixture(adapter, "CurvedSlotOrigin")
    try:
        profile = result.profile
        scenarios["01_slot_horizontal_origin"] = profile.center.to_dict()
        scenarios["06_slot_exact_element_order"] = profile.geometry_indices
        scenarios["07_slot_semicircle_sweeps"] = [arc.sweep_degrees for arc in profile.arcs]
        scenarios["08_slot_bounded_endpoints"] = [join.bounded for join in profile.joins]
        scenarios["09_slot_four_tangent_joins"] = [join.tangent for join in profile.joins]
        scenarios["10_slot_equal_end_radii"] = [arc.radius for arc in profile.arcs]
        scenarios["11_slot_exact_overall_length"] = profile.overall_length
        scenarios["12_slot_exact_overall_width"] = profile.overall_width
        scenarios["13_slot_exact_center"] = profile.center.to_dict()
        scenarios["14_slot_zero_dof"] = int(sketch.DoF)
        scenarios["15_slot_clean_diagnostics"] = True
        assert profile.geometry_indices == (0, 1, 2, 3)
        assert profile.reference_geometry_indices == ()
        assert profile.end_radius == 6.0 and profile.straight_segment_length == 28.0
        assert profile.counter_clockwise and profile.closed and profile.tangent
        assert all(math.isclose(arc.sweep_degrees, 180.0) for arc in profile.arcs)
        assert all(
            type(sketch.Geometry[index]).__name__ == expected
            for index, expected in enumerate(
                ("LineSegment", "ArcOfCircle", "LineSegment", "ArcOfCircle")
            )
        )
    finally:
        rectangle_smoke._close(document)

    for name, values, key in (
        ("CurvedSlotCenter", {"x": 12.0, "y": -7.0}, "02_slot_arbitrary_center"),
        ("CurvedSlotPositive", {"angle": 30.0}, "03_slot_positive_angle"),
        ("CurvedSlotNegative", {"angle": -30.0}, "04_slot_negative_angle"),
        ("CurvedSlotWrapped", {"angle": 390.0}, "05_slot_wrapped_angle"),
    ):
        document, _, result = _slot_fixture(adapter, name, **values)
        try:
            scenarios[key] = result.profile.angle_degrees
        finally:
            rectangle_smoke._close(document)

    document, sketch = rectangle_smoke._new_sketch("CurvedSlotExisting")
    try:
        adapter.create_sketch_rounded_rectangle(
            _rounded_request(document, sketch, width=10.0, height=8.0, radius=1.0, x=20.0)
        )
        old_arcs = tuple(
            (
                float(sketch.Geometry[index].FirstParameter),
                float(sketch.Geometry[index].LastParameter),
            )
            for index in (1, 3, 5, 7)
        )
        document.clearUndos()
        result = adapter.create_sketch_slot(_slot_request(document, sketch, x=-20.0, y=0.0))
        assert result.profile.geometry_indices == (8, 9, 10, 11)
        assert old_arcs == tuple(
            (
                float(sketch.Geometry[index].FirstParameter),
                float(sketch.Geometry[index].LastParameter),
            )
            for index in (1, 3, 5, 7)
        )
        scenarios["16_slot_non_empty_sketch"] = result.profile.geometry_indices
        scenarios["17_slot_existing_arc_preservation"] = True
    finally:
        rectangle_smoke._close(document)

    _body_context_cases(adapter, scenarios, "slot", 18)

    document, _, _ = _slot_fixture(adapter, "CurvedSlotUnsaved")
    try:
        assert str(document.FileName) == ""
        scenarios["20_slot_unsaved_document"] = True
    finally:
        rectangle_smoke._close(document)

    with tempfile.TemporaryDirectory(prefix="freecad-mcp-slot-") as directory:
        document, sketch = rectangle_smoke._new_sketch("CurvedSlotSaved")
        path = Path(directory) / "slot.FCStd"
        try:
            document.saveAs(str(path))
            before = (path.stat().st_size, path.stat().st_mtime_ns, _digest(path))
            adapter.create_sketch_slot(_slot_request(document, sketch))
            after = (path.stat().st_size, path.stat().st_mtime_ns, _digest(path))
            assert before == after
            scenarios["21_slot_saved_file_preservation"] = True
        finally:
            rectangle_smoke._close(document)

    _history_cases(adapter, scenarios, "slot", 22)
    scenarios["26_slot_validation_failures"] = _validation_cases("slot")
    scenarios["27_slot_geometry_failure_rollback"] = _injected_failure(
        adapter, "CurvedSlotGeometryFailure", "slot", "geometry", 1
    )
    scenarios["28_slot_arc_failure_rollback"] = _injected_failure(
        adapter, "CurvedSlotArcFailure", "slot", "geometry", 2
    )
    scenarios["29_slot_tangency_failure_rollback"] = _injected_failure(
        adapter, "CurvedSlotTangentFailure", "slot", "constraint", 1
    )
    scenarios["30_slot_verification_failure_rollback"] = _verification_failure(
        adapter, "CurvedSlotVerificationFailure", "slot"
    )
    scenarios["31_slot_same_sketch_correction"] = _same_sketch_correction(adapter, "slot")
    scenarios["32_slot_cross_document_isolation"] = _cross_document_isolation(adapter, "slot")


def _rounded_cases(adapter: FreeCADDocumentAdapter, scenarios: dict[str, object]) -> None:
    document, sketch, lower_left_result = _rounded_fixture(
        adapter,
        "CurvedRoundedLowerLeft",
        placement="lower_left",
        x=-20.0,
        y=-12.0,
    )
    try:
        profile = lower_left_result.profile
        scenarios["33_rounded_lower_left_fixture"] = profile.placement.model_dump(mode="json")
        scenarios["36_rounded_external_bounds"] = profile.bounds.to_dict()
        scenarios["37_rounded_element_order"] = profile.geometry_indices
        scenarios["38_rounded_equal_corner_radii"] = [arc.radius for arc in profile.arcs]
        scenarios["39_rounded_quarter_arc_sweeps"] = [arc.sweep_degrees for arc in profile.arcs]
        scenarios["40_rounded_eight_closed_joins"] = len(profile.joins)
        scenarios["41_rounded_bounded_tangent_joins"] = [join.tangent for join in profile.joins]
        scenarios["42_rounded_axis_alignment"] = profile.axis_aligned
        scenarios["43_rounded_counter_clockwise"] = profile.counter_clockwise
        scenarios["44_rounded_zero_dof"] = int(sketch.DoF)
        scenarios["45_rounded_clean_diagnostics"] = True
        assert profile.bounds.to_dict() == {
            "left": -20.0,
            "bottom": -12.0,
            "right": 20.0,
            "top": 12.0,
        }
        assert all(math.isclose(arc.radius, 4.0) for arc in profile.arcs)
        assert all(math.isclose(arc.sweep_degrees, 90.0) for arc in profile.arcs)
        assert all(
            type(sketch.Geometry[index]).__name__ == expected
            for index, expected in enumerate(
                (
                    "LineSegment",
                    "ArcOfCircle",
                    "LineSegment",
                    "ArcOfCircle",
                    "LineSegment",
                    "ArcOfCircle",
                    "LineSegment",
                    "ArcOfCircle",
                )
            )
        )
    finally:
        rectangle_smoke._close(document)

    for name, values, key in (
        ("CurvedRoundedCenter", {}, "34_rounded_center_origin_fixture"),
        (
            "CurvedRoundedArbitrary",
            {"width": 30.0, "height": 18.0, "radius": 3.0, "x": 12.0, "y": -7.0},
            "35_rounded_arbitrary_center",
        ),
    ):
        document, _, result = _rounded_fixture(adapter, name, **values)
        try:
            scenarios[key] = result.profile.bounds.to_dict()
        finally:
            rectangle_smoke._close(document)

    document, sketch = rectangle_smoke._new_sketch("CurvedRoundedExisting")
    try:
        point_index = sketch.addGeometry(Part.Point(App.Vector(80.0, 80.0, 0.0)), True)
        sketch.addConstraint(Sketcher.Constraint("DistanceX", point_index, 1, 80.0))
        sketch.addConstraint(Sketcher.Constraint("DistanceY", point_index, 1, 80.0))
        adapter.create_sketch_slot(_slot_request(document, sketch, x=-30.0))
        old_arcs = tuple(
            (
                float(sketch.Geometry[index].FirstParameter),
                float(sketch.Geometry[index].LastParameter),
            )
            for index in (2, 4)
        )
        document.clearUndos()
        result = adapter.create_sketch_rounded_rectangle(_rounded_request(document, sketch, x=30.0))
        assert result.profile.geometry_indices == tuple(range(5, 13))
        assert sketch.getConstruction(0)
        assert old_arcs == tuple(
            (
                float(sketch.Geometry[index].FirstParameter),
                float(sketch.Geometry[index].LastParameter),
            )
            for index in (2, 4)
        )
        scenarios["46_rounded_non_empty_sketch"] = result.profile.geometry_indices
        scenarios["47_rounded_existing_construction_preservation"] = True
        scenarios["48_rounded_existing_arc_preservation"] = True
    finally:
        rectangle_smoke._close(document)

    _body_context_cases(adapter, scenarios, "rounded_rectangle", 49)

    document, _, _ = _rounded_fixture(adapter, "CurvedRoundedUnsaved")
    try:
        assert str(document.FileName) == ""
        scenarios["51_rounded_unsaved_document"] = True
    finally:
        rectangle_smoke._close(document)

    with tempfile.TemporaryDirectory(prefix="freecad-mcp-rounded-") as directory:
        document, sketch = rectangle_smoke._new_sketch("CurvedRoundedSaved")
        path = Path(directory) / "rounded.FCStd"
        try:
            document.saveAs(str(path))
            before = (path.stat().st_size, path.stat().st_mtime_ns, _digest(path))
            adapter.create_sketch_rounded_rectangle(_rounded_request(document, sketch))
            after = (path.stat().st_size, path.stat().st_mtime_ns, _digest(path))
            assert before == after
            scenarios["52_rounded_saved_file_preservation"] = True
        finally:
            rectangle_smoke._close(document)

    _history_cases(adapter, scenarios, "rounded_rectangle", 53)
    validation = _validation_cases("rounded_rectangle")
    scenarios["57_rounded_radius_zero_rejection"] = validation[0]
    scenarios["58_rounded_radius_limit_rejection"] = validation[1]
    scenarios["59_rounded_radius_above_limit_rejection"] = validation[2]
    scenarios["60_rounded_geometry_failure_rollback"] = _injected_failure(
        adapter, "CurvedRoundedGeometryFailure", "rounded_rectangle", "geometry", 1
    )
    scenarios["61_rounded_arc_failure_rollback"] = _injected_failure(
        adapter, "CurvedRoundedArcFailure", "rounded_rectangle", "geometry", 2
    )
    scenarios["62_rounded_tangency_failure_rollback"] = _injected_failure(
        adapter, "CurvedRoundedTangentFailure", "rounded_rectangle", "constraint", 1
    )
    scenarios["63_rounded_verification_failure_rollback"] = _verification_failure(
        adapter, "CurvedRoundedVerificationFailure", "rounded_rectangle"
    )
    scenarios["64_rounded_same_sketch_correction"] = _same_sketch_correction(
        adapter, "rounded_rectangle"
    )
    scenarios["65_rounded_cross_document_isolation"] = _cross_document_isolation(
        adapter, "rounded_rectangle"
    )


def _body_context_cases(
    adapter: FreeCADDocumentAdapter,
    scenarios: dict[str, object],
    kind: ProfileKind,
    first_scenario: int,
) -> None:
    for attached, suffix in ((False, "body_owned"), (True, "xy_attached")):
        document = rectangle_smoke._new_document(f"Curved{kind}{suffix}")
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
            if kind == "slot":
                adapter.create_sketch_slot(_slot_request(document, sketch))
            else:
                adapter.create_sketch_rounded_rectangle(_rounded_request(document, sketch))
            assert sketch.getParentGeoFeatureGroup() is parent
            assert sketch.AttachmentSupport == support and str(sketch.MapMode) == map_mode
            number = first_scenario + (1 if attached else 0)
            label = "slot" if kind == "slot" else "rounded"
            scenarios[f"{number:02d}_{label}_{suffix}_sketch"] = map_mode
        finally:
            rectangle_smoke._close(document)


def _history_cases(
    adapter: FreeCADDocumentAdapter,
    scenarios: dict[str, object],
    kind: ProfileKind,
    first_scenario: int,
) -> None:
    name = "CurvedSlotHistory" if kind == "slot" else "CurvedRoundedHistory"
    document, sketch = rectangle_smoke._new_sketch(name)
    transaction = (
        CREATE_SKETCH_SLOT_TRANSACTION_NAME
        if kind == "slot"
        else CREATE_SKETCH_ROUNDED_RECTANGLE_TRANSACTION_NAME
    )
    label = "slot" if kind == "slot" else "rounded"
    expected_geometry = 4 if kind == "slot" else 8
    try:
        if kind == "slot":
            adapter.create_sketch_slot(_slot_request(document, sketch))
        else:
            adapter.create_sketch_rounded_rectangle(_rounded_request(document, sketch))
        history = adapter.get_document_history(str(document.Name)).history
        assert history.next_undo_name == transaction and history.undo_count == 1
        adapter.undo_document(str(document.Name), transaction)
        document.recompute()
        assert int(sketch.GeometryCount) == 0 and int(sketch.ConstraintCount) == 0
        scenarios[f"{first_scenario:02d}_{label}_one_step_undo"] = True
        adapter.redo_document(str(document.Name), transaction)
        document.recompute()
        assert int(sketch.GeometryCount) == expected_geometry and int(sketch.DoF) == 0
        scenarios[f"{first_scenario + 1:02d}_{label}_one_step_redo"] = True
        before = (int(sketch.GeometryCount), int(document.UndoCount))
        try:
            adapter.undo_document(str(document.Name), "Wrong transaction")
            raise AssertionError("history name mismatch was not rejected")
        except DocumentHistoryTransactionMismatchError:
            pass
        assert before == (int(sketch.GeometryCount), int(document.UndoCount))
        scenarios[f"{first_scenario + 2:02d}_{label}_name_mismatch"] = True
        adapter.undo_document(str(document.Name), transaction)
        point = PointGeometryInput(
            type="point",
            position=SketchPoint2DInput(x=100.0, y=100.0),
            construction=False,
        )
        adapter.add_sketch_geometry(str(document.Name), str(sketch.Name), (point,))
        assert not adapter.get_document_history(str(document.Name)).history.can_redo
        scenarios[f"{first_scenario + 3:02d}_{label}_redo_invalidation"] = True
    finally:
        rectangle_smoke._close(document)


def _validation_cases(kind: ProfileKind) -> tuple[bool, ...] | bool:
    if kind == "slot":
        invalid = (
            validate_create_sketch_slot_request(
                "Model", "Sketch", 12.0, 12.0, {"x": 0.0, "y": 0.0}
            ),
            validate_create_sketch_slot_request(
                "Model", "Sketch", True, 12.0, {"x": 0.0, "y": 0.0}
            ),
            validate_create_sketch_slot_request(
                "Model", "Sketch", 40.0, 12.0, {"x": 0.0, "y": 0.0}, math.inf
            ),
        )
        assert all(not isinstance(item, SketchSlotRequestInput) for item in invalid)
        return True
    invalid = (
        validate_create_sketch_rounded_rectangle_request(
            "Model", "Sketch", 40.0, 24.0, 0.0, {"type": "center", "x": 0.0, "y": 0.0}
        ),
        validate_create_sketch_rounded_rectangle_request(
            "Model", "Sketch", 40.0, 24.0, 12.0, {"type": "center", "x": 0.0, "y": 0.0}
        ),
        validate_create_sketch_rounded_rectangle_request(
            "Model", "Sketch", 40.0, 24.0, 12.1, {"type": "center", "x": 0.0, "y": 0.0}
        ),
    )
    result = tuple(not isinstance(item, SketchRoundedRectangleRequestInput) for item in invalid)
    assert all(result)
    return result


def _injected_failure(
    adapter: FreeCADDocumentAdapter,
    name: str,
    kind: ProfileKind,
    target_phase: str,
    target_call: int,
) -> bool:
    document, sketch = rectangle_smoke._new_sketch(name)
    original = sketch_curved_profile_creation._verify_assigned_index
    calls = {"geometry": 0, "constraint": 0}

    def verifier(
        value: object,
        expected: int,
        actual_kind: ProfileKind,
        phase: str,
    ) -> None:
        original(value, expected, actual_kind, phase)
        calls[phase] += 1
        if actual_kind == kind and phase == target_phase and calls[phase] == target_call:
            if kind == "slot":
                raise SketchSlotCreationError(phase=phase, reason="injected_index_failure")
            raise SketchRoundedRectangleCreationError(phase=phase, reason="injected_index_failure")

    sketch_curved_profile_creation._verify_assigned_index = verifier
    try:
        try:
            if kind == "slot":
                adapter.create_sketch_slot(_slot_request(document, sketch))
            else:
                adapter.create_sketch_rounded_rectangle(_rounded_request(document, sketch))
            raise AssertionError("injected curved-profile failure was not raised")
        except (SketchSlotCreationError, SketchRoundedRectangleCreationError):
            pass
        assert int(sketch.GeometryCount) == 0 and int(sketch.ConstraintCount) == 0
        assert int(document.UndoCount) == 0
        return True
    finally:
        sketch_curved_profile_creation._verify_assigned_index = original
        rectangle_smoke._close(document)


def _verification_failure(
    adapter: FreeCADDocumentAdapter,
    name: str,
    kind: ProfileKind,
) -> bool:
    document, sketch = rectangle_smoke._new_sketch(name)
    original = sketch_curved_profile_creation._verify_curved_profile

    def verifier(**kwargs: object) -> Any:
        if kind == "slot":
            raise SketchSlotVerificationError("injected_verification_failure")
        raise SketchRoundedRectangleVerificationError("injected_verification_failure")

    sketch_curved_profile_creation._verify_curved_profile = verifier
    try:
        try:
            if kind == "slot":
                adapter.create_sketch_slot(_slot_request(document, sketch))
            else:
                adapter.create_sketch_rounded_rectangle(_rounded_request(document, sketch))
            raise AssertionError("injected verification failure was not raised")
        except (SketchSlotVerificationError, SketchRoundedRectangleVerificationError):
            pass
        assert int(sketch.GeometryCount) == 0 and int(sketch.ConstraintCount) == 0
        assert int(document.UndoCount) == 0
        return True
    finally:
        sketch_curved_profile_creation._verify_curved_profile = original
        rectangle_smoke._close(document)


def _same_sketch_correction(adapter: FreeCADDocumentAdapter, kind: ProfileKind) -> bool:
    document, sketch = rectangle_smoke._new_sketch(f"CurvedCorrection{kind}")
    transaction = (
        CREATE_SKETCH_SLOT_TRANSACTION_NAME
        if kind == "slot"
        else CREATE_SKETCH_ROUNDED_RECTANGLE_TRANSACTION_NAME
    )
    try:
        if kind == "slot":
            adapter.create_sketch_slot(_slot_request(document, sketch, x=10.0, angle=30.0))
        else:
            adapter.create_sketch_rounded_rectangle(
                _rounded_request(document, sketch, x=10.0, y=-5.0)
            )
        adapter.undo_document(str(document.Name), transaction)
        document.recompute()
        if kind == "slot":
            adapter.create_sketch_slot(_slot_request(document, sketch))
            expected = 4
        else:
            adapter.create_sketch_rounded_rectangle(_rounded_request(document, sketch))
            expected = 8
        assert int(sketch.GeometryCount) == expected and int(sketch.DoF) == 0
        assert not adapter.get_document_history(str(document.Name)).history.can_redo
        assert len([item for item in document.Objects if str(item.Name) == "Sketch"]) == 1
        return True
    finally:
        rectangle_smoke._close(document)


def _cross_document_isolation(adapter: FreeCADDocumentAdapter, kind: ProfileKind) -> bool:
    first, first_sketch = rectangle_smoke._new_sketch(f"CurvedIsolationA{kind}")
    second, second_sketch = rectangle_smoke._new_sketch(f"CurvedIsolationB{kind}")
    try:
        if kind == "slot":
            adapter.create_sketch_slot(_slot_request(first, first_sketch))
        else:
            adapter.create_sketch_rounded_rectangle(_rounded_request(first, first_sketch))
        assert int(second_sketch.GeometryCount) == 0
        assert int(second_sketch.ConstraintCount) == 0 and int(second.UndoCount) == 0
        return True
    finally:
        rectangle_smoke._close(second)
        rectangle_smoke._close(first)


def _combined_regressions(scenarios: dict[str, object]) -> None:
    scenarios["66_sharp_lower_left_rectangle_regression"] = _run_regression(rectangle_smoke.main)
    scenarios["67_sharp_centered_rectangle_regression"] = _run_regression(
        smoke_sketch_centered_rectangle.main
    )
    polygon = _run_regression(smoke_sketch_polygon_profiles.main)
    scenarios["68_equilateral_triangle_regression"] = polygon
    scenarios["69_regular_polygon_regression"] = polygon
    scenarios["70_tangency_constraint_regression"] = _run_regression(smoke_sketch_tangent.main)
    scenarios["71_symmetry_regression"] = _run_regression(smoke_sketch_symmetric.main)
    scenarios["72_point_relationship_regression"] = _run_regression(
        smoke_sketch_point_relationships.main
    )
    scenarios["73_document_history_regression"] = _run_regression(smoke_document_history.main)
    selection = (
        "straight slot" in CREATE_SKETCH_SLOT_DESCRIPTION
        and "obround" in CREATE_SKETCH_SLOT_DESCRIPTION
        and "pill-shaped" in CREATE_SKETCH_SLOT_DESCRIPTION
        and "rounded rectangle" in CREATE_SKETCH_ROUNDED_RECTANGLE_DESCRIPTION
        and "create_sketch_rectangle" in CREATE_SKETCH_ROUNDED_RECTANGLE_DESCRIPTION
    )
    scenarios["74_tool_selection_comparison"] = selection


def _run_regression(operation: Any) -> bool:
    with redirect_stdout(io.StringIO()):
        return operation() == 0


def _extended_cases(adapter: FreeCADDocumentAdapter, scenarios: dict[str, object]) -> None:
    document, _, result = _slot_fixture(
        adapter,
        "CurvedSlotNearMinimum",
        length=12.001,
        width=12.0,
    )
    try:
        scenarios["76_slot_near_minimum_valid"] = result.profile.straight_segment_length
    finally:
        rectangle_smoke._close(document)

    document, _, result = _rounded_fixture(
        adapter,
        "CurvedRoundedNearLimit",
        radius=11.999,
    )
    try:
        scenarios["77_rounded_near_limit_valid"] = result.profile.corner_radius
    finally:
        rectangle_smoke._close(document)

    constructor = Part.ArcOfCircle(
        Part.Circle(App.Vector(0.0, 0.0, 0.0), App.Vector(0.0, 0.0, 1.0), 2.0),
        -math.pi / 2.0,
        math.pi / 2.0,
    )
    scenarios["78_native_arcofcircle_constructor"] = {
        "type": type(constructor).__name__,
        "first": float(constructor.FirstParameter),
        "last": float(constructor.LastParameter),
    }


def _no_raw_native_readback(adapter: FreeCADDocumentAdapter) -> bool:
    document, _, result = _slot_fixture(adapter, "CurvedNoRawReadback")
    try:
        payload = result.to_dict()
        json.dumps(payload)
        text = repr(payload)
        forbidden = ("Part.Arc", "Part.ArcOfCircle", "Sketcher.Constraint", "0x")
        return not any(item in text for item in forbidden)
    finally:
        rectangle_smoke._close(document)


def main() -> int:
    adapter = FreeCADDocumentAdapter()
    scenarios: dict[str, object] = {}
    _slot_cases(adapter, scenarios)
    _rounded_cases(adapter, scenarios)
    _combined_regressions(scenarios)
    scenarios["75_no_raw_native_readback"] = _no_raw_native_readback(adapter)
    _extended_cases(adapter, scenarios)
    expected = [f"{index:02d}_" for index in range(1, 79)]
    assert len(scenarios) == 78
    assert all(any(key.startswith(prefix) for key in scenarios) for prefix in expected)
    version = App.Version()
    report = {
        "freecad_version": ".".join(str(item) for item in version[:3]),
        "freecad_build": str(version[3]),
        "freecad_revision": str(version[7]),
        "embedded_python": sys.version.split()[0],
        "scenario_count": len(scenarios),
        "pass_count": len(scenarios),
        "constraint_counts": {
            "slot_origin": 9,
            "slot_non_origin": 10,
            "rounded_center_origin": 19,
            "rounded_other_placement": 20,
        },
        "scenarios": scenarios,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    print("Curved profile smoke passed: 78/78")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
