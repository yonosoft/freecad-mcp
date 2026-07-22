"""Direct FreeCAD 1.1 smoke campaign for read-only sketch analysis."""

from __future__ import annotations

import hashlib
import json
import math
import sys
import tempfile
from pathlib import Path
from typing import Any, cast

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

import FreeCAD as App  # type: ignore[import-not-found]  # noqa: E402
import FreeCADGui as Gui  # type: ignore[import-not-found]  # noqa: E402
import Part  # type: ignore[import-not-found]  # noqa: E402

from freecad_mcp.freecad.document import FreeCADDocumentAdapter  # noqa: E402
from freecad_mcp.freecad.sketch_inspection import get_sketch  # noqa: E402
from freecad_mcp.models import (  # noqa: E402
    CenterRoundedRectanglePlacementInput,
    LowerLeftRectanglePlacementInput,
    SketchAnalysisRequestInput,
    SketchCenteredRectangleRequestInput,
    SketchCenterPointInput,
    SketchProfileAnalysisRequestInput,
    SketchRectangleRequestInput,
    SketchRoundedRectangleRequestInput,
    SketchSemanticPolygonRequest,
    SketchSlotRequestInput,
)
from freecad_mcp.tool_registry import REGISTERED_TOOL_NAMES  # noqa: E402

_ADAPTER = FreeCADDocumentAdapter()
_SCENARIOS: dict[str, object] = {}


class _HeadlessGuiDocument:
    def __init__(self) -> None:
        self.Modified = True

    def getInEdit(self) -> None:
        return None


class _HeadlessSelection:
    @staticmethod
    def getSelection() -> list[object]:
        return []


_GUI_DOCUMENTS: dict[str, _HeadlessGuiDocument] = {}
if not hasattr(Gui, "getDocument"):
    Gui.getDocument = lambda name: _GUI_DOCUMENTS.setdefault(name, _HeadlessGuiDocument())
if not hasattr(Gui, "Selection"):
    Gui.Selection = _HeadlessSelection()


def _record(name: str, condition: bool, value: object = True) -> None:
    if not condition:
        raise AssertionError(name)
    _SCENARIOS[f"{len(_SCENARIOS) + 1:02d}_{name}"] = value


def _new_sketch(name: str) -> tuple[Any, Any]:
    if name in App.listDocuments():
        App.closeDocument(name)
    document = App.newDocument(name)
    document.UndoMode = 1
    _GUI_DOCUMENTS[name] = _HeadlessGuiDocument()
    sketch = document.addObject("Sketcher::SketchObject", "Sketch")
    return document, sketch


def _line(start: tuple[float, float], end: tuple[float, float]) -> Any:
    return Part.LineSegment(App.Vector(*start, 0), App.Vector(*end, 0))


def _arc(
    center: tuple[float, float], radius: float, start_degrees: float, end_degrees: float
) -> Any:
    return Part.ArcOfCircle(
        Part.Circle(App.Vector(*center, 0), App.Vector(0, 0, 1), radius),
        math.radians(start_degrees),
        math.radians(end_degrees),
    )


def _rectangle(
    left: float = -5.0,
    bottom: float = -5.0,
    right: float = 5.0,
    top: float = 5.0,
) -> list[Any]:
    return [
        _line((left, bottom), (right, bottom)),
        _line((right, bottom), (right, top)),
        _line((right, top), (left, top)),
        _line((left, top), (left, bottom)),
    ]


def _add(sketch: Any, geometry: list[Any], construction: bool = False) -> tuple[int, ...]:
    result = sketch.addGeometry(geometry, construction)
    if isinstance(result, int):
        return (int(result),)
    return tuple(int(item) for item in result)


def _analyze(document_name: str, *, construction: bool = False) -> dict[str, Any]:
    result = _ADAPTER.analyze_sketch(
        SketchAnalysisRequestInput(
            document_name=document_name,
            sketch_name="Sketch",
            include_construction=construction,
        )
    )
    return cast(dict[str, Any], result.to_dict()["analysis"])


def _validate(
    document_name: str,
    indices: tuple[int, ...] | None = None,
    *,
    construction: bool = False,
    external: bool = False,
) -> dict[str, Any]:
    result = _ADAPTER.validate_sketch_profile(
        SketchProfileAnalysisRequestInput(
            document_name=document_name,
            sketch_name="Sketch",
            geometry_indices=indices,
            include_construction=construction,
            include_external=external,
        )
    )
    return cast(dict[str, Any], result.to_dict()["validation"])


def _open(document_name: str, indices: tuple[int, ...] | None = None) -> dict[str, Any]:
    result = _ADAPTER.list_sketch_open_vertices(
        SketchProfileAnalysisRequestInput(
            document_name=document_name,
            sketch_name="Sketch",
            geometry_indices=indices,
        )
    )
    return result.to_dict()


def _codes(result: dict[str, Any]) -> set[str]:
    return {str(item["code"]) for item in result["findings"]}


def _state(document_name: str) -> dict[str, object]:
    document = App.getDocument(document_name)
    sketch = document.getObject("Sketch")
    gui_document = Gui.getDocument(document_name)
    inspected = get_sketch(document_name, "Sketch").to_dict()
    in_edit = None if gui_document is None else gui_document.getInEdit()
    return {
        "inspection": inspected,
        "file_name": str(document.FileName),
        "label": str(document.Label),
        "undo_count": int(document.UndoCount),
        "redo_count": int(document.RedoCount),
        "transaction_active": bool(document.HasPendingTransaction),
        "modified": None if gui_document is None else bool(gui_document.Modified),
        "active_document": None if App.activeDocument() is None else str(App.activeDocument().Name),
        "selection": tuple(str(item.Name) for item in Gui.Selection.getSelection()),
        "in_edit": None if in_edit is None else str(in_edit.Name),
        "geometry_count": int(sketch.GeometryCount),
        "constraint_count": int(sketch.ConstraintCount),
    }


def _assert_preserved(document_name: str, operation: Any) -> object:
    before = _state(document_name)
    result = operation()
    after = _state(document_name)
    if after != before:
        raise AssertionError({"document": document_name, "before": before, "after": after})
    return result


def _basic_topology_cases() -> None:
    document, sketch = _new_sketch("M17Empty")
    result = cast(dict[str, Any], _assert_preserved("M17Empty", lambda: _analyze("M17Empty")))
    _record("empty_sketch_analysis", result["topology"]["component_count"] == 0)
    App.closeDocument(str(document.Name))

    document, sketch = _new_sketch("M17Line")
    _add(sketch, [_line((0, 0), (10, 0))])
    opened = cast(dict[str, Any], _assert_preserved("M17Line", lambda: _open("M17Line")))
    _record("single_line_two_open_vertices", opened["open_vertex_count"] == 2)
    _record(
        "open_vertex_controlled_references",
        all(item["members"][0]["position"] in {"start", "end"} for item in opened["open_vertices"]),
    )
    App.closeDocument(str(document.Name))

    document, sketch = _new_sketch("M17Polyline")
    _add(
        sketch,
        [_line((0, 0), (10, 0)), _line((10, 0), (10, 5)), _line((10, 5), (0, 5))],
    )
    result = _validate("M17Polyline")
    _record("open_polyline", result["classification"] == "open_profile")
    _record("open_polyline_same_component", result["component_count"] == 1)
    App.closeDocument(str(document.Name))

    document, sketch = _new_sketch("M17Rectangle")
    _add(sketch, _rectangle())
    result = _validate("M17Rectangle")
    _record("closed_rectangle", result["classification"] == "single_closed_profile")
    _record("rectangle_exact_area", abs(result["profiles"][0]["signed_area"] - 100.0) < 1e-9)
    App.closeDocument(str(document.Name))

    document, sketch = _new_sketch("M17Circle")
    _add(sketch, [Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), 4)])
    result = _validate("M17Circle")
    _record("full_circle_profile", result["classification"] == "single_closed_profile")
    _record("full_circle_zero_open_vertices", result["open_vertices"] == [])
    App.closeDocument(str(document.Name))


def _semantic_profile_cases() -> None:
    document, _sketch = _new_sketch("M17SemanticRectangle")
    _ADAPTER.create_sketch_rectangle(
        SketchRectangleRequestInput(
            document_name="M17SemanticRectangle",
            sketch_name="Sketch",
            width=20.0,
            height=10.0,
            placement=LowerLeftRectanglePlacementInput(type="lower_left", x=-10.0, y=-5.0),
        )
    )
    _record("semantic_rectangle_regression", _validate("M17SemanticRectangle")["valid"] is True)
    _record(
        "semantic_rectangle_clean_analysis",
        _analyze("M17SemanticRectangle")["topology"]["probable_profile_count"] == 1,
    )
    App.closeDocument(str(document.Name))

    document, _sketch = _new_sketch("M17CenteredRectangle")
    _ADAPTER.create_sketch_centered_rectangle(
        SketchCenteredRectangleRequestInput(
            document_name="M17CenteredRectangle",
            sketch_name="Sketch",
            width=20.0,
            height=10.0,
            center=SketchCenterPointInput(x=0.0, y=0.0),
        )
    )
    _record("centered_rectangle_regression", _validate("M17CenteredRectangle")["valid"] is True)
    App.closeDocument(str(document.Name))

    for name, sides, profile_type in (
        ("M17Triangle", 3, "equilateral_triangle"),
        ("M17Hexagon", 6, "regular_polygon"),
    ):
        document, _sketch = _new_sketch(name)
        _ADAPTER.create_sketch_polygon(
            SketchSemanticPolygonRequest(
                document_name=name,
                sketch_name="Sketch",
                side_count=sides,
                circumradius=10.0,
                center=SketchCenterPointInput(x=0.0, y=0.0),
                first_vertex_angle_degrees=90.0 if sides == 3 else 0.0,
                profile_type=cast(Any, profile_type),
            )
        )
        _record(f"semantic_{profile_type}_regression", _validate(name)["valid"] is True)
        App.closeDocument(str(document.Name))

    document, _sketch = _new_sketch("M17Slot")
    _ADAPTER.create_sketch_slot(
        SketchSlotRequestInput(
            document_name="M17Slot",
            sketch_name="Sketch",
            overall_length=30.0,
            overall_width=10.0,
            center=SketchCenterPointInput(x=0.0, y=0.0),
        )
    )
    slot = _validate("M17Slot")
    _record("semantic_slot_regression", slot["valid"] is True)
    _record("slot_mixed_line_arc_area", slot["profiles"][0]["signed_area"] is not None)
    App.closeDocument(str(document.Name))

    document, _sketch = _new_sketch("M17RoundedRectangle")
    _ADAPTER.create_sketch_rounded_rectangle(
        SketchRoundedRectangleRequestInput(
            document_name="M17RoundedRectangle",
            sketch_name="Sketch",
            width=30.0,
            height=20.0,
            corner_radius=4.0,
            placement=CenterRoundedRectanglePlacementInput(type="center", x=0.0, y=0.0),
        )
    )
    rounded = _validate("M17RoundedRectangle")
    _record("semantic_rounded_rectangle_regression", rounded["valid"] is True)
    _record(
        "rounded_rectangle_eight_elements", len(rounded["profiles"][0]["geometry_indices"]) == 8
    )
    App.closeDocument(str(document.Name))


def _multiple_selection_and_construction_cases() -> None:
    document, sketch = _new_sketch("M17Multiple")
    _add(sketch, _rectangle(-15, -5, -5, 5) + _rectangle(5, -5, 15, 5))
    result = _validate("M17Multiple")
    _record("two_disjoint_profiles", result["classification"] == "multiple_disjoint_profiles")
    _record("two_disjoint_profile_count", result["profile_count"] == 2)
    App.closeDocument(str(document.Name))

    document, sketch = _new_sketch("M17Nested")
    _add(sketch, _rectangle(-10, -8, 10, 8) + _rectangle(-3, -2, 3, 2))
    result = _validate("M17Nested")
    _record("nested_profiles", result["classification"] == "nested_profiles")
    _record(
        "nested_containment_map",
        result["profiles"][0]["contains_profile_numbers"] == [1]
        and result["profiles"][1]["contained_by_profile_number"] == 0,
    )
    App.closeDocument(str(document.Name))

    document, sketch = _new_sketch("M17Construction")
    _add(sketch, _rectangle())
    _add(sketch, [Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), 2)], True)
    excluded = _validate("M17Construction")
    included = _validate("M17Construction", construction=True)
    _record(
        "construction_excluded_by_default", excluded["classification"] == "single_closed_profile"
    )
    _record("construction_exclusion_finding", "construction_geometry_excluded" in _codes(excluded))
    _record("construction_explicitly_included", included["classification"] == "nested_profiles")
    App.closeDocument(str(document.Name))

    document, sketch = _new_sketch("M17Selection")
    _add(sketch, [*_rectangle(), _line((20, 0), (25, 0))])
    whole = _validate("M17Selection")
    selected = _validate("M17Selection", (0, 1, 2, 3))
    _record("whole_invalid_selected_valid", whole["valid"] is False and selected["valid"] is True)
    _record("selected_subset_profile", selected["classification"] == "single_closed_profile")
    _record(
        "selected_subset_open_vertices",
        _open("M17Selection", (0, 1, 2, 3))["open_vertex_count"] == 0,
    )
    App.closeDocument(str(document.Name))


def _defect_and_intersection_cases() -> None:
    cases: tuple[tuple[str, list[Any], str, str], ...] = (
        (
            "M17Branch",
            [_line((-2, 0), (2, 0)), _line((0, 0), (0, 2))],
            "branched_profile",
            "branched_topology",
        ),
        (
            "M17BowTie",
            [
                _line((-2, -2), (2, 2)),
                _line((2, 2), (-2, 2)),
                _line((-2, 2), (2, -2)),
                _line((2, -2), (-2, -2)),
            ],
            "self_intersecting_profile",
            "self_intersection",
        ),
        (
            "M17Duplicate",
            [_line((0, 0), (2, 0)), _line((0, 0), (2, 0))],
            "ambiguous_profile",
            "duplicate_geometry",
        ),
        (
            "M17ReverseDuplicate",
            [_line((0, 0), (2, 0)), _line((2, 0), (0, 0))],
            "ambiguous_profile",
            "duplicate_geometry",
        ),
    )
    for name, geometry, classification, code in cases:
        document, sketch = _new_sketch(name)
        _add(sketch, geometry)
        result = _validate(name)
        _record(name.removeprefix("M17").lower(), result["classification"] == classification)
        _record(f"{name.removeprefix('M17').lower()}_finding", code in _codes(result))
        App.closeDocument(str(document.Name))

    document, sketch = _new_sketch("M17Zero")
    _add(sketch, [_line((1, 1), (1.0 + 5.0e-8, 1))])
    result = _validate("M17Zero")
    _record("zero", result["valid"] is False)
    _record("zero_finding", "zero_length_geometry" in _codes(result))
    App.closeDocument(str(document.Name))

    document, sketch = _new_sketch("M17GapAbove")
    _add(
        sketch,
        [
            _line((0, 0), (10, 0)),
            _line((10, 0), (10, 5)),
            _line((10, 5), (0, 5)),
            _line((0, 5), (2e-7, 0)),
        ],
    )
    opened = _open("M17GapAbove")
    _record("gap_above_tolerance", opened["open_vertex_count"] == 2)
    _record("near_gap_warning", "suspected_near_open_gap" in _codes(opened))
    App.closeDocument(str(document.Name))

    document, sketch = _new_sketch("M17GapBelow")
    _add(
        sketch,
        [
            _line((0, 0), (10, 0)),
            _line((10, 0), (10, 5)),
            _line((10, 5), (0, 5)),
            _line((0, 5), (5e-8, 0)),
        ],
    )
    _record("gap_below_tolerance_clusters", _validate("M17GapBelow")["valid"] is True)
    App.closeDocument(str(document.Name))

    document, sketch = _new_sketch("M17LineArc")
    _add(sketch, [_line((-2, 0), (2, 0)), _arc((0, 0), 2, 0, 180)])
    _record("line_arc_closed_profile", _validate("M17LineArc")["valid"] is True)
    App.closeDocument(str(document.Name))

    document, sketch = _new_sketch("M17ArcCross")
    _add(sketch, [_arc((0, 0), 2, 0, 270), _arc((2, 0), 2, 90, 360)])
    _record("arc_arc_intersection", "self_intersection" in _codes(_validate("M17ArcCross")))
    App.closeDocument(str(document.Name))


def _ownership_external_and_preservation_cases() -> None:
    document = App.newDocument("M17Body")
    _GUI_DOCUMENTS["M17Body"] = _HeadlessGuiDocument()
    body = document.addObject("PartDesign::Body", "Body")
    sketch = document.addObject("Sketcher::SketchObject", "Sketch")
    body.addObject(sketch)
    _add(sketch, _rectangle())
    before = _state("M17Body")
    _validate("M17Body")
    _record("body_owned_sketch_preserved", _state("M17Body") == before)
    App.closeDocument(str(document.Name))

    document = App.newDocument("M17Attached")
    _GUI_DOCUMENTS["M17Attached"] = _HeadlessGuiDocument()
    body = document.addObject("PartDesign::Body", "Body")
    sketch = document.addObject("Sketcher::SketchObject", "Sketch")
    body.addObject(sketch)
    plane = next(item for item in body.Origin.OriginFeatures if str(item.Role) == "XY_Plane")
    sketch.AttachmentSupport = (plane, [""])
    sketch.MapMode = "FlatFace"
    _add(sketch, _rectangle())
    before = _state("M17Attached")
    _validate("M17Attached")
    after = _state("M17Attached")
    after_inspection = cast(dict[str, Any], after["inspection"])
    _record(
        "xy_attachment_preserved",
        before == after and after_inspection["attachment"] is not None,
    )
    App.closeDocument(str(document.Name))

    first, first_sketch = _new_sketch("M17NamedFirst")
    second, second_sketch = _new_sketch("M17NamedSecond")
    _add(first_sketch, _rectangle())
    _add(second_sketch, [_line((0, 0), (1, 0))])
    App.setActiveDocument("M17NamedSecond")
    second_before = _state("M17NamedSecond")
    selected = _validate("M17NamedFirst")
    _record("named_non_active_document", selected["valid"] is True)
    _record("cross_document_isolation", _state("M17NamedSecond") == second_before)
    _record(
        "active_document_unchanged",
        App.activeDocument() is not None and str(App.activeDocument().Name) == "M17NamedSecond",
    )
    App.closeDocument(str(first.Name))
    App.closeDocument(str(second.Name))

    document, sketch = _new_sketch("M17External")
    source = document.addObject("PartDesign::Feature", "Source")
    source.Shape = Part.makeLine(App.Vector(0, 0, 0), App.Vector(10, 0, 0))
    sketch.addExternal("Source", "Edge1")
    excluded = _validate("M17External")
    included = _validate("M17External", external=True)
    _record("external_excluded_by_default", "external_geometry_excluded" in _codes(excluded))
    _record("external_explicit_inclusion", included["classification"] == "open_profile")
    _record(
        "external_controlled_index",
        included["open_vertices"][0]["members"][0]["geometry_index"] == -1,
    )
    App.closeDocument(str(document.Name))

    document, sketch = _new_sketch("M17Unsaved")
    _add(sketch, _rectangle())
    before = _state("M17Unsaved")
    _analyze("M17Unsaved")
    _validate("M17Unsaved")
    _open("M17Unsaved")
    after = _state("M17Unsaved")
    _record("unsaved_state_preservation", before == after and after["file_name"] == "")
    _record(
        "selection_and_edit_mode_preservation",
        before["selection"] == after["selection"] and before["in_edit"] == after["in_edit"],
    )
    _record("all_three_tools_zero_mutation", before == after)
    App.closeDocument(str(document.Name))

    with tempfile.TemporaryDirectory(dir=REPOSITORY_ROOT) as temporary:
        document, sketch = _new_sketch("M17Saved")
        _add(sketch, _rectangle())
        path = Path(temporary) / "analysis.FCStd"
        document.recompute()
        assert document.saveAs(str(path)) is not False
        before_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        before = _state("M17Saved")
        _validate("M17Saved")
        after_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        _record("saved_file_bytes_preserved", before_hash == after_hash)
        _record("saved_document_state_preserved", before == _state("M17Saved"))
        App.closeDocument(str(document.Name))

    document, sketch = _new_sketch("M17History")
    document.UndoMode = 1
    document.openTransaction("Fixture geometry")
    _add(sketch, _rectangle())
    document.commitTransaction()
    before = _state("M17History")
    _analyze("M17History")
    after = _state("M17History")
    _record(
        "history_transaction_state_unchanged",
        before["transaction_active"] == after["transaction_active"],
    )
    _record("undo_count_unchanged", before["undo_count"] == after["undo_count"])
    _record("redo_count_unchanged", before["redo_count"] == after["redo_count"])
    _record(
        "solver_diagnostics_unchanged",
        before["inspection"]["solver"] == after["inspection"]["solver"],  # type: ignore[index]
    )
    App.closeDocument(str(document.Name))


def main() -> None:
    _basic_topology_cases()
    _semantic_profile_cases()
    _multiple_selection_and_construction_cases()
    _defect_and_intersection_cases()
    _ownership_external_and_preservation_cases()

    _record(
        "exact_39_tool_inventory",
        len(REGISTERED_TOOL_NAMES) == 39
        and REGISTERED_TOOL_NAMES[24:28]
        == (
            "add_external_geometry",
            "list_external_geometry",
            "remove_external_geometry",
            "get_sketch_dependencies",
        )
        and REGISTERED_TOOL_NAMES[28:31]
        == (
            "remove_sketch_constraints",
            "remove_sketch_geometry",
            "set_sketch_geometry_construction",
        )
        and REGISTERED_TOOL_NAMES[31:34]
        == (
            "update_sketch_geometry",
            "replace_sketch_constraint",
            "update_sketch_constraint_value",
        )
        and REGISTERED_TOOL_NAMES[34] == "add_sketch_reference_constraints"
        and REGISTERED_TOOL_NAMES[35:]
        == (
            "set_sketch_constraint_name",
            "set_sketch_constraint_expression",
            "clear_sketch_constraint_expression",
            "list_sketch_constraint_expressions",
        ),
    )
    _record(
        "first_24_tool_regression",
        REGISTERED_TOOL_NAMES[:24]
        == (
            "create_document",
            "list_documents",
            "get_document",
            "save_document",
            "list_objects",
            "get_object",
            "recompute_document",
            "create_body",
            "create_sketch",
            "get_sketch",
            "add_sketch_geometry",
            "add_sketch_constraints",
            "get_document_history",
            "undo_document",
            "redo_document",
            "create_sketch_rectangle",
            "create_sketch_centered_rectangle",
            "create_sketch_equilateral_triangle",
            "create_sketch_regular_polygon",
            "create_sketch_slot",
            "create_sketch_rounded_rectangle",
            "analyze_sketch",
            "validate_sketch_profile",
            "list_sketch_open_vertices",
        ),
    )
    _record("no_raw_native_readback", "Part" not in json.dumps(_SCENARIOS))

    version = App.Version()
    output = {
        "freecad_version": ".".join(str(item) for item in version[:3]),
        "freecad_build": str(version[3]) if len(version) > 3 else "unknown",
        "freecad_revision": str(version[7]) if len(version) > 7 else "unknown",
        "embedded_python": sys.version.split()[0],
        "scenario_count": len(_SCENARIOS),
        "pass_count": len(_SCENARIOS),
        "scenarios": _SCENARIOS,
    }
    print(json.dumps(output, indent=2, sort_keys=True))
    print(f"Sketch analysis smoke passed: {len(_SCENARIOS)}/{len(_SCENARIOS)}")


if __name__ == "__main__":
    try:
        main()
    finally:
        for name in tuple(App.listDocuments()):
            if name.startswith("M17"):
                App.closeDocument(name)
