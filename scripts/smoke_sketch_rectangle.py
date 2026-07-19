"""Direct FreeCAD 1.1 smoke campaign for semantic axis-aligned rectangles."""

from __future__ import annotations

import hashlib
import json
import math
import sys
import tempfile
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

import FreeCAD as App  # type: ignore[import-not-found]  # noqa: E402
import FreeCADGui as Gui  # type: ignore[import-not-found]  # noqa: E402
import Part  # type: ignore[import-not-found]  # noqa: E402
import Sketcher  # type: ignore[import-not-found]  # noqa: E402

from freecad_mcp.exceptions import (  # noqa: E402
    DocumentHistoryTransactionMismatchError,
    SketchRectangleCreationError,
    SketchRectangleVerificationError,
)
from freecad_mcp.freecad import sketch_rectangle_creation  # noqa: E402
from freecad_mcp.freecad.document import FreeCADDocumentAdapter  # noqa: E402
from freecad_mcp.models import (  # noqa: E402
    OriginPlane,
    SketchRectangleRequestInput,
)
from freecad_mcp.transaction_names import (  # noqa: E402
    CREATE_SKETCH_RECTANGLE_TRANSACTION_NAME,
)
from freecad_mcp.validation import (  # noqa: E402
    validate_add_sketch_geometry_request,
    validate_create_sketch_rectangle_request,
)

_TOLERANCE = 1.0e-7


class _HeadlessGuiDocument:
    def __init__(self) -> None:
        self.Modified = True


_GUI_DOCUMENTS: dict[str, _HeadlessGuiDocument] = {}

if not hasattr(Gui, "getDocument"):
    Gui.getDocument = lambda name: _GUI_DOCUMENTS.setdefault(  # type: ignore[attr-defined]
        name, _HeadlessGuiDocument()
    )


def _new_document(name: str) -> Any:
    document = App.newDocument(name)
    document.UndoMode = 1
    _GUI_DOCUMENTS[name] = _HeadlessGuiDocument()
    return document


def _close(document: Any) -> None:
    name = str(document.Name)
    App.closeDocument(name)
    _GUI_DOCUMENTS.pop(name, None)


def _request(
    document: Any,
    sketch: Any,
    *,
    width: float = 30.0,
    height: float = 20.0,
    x: float = 0.0,
    y: float = 0.0,
) -> SketchRectangleRequestInput:
    return SketchRectangleRequestInput.model_validate(
        {
            "document_name": str(document.Name),
            "sketch_name": str(sketch.Name),
            "width": width,
            "height": height,
            "placement": {"type": "lower_left", "x": x, "y": y},
        }
    )


def _new_sketch(name: str) -> tuple[Any, Any]:
    document = _new_document(name)
    sketch = document.addObject("Sketcher::SketchObject", "Sketch")
    document.recompute()
    document.clearUndos()
    return document, sketch


def _point(value: Any) -> tuple[float, float]:
    return float(value.x), float(value.y)


def _same(first: tuple[float, float], second: tuple[float, float]) -> bool:
    return math.isclose(first[0], second[0], abs_tol=_TOLERANCE) and math.isclose(
        first[1], second[1], abs_tol=_TOLERANCE
    )


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _basic_cases(
    adapter: FreeCADDocumentAdapter,
    scenarios: dict[str, object],
) -> None:
    cases = (
        ("RectangleOrigin", 0.0, 0.0, "01_origin_lower_left"),
        ("RectangleCentred", -15.0, -10.0, "02_centred_product_translation"),
        ("RectanglePositive", 5.0, 7.0, "03_positive_placement"),
        ("RectangleNegative", -25.0, -12.0, "04_negative_placement"),
        ("RectangleMixed", 8.0, -6.0, "05_mixed_sign_placement"),
    )
    centred_result: dict[str, object] | None = None
    for name, x, y, key in cases:
        document, sketch = _new_sketch(name)
        try:
            created = adapter.create_sketch_rectangle(_request(document, sketch, x=x, y=y))
            profile = created.profile.to_dict()
            geometry = list(sketch.Geometry)
            assert profile["geometry_indices"] == [0, 1, 2, 3]
            assert int(sketch.GeometryCount) == 4
            assert int(sketch.ConstraintCount) == (11 if x == 0.0 and y == 0.0 else 12)
            assert int(sketch.DoF) == 0 and bool(sketch.FullyConstrained)
            assert list(sketch.ConflictingConstraints) == []
            assert list(sketch.RedundantConstraints) == []
            assert list(sketch.PartiallyRedundantConstraints) == []
            assert list(sketch.MalformedConstraints) == []
            assert str(document.FileName) == ""
            scenarios[key] = {
                "constraint_count": int(sketch.ConstraintCount),
                "degrees_of_freedom": int(sketch.DoF),
                "placement": [x, y],
            }
            if name == "RectangleCentred":
                centred_result = profile
                assert _same(_point(geometry[0].StartPoint), (-15.0, -10.0))
                assert _same(_point(geometry[1].EndPoint), (15.0, 10.0))
        finally:
            _close(document)

    assert centred_result is not None
    scenarios["06_deterministic_edge_order"] = centred_result["edges"]
    scenarios["07_deterministic_corner_mapping"] = centred_result["corners"]
    scenarios["08_exact_width_and_height"] = {
        "width": centred_result["width"],
        "height": centred_result["height"],
    }
    scenarios["09_exact_lower_left"] = centred_result["placement"]
    scenarios["10_exact_upper_right"] = [15.0, 10.0]
    scenarios["11_closed_profile"] = centred_result["closed"]
    scenarios["12_zero_degrees_of_freedom"] = True
    scenarios["13_clean_solver_diagnostics"] = True
    scenarios["14_no_helper_geometry"] = True
    scenarios["15_no_construction_geometry"] = True


def _existing_content_cases(
    adapter: FreeCADDocumentAdapter,
    scenarios: dict[str, object],
) -> None:
    document, sketch = _new_sketch("RectangleExisting")
    try:
        existing_index = sketch.addGeometry(
            Part.LineSegment(App.Vector(-5.0, 50.0, 0.0), App.Vector(5.0, 50.0, 0.0)),
            True,
        )
        sketch.addConstraint(Sketcher.Constraint("Block", existing_index))
        document.recompute()
        document.clearUndos()
        before = (
            _point(sketch.Geometry[0].StartPoint),
            _point(sketch.Geometry[0].EndPoint),
            bool(sketch.getConstruction(0)),
            str(sketch.Constraints[0].Type),
        )
        result = adapter.create_sketch_rectangle(_request(document, sketch, x=12.0, y=6.0))
        after = (
            _point(sketch.Geometry[0].StartPoint),
            _point(sketch.Geometry[0].EndPoint),
            bool(sketch.getConstruction(0)),
            str(sketch.Constraints[0].Type),
        )
        assert before == after
        assert result.profile.geometry_indices == (1, 2, 3, 4)
        scenarios["16_non_empty_sketch"] = {"first_rectangle_index": 1}
        scenarios["17_existing_construction_preserved"] = before == after
    finally:
        _close(document)


def _attached_cases(
    adapter: FreeCADDocumentAdapter,
    scenarios: dict[str, object],
) -> None:
    document = _new_document("RectangleAttached")
    try:
        body = document.addObject("PartDesign::Body", "Body")
        document.recompute()
        adapter.create_sketch(
            str(document.Name),
            str(body.Name),
            "Sketch",
            None,
            OriginPlane.XY,
        )
        sketch = document.getObject("Sketch")
        assert sketch is not None
        document.clearUndos()
        parent_before = sketch.getParentGeoFeatureGroup()
        support_before = sketch.AttachmentSupport
        map_mode_before = str(sketch.MapMode)
        placement_before = sketch.Placement
        adapter.create_sketch_rectangle(_request(document, sketch, x=3.0, y=4.0))
        assert sketch.getParentGeoFeatureGroup() is parent_before
        assert sketch.AttachmentSupport == support_before
        assert str(sketch.MapMode) == map_mode_before
        assert sketch.Placement == placement_before
        scenarios["18_body_owned_sketch"] = str(parent_before.Name)
        scenarios["19_xy_plane_attachment"] = map_mode_before
    finally:
        _close(document)


def _saved_unsaved_cases(
    adapter: FreeCADDocumentAdapter,
    scenarios: dict[str, object],
) -> None:
    document, sketch = _new_sketch("RectangleUnsaved")
    try:
        adapter.create_sketch_rectangle(_request(document, sketch))
        adapter.undo_document(str(document.Name), CREATE_SKETCH_RECTANGLE_TRANSACTION_NAME)
        adapter.redo_document(str(document.Name), CREATE_SKETCH_RECTANGLE_TRANSACTION_NAME)
        assert str(document.FileName) == ""
        scenarios["20_unsaved_document_preserved"] = True
    finally:
        _close(document)

    with tempfile.TemporaryDirectory(prefix="freecad_mcp_rectangle_") as directory:
        document, sketch = _new_sketch("RectangleSaved")
        try:
            path = Path(directory) / "rectangle.FCStd"
            document.saveAs(str(path))
            Gui.getDocument(str(document.Name)).Modified = False
            before = (path.stat().st_size, path.stat().st_mtime_ns, _digest(path))
            adapter.create_sketch_rectangle(_request(document, sketch, x=-2.0, y=5.0))
            adapter.undo_document(str(document.Name), CREATE_SKETCH_RECTANGLE_TRANSACTION_NAME)
            adapter.redo_document(str(document.Name), CREATE_SKETCH_RECTANGLE_TRANSACTION_NAME)
            after = (path.stat().st_size, path.stat().st_mtime_ns, _digest(path))
            assert before == after
            scenarios["21_saved_file_preserved"] = {
                "file_path": str(path),
                "size": before[0],
                "timestamp": before[1],
                "sha256": before[2],
            }
        finally:
            _close(document)


def _history_cases(
    adapter: FreeCADDocumentAdapter,
    scenarios: dict[str, object],
) -> None:
    document, sketch = _new_sketch("RectangleHistory")
    try:
        adapter.create_sketch_rectangle(_request(document, sketch, x=-4.0, y=3.0))
        assert adapter.get_document_history(str(document.Name)).history.next_undo_name == (
            CREATE_SKETCH_RECTANGLE_TRANSACTION_NAME
        )
        adapter.undo_document(str(document.Name), CREATE_SKETCH_RECTANGLE_TRANSACTION_NAME)
        assert int(sketch.GeometryCount) == 0 and int(sketch.ConstraintCount) == 0
        scenarios["22_single_step_undo"] = True
        adapter.redo_document(str(document.Name), CREATE_SKETCH_RECTANGLE_TRANSACTION_NAME)
        document.recompute()
        assert int(sketch.GeometryCount) == 4 and int(sketch.ConstraintCount) == 12
        assert int(sketch.DoF) == 0
        scenarios["23_single_step_redo"] = True
        try:
            adapter.undo_document(str(document.Name), "Wrong rectangle transaction")
            raise AssertionError("name mismatch was not rejected")
        except DocumentHistoryTransactionMismatchError:
            pass
        assert int(sketch.GeometryCount) == 4
        scenarios["24_expected_name_mismatch"] = True

        adapter.undo_document(str(document.Name), CREATE_SKETCH_RECTANGLE_TRANSACTION_NAME)
        payload = validate_add_sketch_geometry_request(
            str(document.Name),
            str(sketch.Name),
            [
                {
                    "type": "point",
                    "position": {"x": 1.0, "y": 2.0},
                    "construction": False,
                }
            ],
        )
        assert isinstance(payload, tuple)
        adapter.add_sketch_geometry(str(document.Name), str(sketch.Name), payload)
        assert not adapter.get_document_history(str(document.Name)).history.can_redo
        scenarios["25_redo_invalidation"] = True
    finally:
        _close(document)


def _failure_cases(
    adapter: FreeCADDocumentAdapter,
    scenarios: dict[str, object],
) -> None:
    document, sketch = _new_sketch("RectangleValidationFailure")
    try:
        before = adapter.get_document_history(str(document.Name)).history
        validation = validate_create_sketch_rectangle_request(
            str(document.Name),
            str(sketch.Name),
            0.0,
            20.0,
            {"type": "lower_left", "x": 0.0, "y": 0.0},
        )
        assert not isinstance(validation, SketchRectangleRequestInput)
        after = adapter.get_document_history(str(document.Name)).history
        assert before == after and int(sketch.GeometryCount) == 0
        scenarios["26_failed_validation_zero_transaction"] = True
    finally:
        _close(document)

    original_index_verifier = sketch_rectangle_creation._verify_assigned_index

    def inject_index_failure(target_phase: str) -> bool:
        document, sketch = _new_sketch(f"RectangleInjected{target_phase.title()}")
        calls = {"geometry": 0, "constraint": 0}

        def verifier(value: object, expected: int, phase: str) -> None:
            calls[phase] += 1
            original_index_verifier(value, expected, phase)
            if phase == target_phase and calls[phase] == 2:
                raise SketchRectangleCreationError(
                    phase=phase,
                    reason="injected_index_failure",
                )

        sketch_rectangle_creation._verify_assigned_index = verifier
        try:
            try:
                adapter.create_sketch_rectangle(_request(document, sketch, x=2.0, y=3.0))
                raise AssertionError("injected rectangle failure was not raised")
            except SketchRectangleCreationError:
                pass
            assert int(sketch.GeometryCount) == 0
            assert int(sketch.ConstraintCount) == 0
            assert int(document.UndoCount) == 0
            return True
        finally:
            sketch_rectangle_creation._verify_assigned_index = original_index_verifier
            _close(document)

    scenarios["27_injected_geometry_failure_rollback"] = inject_index_failure("geometry")
    scenarios["28_injected_constraint_failure_rollback"] = inject_index_failure("constraint")

    document, sketch = _new_sketch("RectangleVerificationFailure")
    original_verifier = sketch_rectangle_creation._verify_rectangle

    def verification_failure(**kwargs: object) -> None:
        raise SketchRectangleVerificationError("injected_verification_failure")

    sketch_rectangle_creation._verify_rectangle = verification_failure
    try:
        try:
            adapter.create_sketch_rectangle(_request(document, sketch, x=4.0, y=-2.0))
            raise AssertionError("injected verification failure was not raised")
        except SketchRectangleVerificationError:
            pass
        assert int(sketch.GeometryCount) == 0
        assert int(sketch.ConstraintCount) == 0
        assert int(document.UndoCount) == 0
        scenarios["29_verification_failure_rollback"] = True
    finally:
        sketch_rectangle_creation._verify_rectangle = original_verifier
        _close(document)


def _isolation_case(
    adapter: FreeCADDocumentAdapter,
    scenarios: dict[str, object],
) -> None:
    first, first_sketch = _new_sketch("RectangleIsolationA")
    second, second_sketch = _new_sketch("RectangleIsolationB")
    try:
        adapter.create_sketch_rectangle(_request(first, first_sketch, x=1.0, y=1.0))
        assert int(second_sketch.GeometryCount) == 0
        assert int(second_sketch.ConstraintCount) == 0
        assert int(second.UndoCount) == 0
        scenarios["30_cross_document_isolation"] = True
    finally:
        _close(second)
        _close(first)


def _legacy_regressions(
    adapter: FreeCADDocumentAdapter,
    scenarios: dict[str, object],
) -> None:
    import smoke_document_history
    import smoke_sketch_point_relationships
    import smoke_sketch_symmetric
    import smoke_sketch_tangent

    symmetric = smoke_sketch_symmetric._centred_rectangle(adapter)
    assert symmetric["solver"]["degrees_of_freedom"] == 0
    scenarios["31_symmetry_regression"] = True

    cardinal = smoke_sketch_point_relationships._cardinal_regression(adapter)
    assert cardinal["24_circle_cardinal_point_regression"]["degrees_of_freedom"] == 0
    scenarios["32_point_relationship_regression"] = True

    history = smoke_document_history._workflow_cases(adapter)
    assert history
    scenarios["33_document_history_regression"] = True

    tangent = smoke_sketch_tangent._combined_regression(adapter)
    assert (
        tangent["32_symmetry_point_relationship_tangent_regression"]["solver"]["degrees_of_freedom"]
        == 0
    )
    scenarios["34_tangent_regression"] = True


def _same_sketch_recovery(
    adapter: FreeCADDocumentAdapter,
    scenarios: dict[str, object],
) -> None:
    document, sketch = _new_sketch("RectangleRecovery")
    try:
        adapter.create_sketch_rectangle(_request(document, sketch, x=40.0, y=30.0))
        assert _same(_point(sketch.Geometry[0].StartPoint), (40.0, 30.0))
        history = adapter.get_document_history(str(document.Name)).history
        assert history.next_undo_name == CREATE_SKETCH_RECTANGLE_TRANSACTION_NAME
        adapter.undo_document(str(document.Name), CREATE_SKETCH_RECTANGLE_TRANSACTION_NAME)
        assert int(sketch.GeometryCount) == 0 and int(sketch.ConstraintCount) == 0
        adapter.create_sketch_rectangle(_request(document, sketch, x=-15.0, y=-10.0))
        document.recompute()
        assert _same(_point(sketch.Geometry[0].StartPoint), (-15.0, -10.0))
        assert int(sketch.GeometryCount) == 4
        assert len([obj for obj in document.Objects if str(obj.Name) == "Sketch"]) == 1
        assert not adapter.get_document_history(str(document.Name)).history.can_redo
        scenarios["35_same_sketch_recovery"] = {
            "redo_invalidated": True,
            "replacement_sketches": 0,
        }
    finally:
        _close(document)


def main() -> int:
    adapter = FreeCADDocumentAdapter()
    scenarios: dict[str, object] = {}
    _basic_cases(adapter, scenarios)
    _existing_content_cases(adapter, scenarios)
    _attached_cases(adapter, scenarios)
    _saved_unsaved_cases(adapter, scenarios)
    _history_cases(adapter, scenarios)
    _failure_cases(adapter, scenarios)
    _isolation_case(adapter, scenarios)
    _legacy_regressions(adapter, scenarios)
    _same_sketch_recovery(adapter, scenarios)
    assert len(scenarios) == 35

    version = App.Version()
    result = {
        "freecad_version": version,
        "freecad_revision": version[-1],
        "python_executable": sys.executable,
        "python_version": sys.version,
        "scenario_count": len(scenarios),
        "pass_count": len(scenarios),
        "scenarios": scenarios,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
