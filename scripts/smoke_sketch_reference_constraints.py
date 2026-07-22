"""Direct FreeCAD 1.1.1 smoke campaign for Milestone 21 reference constraints."""

from __future__ import annotations

import hashlib
import json
import math
import os
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any, ClassVar

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
SOURCE_ROOT = REPOSITORY_ROOT / "src"
while str(SOURCE_ROOT) in sys.path:
    sys.path.remove(str(SOURCE_ROOT))
sys.path.insert(0, str(SOURCE_ROOT))

import FreeCAD as App  # type: ignore[import-not-found]  # noqa: E402
import FreeCADGui as Gui  # type: ignore[import-not-found]  # noqa: E402
import Part  # type: ignore[import-not-found]  # noqa: E402
import Sketcher  # type: ignore[import-not-found]  # noqa: E402
from pydantic import TypeAdapter  # noqa: E402

# FreeCAD can preload an installed workbench package. Always exercise this checkout.
while str(SOURCE_ROOT) in sys.path:
    sys.path.remove(str(SOURCE_ROOT))
sys.path.insert(0, str(SOURCE_ROOT))
for _module_name in tuple(sys.modules):
    if _module_name == "freecad_mcp" or _module_name.startswith("freecad_mcp."):
        del sys.modules[_module_name]

import freecad_mcp.freecad.sketch_reference_constraints as reference_module  # noqa: E402
from freecad_mcp.exceptions import (  # noqa: E402
    SketchExternalGeometryRemovalUnsafeError,
    SketchGeometryRemovalUnsafeError,
    SketchReferenceConstraintError,
)
from freecad_mcp.freecad.document import FreeCADDocumentAdapter  # noqa: E402
from freecad_mcp.models import (  # noqa: E402
    LineSegmentGeometryUpdateInput,
    ObjectSubelementExternalGeometrySourceInput,
    SketchGeometryExternalGeometrySourceInput,
    SketchPoint2DInput,
    SketchReferenceConstraintInput,
)
from freecad_mcp.reference_constraint_capabilities import (  # noqa: E402
    SUPPORTED_EQUAL_GEOMETRY_PAIRS,
    SUPPORTED_MIXED_VARIANT_MODES,
    SUPPORTED_TANGENT_GEOMETRY_PAIRS,
)
from freecad_mcp.tool_registry import REGISTERED_TOOL_NAMES  # noqa: E402
from freecad_mcp.transaction_names import (  # noqa: E402
    ADD_SKETCH_REFERENCE_CONSTRAINTS_TRANSACTION_NAME,
)


class _HeadlessGuiDocument:
    def __init__(self) -> None:
        self.Modified = True
        self.in_edit: Any | None = None

    def getInEdit(self) -> Any | None:
        return self.in_edit


class _HeadlessSelection:
    selected: ClassVar[list[Any]] = []

    @classmethod
    def getSelection(cls) -> list[Any]:
        return list(cls.selected)


_GUI_DOCUMENTS: dict[str, _HeadlessGuiDocument] = {}
if not hasattr(Gui, "getDocument"):
    Gui.getDocument = lambda name: _GUI_DOCUMENTS.setdefault(name, _HeadlessGuiDocument())
if not hasattr(Gui, "Selection"):
    Gui.Selection = _HeadlessSelection()

_ADAPTER = FreeCADDocumentAdapter()
_CONSTRAINT_ADAPTER: TypeAdapter[SketchReferenceConstraintInput] = TypeAdapter(
    SketchReferenceConstraintInput
)
_ASSERTIONS: dict[str, object] = {}


def _record(name: str, condition: bool, value: object = True) -> None:
    if not condition:
        raise AssertionError(f"{name}: {value!r}")
    _ASSERTIONS[f"{len(_ASSERTIONS) + 1:03d}_{name}"] = value


def _new_document(name: str) -> Any:
    if name in App.listDocuments():
        App.closeDocument(name)
    document = App.newDocument(name)
    document.UndoMode = 1
    _GUI_DOCUMENTS[name] = _HeadlessGuiDocument()
    return document


def _close(name: str) -> None:
    if name in App.listDocuments():
        App.closeDocument(name)
    _GUI_DOCUMENTS.pop(name, None)


def _line(start_x: float, start_y: float, end_x: float, end_y: float) -> Any:
    return Part.LineSegment(
        App.Vector(start_x, start_y, 0.0),
        App.Vector(end_x, end_y, 0.0),
    )


def _circle(center_x: float, center_y: float, radius: float) -> Any:
    return Part.Circle(
        App.Vector(center_x, center_y, 0.0),
        App.Vector(0.0, 0.0, 1.0),
        radius,
    )


def _internal(index: int) -> dict[str, object]:
    return {"kind": "internal", "geometry_index": index}


def _external(number: int) -> dict[str, object]:
    return {"kind": "external", "external_reference_number": number}


def _point(geometry: dict[str, object], position: str) -> dict[str, object]:
    return {"geometry": geometry, "position": position}


def _constraints(*items: Mapping[str, object]) -> tuple[SketchReferenceConstraintInput, ...]:
    return tuple(_CONSTRAINT_ADAPTER.validate_python(item) for item in items)


def _source(sketch_name: str, geometry_index: int = 0) -> Any:
    return SketchGeometryExternalGeometrySourceInput(
        type="sketch_geometry",
        sketch_name=sketch_name,
        geometry_index=geometry_index,
    )


def _object_source(object_name: str, subelement: str) -> Any:
    return ObjectSubelementExternalGeometrySourceInput(
        type="object_subelement",
        object_name=object_name,
        subelement=subelement,
    )


def _point_input(x: float, y: float) -> SketchPoint2DInput:
    return SketchPoint2DInput(x=x, y=y)


def _line_update(start_x: float, start_y: float, end_x: float, end_y: float) -> Any:
    return LineSegmentGeometryUpdateInput(
        type="line_segment",
        start=_point_input(start_x, start_y),
        end=_point_input(end_x, end_y),
    )


def _history(document: Any) -> tuple[object, ...]:
    return (
        int(document.UndoCount),
        int(document.RedoCount),
        tuple(document.UndoNames),
        tuple(document.RedoNames),
        bool(document.HasPendingTransaction),
    )


def _controlled_state(document_name: str, sketch_name: str) -> tuple[object, ...]:
    document = App.getDocument(document_name)
    gui_document = Gui.getDocument(document_name)
    active = App.activeDocument()
    return (
        _ADAPTER.get_sketch(document_name, sketch_name).to_dict(),
        _ADAPTER.list_external_geometry(document_name, sketch_name).to_dict(),
        _ADAPTER.get_sketch_dependencies(document_name, sketch_name).to_dict(),
        _history(document),
        str(document.FileName),
        None if active is None else str(active.Name),
        bool(gui_document.Modified),
        gui_document.getInEdit(),
        tuple((str(item.Document.Name), str(item.Name)) for item in Gui.Selection.getSelection()),
    )


def _line_direction(sketch: Any, index: int = 0) -> tuple[float, float]:
    geometry = sketch.Geometry[index]
    return (
        float(geometry.EndPoint.x - geometry.StartPoint.x),
        float(geometry.EndPoint.y - geometry.StartPoint.y),
    )


def _parallel(first: tuple[float, float], second: tuple[float, float]) -> bool:
    scale = max(1.0, math.hypot(*first) * math.hypot(*second))
    return abs(first[0] * second[1] - first[1] * second[0]) <= 1e-7 * scale


def _inventory_and_internal_parity() -> None:
    _record("freecad_1_1_1", tuple(App.Version()[:3]) == ("1", "1", "1"))
    _record("exact_48_tool_inventory", len(REGISTERED_TOOL_NAMES) == 48)
    _record(
        "unchanged_milestone_20_tail",
        REGISTERED_TOOL_NAMES[31:34]
        == (
            "update_sketch_geometry",
            "replace_sketch_constraint",
            "update_sketch_constraint_value",
        ),
    )
    _record(
        "tool_35_appended",
        REGISTERED_TOOL_NAMES[34] == "add_sketch_reference_constraints",
    )
    _record(
        "milestone_22_tool_order",
        REGISTERED_TOOL_NAMES[35:39]
        == (
            "set_sketch_constraint_name",
            "set_sketch_constraint_expression",
            "clear_sketch_constraint_expression",
            "list_sketch_constraint_expressions",
        ),
    )
    _record("mixed_variant_mode_rules", len(SUPPORTED_MIXED_VARIANT_MODES) == 12)
    _record("equal_pair_rules", len(SUPPORTED_EQUAL_GEOMETRY_PAIRS) == 5)
    _record("tangent_pair_rules", len(SUPPORTED_TANGENT_GEOMETRY_PAIRS) == 8)

    document = _new_document("M21Internal")
    sketch = document.addObject("Sketcher::SketchObject", "Sketch")
    sketch.addGeometry([_line(0, 0, 6, 1), _line(0, 5, 6, 5)], False)
    document.recompute()
    document.clearUndos()
    result = _ADAPTER.add_sketch_reference_constraints(
        "M21Internal",
        "Sketch",
        _constraints({"type": "parallel", "first": _internal(0), "second": _internal(1)}),
    )
    _record(
        "internal_internal_parity",
        result.added_indices == (0,)
        and result.external_reference_numbers == ()
        and result.internal_geometry_indices == (0, 1),
    )
    _record(
        "owned_transaction_name",
        tuple(document.UndoNames) == (ADD_SKETCH_REFERENCE_CONSTRAINTS_TRANSACTION_NAME,),
    )
    _close("M21Internal")


def _mixed_relationships_and_refusals() -> None:
    document = _new_document("M21Mixed")
    source = document.addObject("Sketcher::SketchObject", "Source")
    source.addGeometry(
        [
            _line(0, 0, 10, 0),
            _line(0, 5, 10, 5),
        ],
        False,
    )
    tangent = document.addObject("Sketcher::SketchObject", "Tangent")
    tangent.addGeometry(_circle(5, 3, 2), False)
    parallel = document.addObject("Sketcher::SketchObject", "Parallel")
    parallel.addGeometry(_line(1, 1, 5, 3), False)
    perpendicular = document.addObject("Sketcher::SketchObject", "Perpendicular")
    perpendicular.addGeometry(_line(1, 1, 5, 3), False)
    coincident = document.addObject("Sketcher::SketchObject", "Coincident")
    coincident.addGeometry(_line(20, 20, 25, 22), False)
    point_on_object = document.addObject("Sketcher::SketchObject", "PointOnObject")
    point_on_object.addGeometry(_circle(2, 2, 4), False)
    dimensional = document.addObject("Sketcher::SketchObject", "Dimensional")
    dimensional.addGeometry(Part.Point(App.Vector(7, 3, 0)), False)
    document.recompute()
    for target_name, source_index in (
        ("Tangent", 0),
        ("Parallel", 0),
        ("Perpendicular", 0),
        ("Coincident", 0),
        ("PointOnObject", 0),
        ("Dimensional", 0),
    ):
        _ADAPTER.add_external_geometry("M21Mixed", target_name, _source("Source", source_index))
    document.clearUndos()

    tangent_result = _ADAPTER.add_sketch_reference_constraints(
        "M21Mixed",
        "Tangent",
        _constraints({"type": "tangent", "first": _internal(0), "second": _external(0)}),
    )
    _record("internal_circle_tangent_external_line", tangent_result.added_indices == (0,))
    serialized_tangent = json.dumps(tangent_result.to_dict(), sort_keys=True)
    _record(
        "no_native_negative_identity_leakage",
        "native_id" not in serialized_tangent and '"geometry_index": -' not in serialized_tangent,
    )
    parallel_result = _ADAPTER.add_sketch_reference_constraints(
        "M21Mixed",
        "Parallel",
        _constraints({"type": "parallel", "first": _external(0), "second": _internal(0)}),
    )
    _record("external_internal_parallel_order", parallel_result.added_indices == (0,))
    perpendicular_result = _ADAPTER.add_sketch_reference_constraints(
        "M21Mixed",
        "Perpendicular",
        _constraints({"type": "perpendicular", "first": _internal(0), "second": _external(0)}),
    )
    _record("internal_external_perpendicular_order", perpendicular_result.added_indices == (0,))
    coincident_result = _ADAPTER.add_sketch_reference_constraints(
        "M21Mixed",
        "Coincident",
        _constraints(
            {
                "type": "coincident",
                "first": _point(_external(0), "start"),
                "second": _point(_internal(0), "start"),
            }
        ),
    )
    _record(
        "external_endpoint_coincident_internal_endpoint", coincident_result.added_indices == (0,)
    )
    point_result = _ADAPTER.add_sketch_reference_constraints(
        "M21Mixed",
        "PointOnObject",
        _constraints(
            {
                "type": "point_on_object",
                "first": _point(_external(0), "start"),
                "second": _internal(0),
            }
        ),
    )
    _record("external_point_on_internal_circle", point_result.added_indices == (0,))
    distance_result = _ADAPTER.add_sketch_reference_constraints(
        "M21Mixed",
        "Dimensional",
        _constraints(
            {
                "type": "distance_x",
                "mode": "between_points",
                "first": _point(_external(0), "start"),
                "second": _point(_internal(0), "point"),
                "value": 5.0,
            }
        ),
    )
    _record("supported_mixed_dimension", distance_result.added_indices == (0,))

    refusal_sketch = document.addObject("Sketcher::SketchObject", "Refusal")
    refusal_sketch.addGeometry(_line(0, 2, 5, 3), False)
    document.recompute()
    _ADAPTER.add_external_geometry("M21Mixed", "Refusal", _source("Source", 0))
    _ADAPTER.add_external_geometry("M21Mixed", "Refusal", _source("Source", 1))
    document.clearUndos()
    before = _controlled_state("M21Mixed", "Refusal")
    refusal_reasons: list[str] = []
    for request in (
        {"type": "horizontal", "geometry": _external(0)},
        {"type": "parallel", "first": _external(0), "second": _external(1)},
        {
            "type": "coincident",
            "first": _point(_internal(0), "center"),
            "second": _point(_external(0), "start"),
        },
    ):
        try:
            _ADAPTER.add_sketch_reference_constraints("M21Mixed", "Refusal", _constraints(request))
        except SketchReferenceConstraintError as exc:
            refusal_reasons.append(exc.reason)
        else:
            raise AssertionError(f"unsupported request was accepted: {request!r}")
    _record(
        "unsupported_preflight_reasons",
        refusal_reasons
        == ["external_only_constraint", "external_only_constraint", "unsupported_point_position"],
    )
    duplicate = {
        "type": "parallel",
        "first": _internal(0),
        "second": _external(0),
    }
    try:
        _ADAPTER.add_sketch_reference_constraints(
            "M21Mixed", "Refusal", _constraints(duplicate, duplicate)
        )
    except SketchReferenceConstraintError as exc:
        duplicate_reason = exc.reason
    else:
        raise AssertionError("duplicate batch was accepted")
    _record("duplicate_batch_refused", duplicate_reason == "duplicate_constraint")
    try:
        _ADAPTER.add_sketch_reference_constraints(
            "M21Mixed",
            "Refusal",
            _constraints(
                duplicate,
                {"type": "horizontal", "geometry": _external(1)},
            ),
        )
    except SketchReferenceConstraintError:
        pass
    else:
        raise AssertionError("mixed safe/unsupported batch was accepted")
    _record("mixed_batch_atomic_refusal", _controlled_state("M21Mixed", "Refusal") == before)
    _record("refusals_create_zero_history", int(document.UndoCount) == 0)
    corrected = _ADAPTER.add_sketch_reference_constraints(
        "M21Mixed",
        "Refusal",
        _constraints(duplicate),
    )
    _record("same_sketch_correction", corrected.added_indices == (0,))
    _close("M21Mixed")


def _dependency_and_removal_cases() -> None:
    document = _new_document("M21Removal")
    source = document.addObject("Sketcher::SketchObject", "Source")
    source.addGeometry(_line(0, 0, 10, 0), False)
    target = document.addObject("Sketcher::SketchObject", "Target")
    target.addGeometry(_line(0, 2, 8, 4), False)
    document.recompute()
    _ADAPTER.add_external_geometry("M21Removal", "Target", _source("Source"))
    document.clearUndos()
    added = _ADAPTER.add_sketch_reference_constraints(
        "M21Removal",
        "Target",
        _constraints({"type": "parallel", "first": _internal(0), "second": _external(0)}),
    )
    dependencies = _ADAPTER.get_sketch_dependencies("M21Removal", "Target")
    _record(
        "exact_dependency_reporting",
        dependencies.constraint_external_references
        == ({"external_reference_number": 0, "constraint_indices": [0]},),
        dependencies.constraint_external_references,
    )
    listed = _ADAPTER.list_external_geometry("M21Removal", "Target")
    _record(
        "external_usage_readback",
        listed.external_geometry[0].used_by_constraint_indices == (0,),
    )
    try:
        _ADAPTER.remove_external_geometry("M21Removal", "Target", 0)
    except SketchExternalGeometryRemovalUnsafeError as exc:
        external_dependents = exc.constraint_indices
    else:
        raise AssertionError("used external reference was removed")
    _record("external_removal_refused_while_used", external_dependents == (0,))
    try:
        _ADAPTER.remove_sketch_geometry("M21Removal", "Target", (0,))
    except SketchGeometryRemovalUnsafeError as exc:
        geometry_dependents = exc.dependencies
    else:
        raise AssertionError("constrained internal geometry was removed")
    _record(
        "internal_geometry_removal_refused",
        geometry_dependents == ({"geometry_index": 0, "dependent_constraint_indices": [0]},),
    )
    removed_constraint = _ADAPTER.remove_sketch_constraints("M21Removal", "Target", (0,))
    _record(
        "explicit_reference_constraint_removal",
        removed_constraint.removed_constraint_indices == (0,)
        and removed_constraint.sketch.constraint_count == 0,
    )
    removed_external = _ADAPTER.remove_external_geometry("M21Removal", "Target", 0)
    _record(
        "external_removal_after_constraint",
        removed_external.action == "remove" and not removed_external.external_geometry,
    )
    _record(
        "added_result_dependency_summary", added.dependencies.constraint_external_references != ()
    )
    _close("M21Removal")


def _linear_source_propagation() -> None:
    document = _new_document("M21LinearPropagation")
    source = document.addObject("Sketcher::SketchObject", "Source")
    source.addGeometry(_line(0, 0, 10, 0), False)
    target = document.addObject("Sketcher::SketchObject", "Target")
    target.addGeometry(_line(2, 4, 8, 6), False)
    document.recompute()
    _ADAPTER.add_external_geometry("M21LinearPropagation", "Target", _source("Source"))
    _ADAPTER.add_sketch_reference_constraints(
        "M21LinearPropagation",
        "Target",
        _constraints({"type": "parallel", "first": _internal(0), "second": _external(0)}),
    )
    before_target = _line_direction(target)
    _ADAPTER.update_sketch_geometry(
        "M21LinearPropagation",
        "Source",
        0,
        _line_update(0, 0, 10, 5),
    )
    document.recompute()
    after_target = _line_direction(target)
    source_direction = _line_direction(source)
    _record(
        "linear_source_change_propagates",
        before_target != after_target and _parallel(after_target, source_direction),
        (before_target, after_target, source_direction),
    )
    _record(
        "linear_mapping_preserved",
        _ADAPTER.list_external_geometry("M21LinearPropagation", "Target")
        .external_geometry[0]
        .resolved,
    )
    _record("linear_constraint_preserved", int(target.ConstraintCount) == 1)
    _close("M21LinearPropagation")


def _circumcircle_source_propagation() -> None:
    document = _new_document("M21Circumcircle")
    source = document.addObject("Sketcher::SketchObject", "Triangle")
    source.addGeometry(
        [_line(0, 0, 8, 0), _line(8, 0, 4, 6), _line(4, 6, 0, 0)],
        False,
    )
    target = document.addObject("Sketcher::SketchObject", "Circumcircle")
    target.addGeometry(_circle(4, 2, 4.5), False)
    document.recompute()
    for source_index in range(2):
        _ADAPTER.add_external_geometry(
            "M21Circumcircle", "Circumcircle", _source("Triangle", source_index)
        )
    result = _ADAPTER.add_sketch_reference_constraints(
        "M21Circumcircle",
        "Circumcircle",
        _constraints(
            {
                "type": "point_on_object",
                "first": _point(_external(0), "start"),
                "second": _internal(0),
            },
            {
                "type": "point_on_object",
                "first": _point(_external(0), "end"),
                "second": _internal(0),
            },
            {
                "type": "point_on_object",
                "first": _point(_external(1), "end"),
                "second": _internal(0),
            },
        ),
    )
    before_circle = target.Geometry[0]
    before = (
        float(before_circle.Center.x),
        float(before_circle.Center.y),
        float(before_circle.Radius),
    )
    _record(
        "circumcircle_point_on_object_batch",
        result.added_indices == (0, 1, 2) and int(target.GeometryCount) == 1,
    )
    _ADAPTER.update_sketch_geometry(
        "M21Circumcircle",
        "Triangle",
        1,
        _line_update(8, 0, 4, 8),
    )
    document.recompute()
    after_circle = target.Geometry[0]
    after = (
        float(after_circle.Center.x),
        float(after_circle.Center.y),
        float(after_circle.Radius),
    )
    _record("circumcircle_source_change_propagates", before != after, (before, after))
    _record(
        "circumcircle_intent_preserved",
        int(target.ConstraintCount) == 3
        and int(target.GeometryCount) == 1
        and all(
            item.resolved
            for item in _ADAPTER.list_external_geometry(
                "M21Circumcircle", "Circumcircle"
            ).external_geometry
        ),
    )
    _close("M21Circumcircle")


def _incircle_source_propagation() -> None:
    document = _new_document("M21Incircle")
    source = document.addObject("Sketcher::SketchObject", "Triangle")
    source.addGeometry(
        [_line(0, 0, 8, 0), _line(8, 0, 4, 6), _line(4, 6, 0, 0)],
        False,
    )
    target = document.addObject("Sketcher::SketchObject", "Incircle")
    target.addGeometry(_circle(4, 2, 2), False)
    document.recompute()
    for source_index in range(3):
        _ADAPTER.add_external_geometry("M21Incircle", "Incircle", _source("Triangle", source_index))
    result = _ADAPTER.add_sketch_reference_constraints(
        "M21Incircle",
        "Incircle",
        _constraints(
            *(
                {"type": "tangent", "first": _internal(0), "second": _external(index)}
                for index in range(3)
            )
        ),
    )
    before_circle = target.Geometry[0]
    before = (
        float(before_circle.Center.x),
        float(before_circle.Center.y),
        float(before_circle.Radius),
    )
    _record(
        "incircle_three_tangencies",
        result.added_indices == (0, 1, 2) and int(target.GeometryCount) == 1,
    )
    _ADAPTER.update_sketch_geometry(
        "M21Incircle",
        "Triangle",
        1,
        _line_update(8, 0, 5, 8),
    )
    document.recompute()
    after_circle = target.Geometry[0]
    after = (
        float(after_circle.Center.x),
        float(after_circle.Center.y),
        float(after_circle.Radius),
    )
    _record("incircle_source_change_propagates", before != after, (before, after))
    _record(
        "incircle_intent_preserved",
        int(target.ConstraintCount) == 3
        and int(target.GeometryCount) == 1
        and all(
            item.resolved
            for item in _ADAPTER.list_external_geometry("M21Incircle", "Incircle").external_geometry
        ),
    )
    _close("M21Incircle")


def _equilateral_source(document: Any, name: str) -> Any:
    source = document.addObject("Sketcher::SketchObject", name)
    radius = 30.0
    vertices = tuple(
        (
            radius * math.cos(math.radians(90.0 + 120.0 * index)),
            radius * math.sin(math.radians(90.0 + 120.0 * index)),
        )
        for index in range(3)
    )
    source.addGeometry(
        [_line(*vertices[index], *vertices[(index + 1) % 3]) for index in range(3)],
        False,
    )
    return source


def _inject_solver_failure(call: Any, reason: str) -> SketchReferenceConstraintError:
    original_verify: Any = reference_module._verify_solver

    def _fail_solver(_solver: Any) -> None:
        raise SketchReferenceConstraintError(
            code="external_constraint_solver_conflict",
            reason=reason,
        )

    reference_module._verify_solver = _fail_solver
    try:
        try:
            call()
        except SketchReferenceConstraintError as exc:
            return exc
        raise AssertionError(f"{reason} did not fail")
    finally:
        reference_module._verify_solver = original_verify


def _live_topology_rollback_regressions() -> None:
    document = _new_document("M21CircumcircleSequentialRollback")
    _equilateral_source(document, "Source")
    target = document.addObject("Sketcher::SketchObject", "Target")
    target.addGeometry(_circle(0, 0, 20), False)
    document.recompute()
    for source_index in range(3):
        _ADAPTER.add_external_geometry(document.Name, "Target", _source("Source", source_index))
    document.clearUndos()
    for source_index in range(2):
        _ADAPTER.add_sketch_reference_constraints(
            document.Name,
            "Target",
            _constraints(
                {
                    "type": "point_on_object",
                    "first": _point(_external(source_index), "start"),
                    "second": _internal(0),
                }
            ),
        )
    before = _controlled_state(document.Name, "Target")
    failure = _inject_solver_failure(
        lambda: _ADAPTER.add_sketch_reference_constraints(
            document.Name,
            "Target",
            _constraints(
                {
                    "type": "point_on_object",
                    "first": _point(_external(2), "start"),
                    "second": _internal(0),
                }
            ),
        ),
        "third_sequential_point_on_object_solver_failure",
    )
    after = _controlled_state(document.Name, "Target")
    _record("third_point_on_object_failure_controlled", failure.index is None)
    _record("third_point_on_object_exact_rollback", after == before)
    _record(
        "third_point_on_object_no_failed_history",
        len(tuple(document.UndoNames)) == 2
        and tuple(document.UndoNames)
        == (
            ADD_SKETCH_REFERENCE_CONSTRAINTS_TRANSACTION_NAME,
            ADD_SKETCH_REFERENCE_CONSTRAINTS_TRANSACTION_NAME,
        ),
        tuple(document.UndoNames),
    )
    corrected = _ADAPTER.add_sketch_reference_constraints(
        document.Name,
        "Target",
        _constraints(
            {
                "type": "point_on_object",
                "first": _point(_external(2), "start"),
                "second": _internal(0),
            }
        ),
    )
    _record(
        "third_point_on_object_same_sketch_retry",
        corrected.added_indices == (2,) and int(target.ConstraintCount) == 3,
    )
    _close(document.Name)

    document = _new_document("M21CircumcircleBatchRollback")
    _equilateral_source(document, "Source")
    target = document.addObject("Sketcher::SketchObject", "Target")
    target.addGeometry(_circle(0, 0, 20), False)
    document.recompute()
    for source_index in range(3):
        _ADAPTER.add_external_geometry(document.Name, "Target", _source("Source", source_index))
    document.clearUndos()
    before = _controlled_state(document.Name, "Target")
    _inject_solver_failure(
        lambda: _ADAPTER.add_sketch_reference_constraints(
            document.Name,
            "Target",
            _constraints(
                *(
                    {
                        "type": "point_on_object",
                        "first": _point(_external(index), "start"),
                        "second": _internal(0),
                    }
                    for index in range(3)
                )
            ),
        ),
        "circumcircle_batch_solver_failure",
    )
    _record(
        "circumcircle_batch_exact_zero_history_rollback",
        _controlled_state(document.Name, "Target") == before,
    )
    _close(document.Name)

    document = _new_document("M21IncircleSequentialRollback")
    _equilateral_source(document, "Source")
    target = document.addObject("Sketcher::SketchObject", "Target")
    target.addGeometry(_circle(0, 0, 10), False)
    document.recompute()
    for source_index in range(3):
        _ADAPTER.add_external_geometry(document.Name, "Target", _source("Source", source_index))
    document.clearUndos()
    _ADAPTER.add_sketch_reference_constraints(
        document.Name,
        "Target",
        _constraints({"type": "tangent", "first": _internal(0), "second": _external(0)}),
    )
    before = _controlled_state(document.Name, "Target")
    failure = _inject_solver_failure(
        lambda: _ADAPTER.add_sketch_reference_constraints(
            document.Name,
            "Target",
            _constraints({"type": "tangent", "first": _internal(0), "second": _external(1)}),
        ),
        "second_sequential_tangent_solver_failure",
    )
    _record("second_tangent_failure_controlled", failure.index is None)
    _record(
        "second_tangent_exact_zero_history_rollback",
        _controlled_state(document.Name, "Target") == before,
    )
    corrected = _ADAPTER.add_sketch_reference_constraints(
        document.Name,
        "Target",
        _constraints({"type": "tangent", "first": _internal(0), "second": _external(1)}),
    )
    _record(
        "second_tangent_same_sketch_retry",
        corrected.added_indices == (1,) and int(target.ConstraintCount) == 2,
    )
    _close(document.Name)

    document = _new_document("M21IncircleBatchRollback")
    _equilateral_source(document, "Source")
    target = document.addObject("Sketcher::SketchObject", "Target")
    target.addGeometry(_circle(0, 0, 10), False)
    document.recompute()
    for source_index in range(3):
        _ADAPTER.add_external_geometry(document.Name, "Target", _source("Source", source_index))
    document.clearUndos()
    before = _controlled_state(document.Name, "Target")
    _inject_solver_failure(
        lambda: _ADAPTER.add_sketch_reference_constraints(
            document.Name,
            "Target",
            _constraints(
                *(
                    {
                        "type": "tangent",
                        "first": _internal(0),
                        "second": _external(index),
                    }
                    for index in range(3)
                )
            ),
        ),
        "incircle_batch_solver_failure",
    )
    _record(
        "incircle_batch_exact_zero_history_rollback",
        _controlled_state(document.Name, "Target") == before,
    )
    _close(document.Name)

    document = _new_document("M21NaturalSolverRollback")
    source = document.addObject("Sketcher::SketchObject", "Source")
    source.addGeometry(_line(0, 0, 10, 0), False)
    target = document.addObject("Sketcher::SketchObject", "Target")
    target.addGeometry(_line(0, 2, 7, 5), False)
    document.recompute()
    _ADAPTER.add_external_geometry(document.Name, "Target", _source("Source"))
    document.clearUndos()
    conflicting = _constraints(
        {"type": "parallel", "first": _internal(0), "second": _external(0)},
        {"type": "perpendicular", "first": _internal(0), "second": _external(0)},
    )
    before = _controlled_state(document.Name, "Target")
    try:
        _ADAPTER.add_sketch_reference_constraints(document.Name, "Target", conflicting)
    except SketchReferenceConstraintError as exc:
        natural_reason = exc.reason
    else:
        raise AssertionError("naturally conflicting mixed batch unexpectedly succeeded")
    _record(
        "natural_solver_failure_controlled",
        natural_reason in {"solver_state_unavailable", "solver_conflict"},
        natural_reason,
    )
    _record(
        "natural_solver_failure_exact_zero_history_rollback",
        _controlled_state(document.Name, "Target") == before
        and int(document.UndoCount) == 0
        and int(document.RedoCount) == 0,
        _history(document),
    )
    corrected = _ADAPTER.add_sketch_reference_constraints(
        document.Name,
        "Target",
        _constraints({"type": "parallel", "first": _internal(0), "second": _external(0)}),
    )
    _record("natural_failure_same_sketch_correction", corrected.added_indices == (0,))
    document.undo()
    document.clearUndos()

    document.openTransaction("Caller natural solver rollback")
    target.Label = "Caller-owned natural target"
    caller_before = _controlled_state(document.Name, "Target")
    try:
        _ADAPTER.add_sketch_reference_constraints(document.Name, "Target", conflicting)
    except SketchReferenceConstraintError:
        pass
    else:
        raise AssertionError("caller-owned naturally conflicting batch unexpectedly succeeded")
    _record(
        "caller_owned_natural_failure_exact_rollback",
        bool(document.HasPendingTransaction)
        and _controlled_state(document.Name, "Target") == caller_before,
    )
    document.abortTransaction()
    _close(document.Name)


def _zero_effect_owned_history_cleanup_regression() -> None:
    document = _new_document("M21ZeroEffectHistoryCleanup")
    sketch = document.addObject("Sketcher::SketchObject", "Target")
    sketch.addGeometry(_line(0, 0, 10, 2), False)
    document.recompute()
    document.clearUndos()

    document.openTransaction("Earlier retained transaction")
    sketch.Label = "Stable target"
    document.commitTransaction()
    other = _new_document("M21ZeroEffectHistoryOther")
    other.addObject("Sketcher::SketchObject", "OtherSketch")
    other.recompute()
    other.clearUndos()
    before_state = _controlled_state(document.Name, "Target")
    other_before = _history(other)
    before_history = (
        int(document.UndoMode),
        int(document.UndoCount),
        int(document.RedoCount),
        tuple(document.UndoNames),
        tuple(document.RedoNames),
    )

    App.setActiveDocument(document.Name)
    document.openTransaction(ADD_SKETCH_REFERENCE_CONSTRAINTS_TRANSACTION_NAME)
    sketch.Label = "Transient failed target"
    sketch.Label = "Stable target"
    document.commitTransaction()
    App.setActiveDocument(other.Name)
    _record(
        "zero_effect_history_fixture_has_one_leaked_record",
        tuple(document.UndoNames)
        == (
            ADD_SKETCH_REFERENCE_CONSTRAINTS_TRANSACTION_NAME,
            "Earlier retained transaction",
        ),
        _history(document),
    )

    reference_module._repair_zero_effect_owned_history(document, sketch, before_history, App)
    _record(
        "zero_effect_owned_history_cleanup_is_exact",
        _controlled_state(document.Name, "Target") == before_state,
        _history(document),
    )
    _record(
        "zero_effect_history_cleanup_cross_document_isolation",
        _history(other) == other_before and str(App.activeDocument().Name) == other.Name,
        (_history(other), other_before),
    )
    _close(document.Name)
    _close(other.Name)


def _populate_history(document: Any, target: Any, count: int, prefix: str) -> None:
    for index in range(count):
        document.openTransaction(f"{prefix} {index + 1:02d}")
        target.Label = f"{prefix} target {index + 1:02d}"
        document.commitTransaction()


def _capacity_fixture(name: str, undo_count: int) -> tuple[Any, Any]:
    document = _new_document(name)
    source = document.addObject("Sketcher::SketchObject", "Source")
    source.addGeometry(_line(0, 0, 10, 0), False)
    source.addConstraint(Sketcher.Constraint("Horizontal", 0))
    target = document.addObject("Sketcher::SketchObject", "Target")
    target.addGeometry(_line(0, 2, 10, 2), False)
    target.addConstraint(Sketcher.Constraint("Horizontal", 0))
    document.recompute()
    _ADAPTER.add_external_geometry(name, "Target", _source("Source"))
    document.clearUndos()
    _populate_history(document, target, undo_count, f"{name} history")
    return document, target


def _expect_redundant_parallel(document_name: str) -> SketchReferenceConstraintError:
    try:
        _ADAPTER.add_sketch_reference_constraints(
            document_name,
            "Target",
            _constraints({"type": "parallel", "first": _internal(0), "second": _external(0)}),
        )
    except SketchReferenceConstraintError as exc:
        return exc
    raise AssertionError("redundant mixed parallel request unexpectedly succeeded")


def _undo_capacity_redundancy_regressions() -> None:
    discover, discover_target = _capacity_fixture("M21CapacityDiscover", 0)
    _populate_history(discover, discover_target, 40, "Limit probe")
    undo_limit = int(discover.UndoCount)
    _record(
        "configured_undo_capacity_is_twenty",
        undo_limit == 20 and len(tuple(discover.UndoNames)) == undo_limit,
        _history(discover),
    )
    _close(discover.Name)

    document, target = _capacity_fixture("M21CapacityOwned", undo_limit)
    before = _controlled_state(document.Name, "Target")
    oldest = str(document.UndoNames[-1])
    failure = _expect_redundant_parallel(document.Name)
    after = _controlled_state(document.Name, "Target")
    _record(
        "capacity_redundant_parallel_preflight_refusal",
        failure.code == "external_constraint_duplicate"
        and failure.reason == "redundant_constraint",
        (failure.code, failure.reason),
    )
    _record("capacity_failure_complete_state_and_history_equality", after == before)
    _record(
        "capacity_failure_preserves_oldest_history",
        str(document.UndoNames[-1]) == oldest
        and ADD_SKETCH_REFERENCE_CONSTRAINTS_TRANSACTION_NAME not in tuple(document.UndoNames),
        _history(document),
    )
    recovered = _ADAPTER.add_sketch_reference_constraints(
        document.Name,
        "Target",
        _constraints(
            {
                "type": "distance_y",
                "mode": "between_points",
                "first": _point(_external(0), "start"),
                "second": _point(_internal(0), "start"),
                "value": 5.0,
            }
        ),
    )
    _record(
        "capacity_failure_same_sketch_valid_recovery",
        recovered.added_indices == (1,) and int(target.ConstraintCount) == 2,
        _history(document),
    )
    _close(document.Name)

    redo_document, _redo_target = _capacity_fixture("M21CapacityRedo", undo_limit)
    redo_document.undo()
    redo_before = _controlled_state(redo_document.Name, "Target")
    _expect_redundant_parallel(redo_document.Name)
    _record(
        "capacity_preflight_preserves_complete_redo_history",
        _controlled_state(redo_document.Name, "Target") == redo_before
        and int(redo_document.RedoCount) == 1,
        _history(redo_document),
    )
    _close(redo_document.Name)

    first, _first_target = _capacity_fixture("M21CapacityDocA", undo_limit)
    second, _second_target = _capacity_fixture("M21CapacityDocB", undo_limit)
    App.setActiveDocument(second.Name)
    first_before = _controlled_state(first.Name, "Target")
    second_before = _controlled_state(second.Name, "Target")
    _expect_redundant_parallel(first.Name)
    _record(
        "capacity_cross_document_forward_failure_isolation",
        _controlled_state(first.Name, "Target") == first_before
        and _controlled_state(second.Name, "Target") == second_before
        and str(App.activeDocument().Name) == second.Name,
    )
    App.setActiveDocument(first.Name)
    first_before = _controlled_state(first.Name, "Target")
    second_before = _controlled_state(second.Name, "Target")
    _expect_redundant_parallel(second.Name)
    _record(
        "capacity_cross_document_reverse_failure_isolation",
        _controlled_state(first.Name, "Target") == first_before
        and _controlled_state(second.Name, "Target") == second_before
        and str(App.activeDocument().Name) == first.Name,
    )
    _close(first.Name)
    _close(second.Name)

    caller, caller_target = _capacity_fixture("M21CapacityCaller", undo_limit)
    caller_baseline = _controlled_state(caller.Name, "Target")
    caller.openTransaction("Caller capacity transaction")
    caller_target.Label = "Caller capacity target"
    caller_before = _controlled_state(caller.Name, "Target")
    _expect_redundant_parallel(caller.Name)
    _record(
        "capacity_caller_owned_failure_left_open_and_exact",
        bool(caller.HasPendingTransaction)
        and _controlled_state(caller.Name, "Target") == caller_before,
        _history(caller),
    )
    caller.abortTransaction()
    _record(
        "capacity_caller_abort_restores_baseline",
        _controlled_state(caller.Name, "Target") == caller_baseline,
        _history(caller),
    )
    _close(caller.Name)


def _object_source_cases() -> None:
    document = _new_document("M21ObjectSources")
    box = document.addObject("Part::Box", "Box")
    box.Length = 10
    box.Width = 10
    box.Height = 10
    edge_target = document.addObject("Sketcher::SketchObject", "EdgeTarget")
    edge_target.addGeometry(_circle(5, 2, 2), False)
    vertex_target = document.addObject("Sketcher::SketchObject", "VertexTarget")
    vertex_target.addGeometry(_circle(3, 0, 3), False)
    document.recompute()
    edge = _ADAPTER.add_external_geometry(
        "M21ObjectSources", "EdgeTarget", _object_source("Box", "Edge9")
    )
    vertex = _ADAPTER.add_external_geometry(
        "M21ObjectSources", "VertexTarget", _object_source("Box", "Vertex1")
    )
    _record(
        "object_edge_and_vertex_categories",
        edge.reference.reference_category == "object_edge"
        and vertex.reference.reference_category == "object_vertex",
    )
    edge_result = _ADAPTER.add_sketch_reference_constraints(
        "M21ObjectSources",
        "EdgeTarget",
        _constraints({"type": "tangent", "first": _internal(0), "second": _external(0)}),
    )
    vertex_result = _ADAPTER.add_sketch_reference_constraints(
        "M21ObjectSources",
        "VertexTarget",
        _constraints(
            {
                "type": "point_on_object",
                "first": _point(_external(0), "point"),
                "second": _internal(0),
            }
        ),
    )
    _record(
        "object_edge_and_vertex_constraints",
        edge_result.added_indices == (0,) and vertex_result.added_indices == (0,),
    )
    _close("M21ObjectSources")


def _history_caller_rollback_and_isolation() -> None:
    document = _new_document("M21History")
    source = document.addObject("Sketcher::SketchObject", "Source")
    source.addGeometry(_line(0, 0, 10, 0), False)
    target = document.addObject("Sketcher::SketchObject", "Target")
    target.addGeometry([_line(0, 2, 7, 5), _line(0, 5, 7, 7)], False)
    document.recompute()
    _ADAPTER.add_external_geometry("M21History", "Target", _source("Source"))
    document.clearUndos()
    _ADAPTER.add_sketch_reference_constraints(
        "M21History",
        "Target",
        _constraints({"type": "parallel", "first": _internal(0), "second": _external(0)}),
    )
    after_add = _ADAPTER.get_sketch("M21History", "Target")
    document.undo()
    _record("undo_reference_constraint", int(target.ConstraintCount) == 0)
    document.redo()
    after_redo = _ADAPTER.get_sketch("M21History", "Target")
    _record(
        "redo_reference_constraint",
        after_redo.constraint_count == after_add.constraint_count == 1
        and after_redo.constraints == after_add.constraints
        and _ADAPTER.list_external_geometry("M21History", "Target")
        .external_geometry[0]
        .used_by_constraint_indices
        == (0,),
    )
    document.undo()
    _ADAPTER.add_sketch_reference_constraints(
        "M21History",
        "Target",
        _constraints({"type": "perpendicular", "first": _internal(0), "second": _internal(1)}),
    )
    _record("redo_invalidation", int(document.RedoCount) == 0)
    document.undo()
    document.clearUndos()

    document.openTransaction("Caller reference batch")
    target.Label = "Caller-owned target"
    caller_history = _history(document)
    caller_result = _ADAPTER.add_sketch_reference_constraints(
        "M21History",
        "Target",
        _constraints({"type": "parallel", "first": _internal(1), "second": _external(0)}),
    )
    _record(
        "caller_owned_transaction_remains_open",
        caller_result.added_indices == (0,)
        and bool(document.HasPendingTransaction)
        and _history(document) == caller_history,
        (caller_result.added_indices, _history(document), caller_history),
    )
    document.commitTransaction()
    _record(
        "caller_owned_one_history_step", tuple(document.UndoNames) == ("Caller reference batch",)
    )
    document.clearUndos()

    before_rollback = _controlled_state("M21History", "Target")
    original_verify: Any = reference_module._verify_native_constraints

    def _fail_verify(*_args: Any) -> None:
        raise SketchReferenceConstraintError(
            code="external_constraint_solver_conflict",
            reason="injected_verification_failure",
        )

    reference_module._verify_native_constraints = _fail_verify
    try:
        try:
            _ADAPTER.add_sketch_reference_constraints(
                "M21History",
                "Target",
                _constraints(
                    {
                        "type": "perpendicular",
                        "first": _internal(0),
                        "second": _internal(1),
                    }
                ),
            )
        except SketchReferenceConstraintError:
            pass
        else:
            raise AssertionError("injected verification failure did not propagate")
    finally:
        reference_module._verify_native_constraints = original_verify
    _record(
        "owned_failure_exact_rollback",
        _controlled_state("M21History", "Target") == before_rollback,
    )
    _record("rollback_zero_history", int(document.UndoCount) == 0)

    document.openTransaction("Caller failure")
    target.Label = "Caller failure target"
    caller_failure_before = _controlled_state("M21History", "Target")
    reference_module._verify_native_constraints = _fail_verify
    try:
        try:
            _ADAPTER.add_sketch_reference_constraints(
                "M21History",
                "Target",
                _constraints(
                    {
                        "type": "perpendicular",
                        "first": _internal(0),
                        "second": _internal(1),
                    }
                ),
            )
        except SketchReferenceConstraintError:
            pass
        else:
            raise AssertionError("caller-owned injected failure did not propagate")
    finally:
        reference_module._verify_native_constraints = original_verify
    _record(
        "caller_owned_failure_exact_rollback",
        bool(document.HasPendingTransaction)
        and _controlled_state("M21History", "Target") == caller_failure_before,
    )
    document.abortTransaction()
    document.clearUndos()

    other = _new_document("M21Other")
    other_target = other.addObject("Sketcher::SketchObject", "Target")
    other_target.addGeometry(
        [_line(100, 0, 110, 3), _line(100, 8, 109, 14)],
        False,
    )
    other.recompute()
    other.clearUndos()
    other_before = _controlled_state("M21Other", "Target")
    App.setActiveDocument("M21Other")
    _ADAPTER.add_sketch_reference_constraints(
        "M21History",
        "Target",
        _constraints({"type": "perpendicular", "first": _internal(0), "second": _internal(1)}),
    )
    _record("non_active_document_targeting", str(App.activeDocument().Name) == "M21Other")
    other_after = _controlled_state("M21Other", "Target")
    _record(
        "same_named_cross_document_exact_isolation",
        other_after == other_before,
        (other_before, other_after),
    )

    App.setActiveDocument("M21History")
    primary_before = _controlled_state("M21History", "Target")
    _ADAPTER.add_sketch_reference_constraints(
        "M21Other",
        "Target",
        _constraints(
            {
                "type": "parallel",
                "first": _internal(0),
                "second": _internal(1),
            }
        ),
    )
    _record(
        "reverse_non_active_document_targeting",
        str(App.activeDocument().Name) == "M21History",
    )
    primary_after = _controlled_state("M21History", "Target")
    _record(
        "reverse_same_named_cross_document_exact_isolation",
        primary_after == primary_before,
        (primary_before, primary_after),
    )
    _record("no_gui_edit_mode_mutation", Gui.getDocument("M21History").getInEdit() is None)
    _close("M21History")
    _close("M21Other")


def _persistence_and_no_auto_save() -> None:
    document = _new_document("M21Saved")
    source = document.addObject("Sketcher::SketchObject", "Source")
    source.addGeometry(_line(0, 0, 10, 0), False)
    target = document.addObject("Sketcher::SketchObject", "Target")
    target.addGeometry(_line(0, 2, 8, 5), False)
    document.recompute()
    _ADAPTER.add_external_geometry("M21Saved", "Target", _source("Source"))
    descriptor, path_text = tempfile.mkstemp(suffix=".FCStd")
    os.close(descriptor)
    path = Path(path_text)
    path.unlink()
    try:
        document.saveAs(str(path))
        before_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        _ADAPTER.add_sketch_reference_constraints(
            "M21Saved",
            "Target",
            _constraints({"type": "parallel", "first": _internal(0), "second": _external(0)}),
        )
        after_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        _record("saved_document_not_auto_saved", before_hash == after_hash)
        document.save()
        App.closeDocument("M21Saved")
        _GUI_DOCUMENTS.pop("M21Saved", None)
        reopened = App.openDocument(str(path))
        reopened_name = str(reopened.Name)
        _GUI_DOCUMENTS[reopened_name] = _HeadlessGuiDocument()
        inspected = _ADAPTER.get_sketch(reopened_name, "Target")
        listed = _ADAPTER.list_external_geometry(reopened_name, "Target")
        _record(
            "native_save_reopen_preserves_reference_constraint",
            inspected.constraint_count == 1
            and listed.external_geometry[0].used_by_constraint_indices == (0,),
        )
        _close(reopened_name)
    finally:
        if path.exists():
            path.unlink()

    unsaved = _new_document("M21Unsaved")
    sketch = unsaved.addObject("Sketcher::SketchObject", "Sketch")
    sketch.addGeometry([_line(0, 0, 5, 2), _line(0, 4, 5, 4)], False)
    unsaved.recompute()
    _ADAPTER.add_sketch_reference_constraints(
        "M21Unsaved",
        "Sketch",
        _constraints({"type": "parallel", "first": _internal(0), "second": _internal(1)}),
    )
    _record("unsaved_document_remains_unsaved", str(unsaved.FileName) == "")
    _close("M21Unsaved")


def main() -> None:
    _inventory_and_internal_parity()
    _mixed_relationships_and_refusals()
    _dependency_and_removal_cases()
    _linear_source_propagation()
    _circumcircle_source_propagation()
    _incircle_source_propagation()
    _live_topology_rollback_regressions()
    _zero_effect_owned_history_cleanup_regression()
    _undo_capacity_redundancy_regressions()
    _object_source_cases()
    _history_caller_rollback_and_isolation()
    _persistence_and_no_auto_save()
    print(f"Milestone 21 native smoke passed: {len(_ASSERTIONS)}/{len(_ASSERTIONS)} assertions.")


if __name__ == "__main__":
    main()
