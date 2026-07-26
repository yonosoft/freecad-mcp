"""Atomic reference-aware sketch constraints through controlled FreeCAD APIs."""

from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Integral
from typing import Any, cast

from freecad_mcp.exceptions import (
    SketchExternalGeometryRollbackError,
    SketchReferenceConstraintError,
    SketchReferenceConstraintRollbackError,
)
from freecad_mcp.freecad import (
    document_operations,
    sketch_constraint_creation,
    sketch_dependencies,
    sketch_external_geometry,
    sketch_inspection,
    sketch_rectangle_creation,
)
from freecad_mcp.freecad.history_guard import history_activity
from freecad_mcp.models import (
    ExternalGeometryReferenceData,
    ExternalSketchGeometryReferenceInput,
    InternalSketchGeometryReferenceInput,
    SketchArcGeometry,
    SketchCircleGeometry,
    SketchGeometry,
    SketchGeometryReferenceInput,
    SketchHorizontalAxisReferenceInput,
    SketchLineGeometry,
    SketchOriginReferenceInput,
    SketchPointGeometry,
    SketchPointPosition,
    SketchReferenceConstraintAdditionResult,
    SketchReferenceConstraintInput,
    SketchReferenceConstraintPointInput,
    SketchReferenceConstraintSummary,
    SketchVerticalAxisReferenceInput,
    UnsupportedSketchGeometry,
)
from freecad_mcp.reference_constraint_capabilities import (
    OperandKind,
    decide_reference_constraint_capability,
)
from freecad_mcp.transaction_names import ADD_SKETCH_REFERENCE_CONSTRAINTS_TRANSACTION_NAME

_UNUSED = -2000
_ORIGIN = (-1, 1)
_REDUNDANCY_TOLERANCE = 1e-9
_POINT_POSITIONS = {
    SketchPointPosition.START: 1,
    SketchPointPosition.END: 2,
    SketchPointPosition.CENTER: 3,
    SketchPointPosition.POINT: 1,
}
_ROLLBACK_HISTORY_CLEANUP_TRANSACTION_NAME = "Clean failed sketch reference history"


@dataclass(frozen=True, slots=True)
class _ResolvedGeometry:
    native_id: int
    kind: OperandKind
    public_index: int
    geometry: SketchGeometry

    @property
    def geometry_type(self) -> str:
        if isinstance(self.geometry, SketchLineGeometry):
            return "line_segment"
        if isinstance(self.geometry, SketchCircleGeometry):
            return "circle"
        if isinstance(self.geometry, SketchArcGeometry):
            return "arc_of_circle"
        if isinstance(self.geometry, SketchPointGeometry):
            return "point"
        return "unsupported"


@dataclass(frozen=True, slots=True)
class _ResolvedPoint:
    geometry: _ResolvedGeometry
    position: int

    @property
    def native(self) -> tuple[int, int]:
        return self.geometry.native_id, self.position


@dataclass(frozen=True, slots=True)
class _NativeSpec:
    item: SketchReferenceConstraintInput
    native_type: str
    constructor_args: tuple[int | float, ...]
    fields: tuple[int, int, int, int, int, int]
    value: float
    semantic_key: tuple[object, ...]
    alternate_fields: tuple[tuple[int, int, int, int, int, int], ...] = ()


class _Resolver:
    def __init__(
        self,
        internal: tuple[SketchGeometry, ...],
        external: tuple[ExternalGeometryReferenceData, ...],
    ) -> None:
        self.internal = internal
        self.external = external
        self.resolved: list[_ResolvedGeometry] = []

    def geometry(self, operand: SketchGeometryReferenceInput, index: int) -> _ResolvedGeometry:
        if isinstance(operand, InternalSketchGeometryReferenceInput):
            if operand.geometry_index >= len(self.internal):
                raise _error(
                    "external_constraint_operand_invalid", "internal_geometry_not_found", index
                )
            geometry = self.internal[operand.geometry_index]
            resolved = _ResolvedGeometry(
                operand.geometry_index,
                "internal",
                operand.geometry_index,
                geometry,
            )
        else:
            assert isinstance(operand, ExternalSketchGeometryReferenceInput)
            number = operand.external_reference_number
            if number >= len(self.external):
                raise _error(
                    "external_constraint_reference_not_found",
                    "external_reference_not_found",
                    index,
                )
            reference = self.external[number]
            if not reference.resolved:
                raise _error(
                    "external_constraint_reference_broken",
                    reference.broken_reason or "broken_external_reference",
                    index,
                )
            if not sketch_external_geometry.reference_is_controlled_normal(reference):
                raise _error(
                    "external_constraint_reference_broken",
                    "stale_external_reference",
                    index,
                )
            external_geometry = reference.geometry
            if external_geometry is None or isinstance(
                external_geometry, UnsupportedSketchGeometry
            ):
                raise _error(
                    "external_constraint_geometry_type_unsupported",
                    "unsupported_external_geometry",
                    index,
                )
            resolved = _ResolvedGeometry(-3 - number, "external", number, external_geometry)
        if isinstance(resolved.geometry, UnsupportedSketchGeometry):
            raise _error(
                "external_constraint_geometry_type_unsupported",
                "unsupported_geometry_type",
                index,
            )
        self.resolved.append(resolved)
        return resolved

    def point(self, operand: SketchReferenceConstraintPointInput, index: int) -> _ResolvedPoint:
        geometry = self.geometry(operand.geometry, index)
        allowed: set[SketchPointPosition]
        if isinstance(geometry.geometry, SketchLineGeometry):
            allowed = {SketchPointPosition.START, SketchPointPosition.END}
        elif isinstance(geometry.geometry, SketchArcGeometry):
            allowed = {
                SketchPointPosition.START,
                SketchPointPosition.END,
                SketchPointPosition.CENTER,
            }
        elif isinstance(geometry.geometry, SketchCircleGeometry):
            allowed = {SketchPointPosition.CENTER}
        elif isinstance(geometry.geometry, SketchPointGeometry):
            allowed = {SketchPointPosition.POINT}
        else:
            allowed = set()
        if operand.position not in allowed:
            raise _error(
                "external_constraint_point_position_unsupported",
                "unsupported_point_position",
                index,
            )
        return _ResolvedPoint(geometry, _POINT_POSITIONS[operand.position])


def add_sketch_reference_constraints(
    document_name: str,
    sketch_name: str,
    constraints: tuple[SketchReferenceConstraintInput, ...],
) -> SketchReferenceConstraintAdditionResult:
    """Preflight the full batch, add it once, recompute, and verify atomically."""
    import FreeCAD as App  # type: ignore[import-not-found]
    import FreeCADGui as Gui  # type: ignore[import-not-found]
    import Part  # type: ignore[import-not-found]
    import Sketcher  # type: ignore[import-not-found]

    document, sketch = sketch_external_geometry.find_document_and_sketch(
        App,
        document_name,
        sketch_name,
    )
    references = sketch_external_geometry.enumerate_external_geometry(document, sketch, Part)
    internal = sketch_inspection._inspect_geometry(sketch, Part)
    specs = tuple(
        _prepare_constraint(item, index, internal, references)
        for index, item in enumerate(constraints)
    )
    _reject_duplicates(specs, tuple(sketch.Constraints))
    _reject_deterministic_redundancies(document, sketch, specs, internal, references)

    snapshot = sketch_external_geometry._mutation_snapshot(
        document,
        sketch,
        references,
        Part,
        App,
        Gui,
    )
    caller_owned = sketch_constraint_creation._pending_transaction(document)
    try:
        sketch_external_geometry._require_owned_history(snapshot, caller_owned)
    except Exception as exc:
        raise _error(
            "external_constraint_combination_unsupported", "undo_mode_disabled", None
        ) from exc

    original_count = sketch_constraint_creation._constraint_count(sketch)
    owned_transaction = False
    mutation_applied = False
    previous_active_document: str | None = None
    active_document_switched = False
    added: list[int] = []

    if not caller_owned:
        try:
            previous_active_document, active_document_switched = (
                sketch_rectangle_creation._activate_target_document(App, document_name)
            )
        except Exception as exc:
            raise _error(
                "external_constraint_solver_conflict",
                "target_document_activation_failed",
                None,
            ) from exc
        try:
            document.openTransaction(ADD_SKETCH_REFERENCE_CONSTRAINTS_TRANSACTION_NAME)
            owned_transaction = True
        except Exception as exc:
            if active_document_switched:
                try:
                    sketch_rectangle_creation._restore_active_document(
                        App,
                        previous_active_document,
                    )
                except Exception as restore_exc:
                    raise _error(
                        "external_constraint_solver_conflict",
                        "active_document_restore_failed",
                        None,
                    ) from restore_exc
            raise _error(
                "external_constraint_solver_conflict",
                "transaction_open_failed",
                None,
            ) from exc

    try:
        for index, spec in enumerate(specs):
            native = Sketcher.Constraint(spec.native_type, *spec.constructor_args)
            assigned = sketch.addConstraint(native)
            mutation_applied = True
            expected = original_count + index
            if (
                isinstance(assigned, bool)
                or not isinstance(assigned, Integral)
                or int(assigned) != expected
            ):
                raise _error("external_constraint_solver_conflict", "invalid_assigned_index", index)
            added.append(int(assigned))

        recompute_result = document.recompute()
        if recompute_result is False:
            raise _error("external_constraint_solver_conflict", "recompute_failed", None)
        if sketch_constraint_creation._constraint_count(sketch) != original_count + len(specs):
            raise _error("external_constraint_solver_conflict", "constraint_count_mismatch", None)

        after_references = sketch_external_geometry.enumerate_external_geometry(
            document,
            sketch,
            Part,
        )
        _verify_external_preservation(references, after_references, tuple(added), specs)
        inspected = sketch_inspection.get_sketch(document_name, sketch_name)
        _verify_solver(inspected.solver)
        _verify_native_constraints(tuple(sketch.Constraints), original_count, specs)
        if active_document_switched:
            try:
                sketch_rectangle_creation._restore_active_document(
                    App,
                    previous_active_document,
                )
            except Exception as exc:
                raise _error(
                    "external_constraint_solver_conflict",
                    "active_document_restore_failed",
                    None,
                ) from exc
            active_document_switched = False
        _verify_context(snapshot, document, sketch, App, Gui)

        if owned_transaction:
            document.commitTransaction()
            owned_transaction = False
            _verify_owned_history(snapshot.base.history, document)

        dependencies = sketch_dependencies.get_sketch_dependencies(document_name, sketch_name)
        summary = document_operations._summarize_document(
            document,
            document_operations._active_document_name(App),
            Gui,
        )
        internal_indices = sorted(
            {
                resolved.public_index
                for spec in specs
                for resolved in _resolved_operands(spec.item, internal, references)
                if resolved.kind == "internal"
            }
        )
        external_numbers = sorted(
            {
                resolved.public_index
                for spec in specs
                for resolved in _resolved_operands(spec.item, internal, references)
                if resolved.kind == "external"
            }
        )
        return SketchReferenceConstraintAdditionResult(
            document_name=document_name,
            sketch_name=sketch_name,
            added_indices=tuple(added),
            added_constraints=tuple(
                SketchReferenceConstraintSummary(index, spec.item)
                for index, spec in zip(added, specs, strict=True)
            ),
            external_reference_numbers=tuple(external_numbers),
            internal_geometry_indices=tuple(internal_indices),
            sketch=inspected,
            dependencies=dependencies,
            document=summary,
        )
    except SketchReferenceConstraintRollbackError:
        raise
    except Exception as exc:
        if mutation_applied or owned_transaction:
            try:
                _rollback(
                    document,
                    sketch,
                    snapshot,
                    owned_transaction,
                    caller_owned,
                    Part,
                    App,
                    Gui,
                    previous_active_document,
                    active_document_switched,
                )
                active_document_switched = False
            except SketchReferenceConstraintRollbackError as rollback_exc:
                raise rollback_exc from exc
        if isinstance(exc, SketchReferenceConstraintError):
            raise
        raise _error(
            "external_constraint_solver_conflict", "unexpected_native_failure", None
        ) from exc


def _prepare_constraint(
    item: SketchReferenceConstraintInput,
    index: int,
    internal: tuple[SketchGeometry, ...],
    external: tuple[ExternalGeometryReferenceData, ...],
) -> _NativeSpec:
    resolver = _Resolver(internal, external)
    value = cast(Any, item)
    variant = item.type
    mode = _mode(item)
    native_type = _native_type(variant)
    fields: tuple[int, int, int, int, int, int] = (_UNUSED, 0, _UNUSED, 0, _UNUSED, 0)
    constructor: tuple[int | float, ...]
    numeric_value = 0.0
    commutative = False
    symmetry_about: str | None = None

    if variant in {"horizontal", "vertical"}:
        geometry = resolver.geometry(value.geometry, index)
        _require_geometry_type(geometry, {"line_segment"}, index)
        fields = (geometry.native_id, 0, _UNUSED, 0, _UNUSED, 0)
        constructor = (geometry.native_id,)
    elif variant in {"horizontal_points", "vertical_points", "coincident"}:
        if variant == "coincident":
            first_point = _coincident_operand(value.first, resolver, index)
            second_point = _coincident_operand(value.second, resolver, index)
        else:
            first_point = resolver.point(value.first, index).native
            second_point = resolver.point(value.second, index).native
        if first_point == second_point:
            raise _error("external_constraint_duplicate", "identical_point_references", index)
        fields = (*first_point, *second_point, _UNUSED, 0)
        constructor = (*first_point, *second_point)
        commutative = True
    elif variant in {"parallel", "perpendicular", "equal", "tangent"}:
        first_geometry = resolver.geometry(value.first, index)
        second_geometry = resolver.geometry(value.second, index)
        if first_geometry.native_id == second_geometry.native_id:
            raise _error("external_constraint_duplicate", "identical_geometry_references", index)
        if variant in {"parallel", "perpendicular"}:
            _require_geometry_type(first_geometry, {"line_segment"}, index)
            _require_geometry_type(second_geometry, {"line_segment"}, index)
        fields = (first_geometry.native_id, 0, second_geometry.native_id, 0, _UNUSED, 0)
        constructor = (first_geometry.native_id, second_geometry.native_id)
        commutative = True
    elif variant == "point_on_object":
        first_is_point = isinstance(value.first, SketchReferenceConstraintPointInput)
        point = resolver.point(value.first if first_is_point else value.second, index)
        target_operand = value.second if first_is_point else value.first
        target_id: int
        if isinstance(target_operand, SketchHorizontalAxisReferenceInput):
            target_id = -1
            target_type = "axis"
        elif isinstance(target_operand, SketchVerticalAxisReferenceInput):
            target_id = -2
            target_type = "axis"
        else:
            target = resolver.geometry(target_operand, index)
            target_id = target.native_id
            target_type = target.geometry_type
            _require_geometry_type(target, {"line_segment", "circle", "arc_of_circle"}, index)
        if point.geometry.native_id == target_id:
            raise _error(
                "external_constraint_operand_invalid", "point_on_object_self_target", index
            )
        fields = (*point.native, target_id, 0, _UNUSED, 0)
        constructor = (*point.native, target_id)
        if target_type == "axis":
            symmetry_about = "axis"
    elif variant == "symmetric":
        first_symmetric_point = resolver.point(value.first, index)
        second_symmetric_point = resolver.point(value.second, index)
        if first_symmetric_point.native == second_symmetric_point.native:
            raise _error("external_constraint_duplicate", "identical_symmetric_points", index)
        about = value.about
        if isinstance(about, SketchOriginReferenceInput):
            third = _ORIGIN
            symmetry_about = "origin"
            constructor = (*first_symmetric_point.native, *second_symmetric_point.native, *third)
        elif isinstance(about, SketchHorizontalAxisReferenceInput):
            third = (-1, 0)
            symmetry_about = "axis"
            constructor = (*first_symmetric_point.native, *second_symmetric_point.native, -1)
        elif isinstance(about, SketchVerticalAxisReferenceInput):
            third = (-2, 0)
            symmetry_about = "axis"
            constructor = (*first_symmetric_point.native, *second_symmetric_point.native, -2)
        elif isinstance(about, SketchReferenceConstraintPointInput):
            about_point = resolver.point(about, index)
            third = about_point.native
            symmetry_about = f"point_{about_point.geometry.kind}"
            constructor = (*first_symmetric_point.native, *second_symmetric_point.native, *third)
        else:
            about_geometry = resolver.geometry(about, index)
            _require_geometry_type(about_geometry, {"line_segment"}, index)
            third = (about_geometry.native_id, 0)
            symmetry_about = f"line_{about_geometry.kind}"
            constructor = (
                *first_symmetric_point.native,
                *second_symmetric_point.native,
                about_geometry.native_id,
            )
        if third in {first_symmetric_point.native, second_symmetric_point.native}:
            raise _error(
                "external_constraint_operand_invalid", "degenerate_symmetry_reference", index
            )
        fields = (*first_symmetric_point.native, *second_symmetric_point.native, *third)
        commutative = True
    elif variant == "distance" and mode == "line_length":
        geometry = resolver.geometry(value.geometry, index)
        _require_geometry_type(geometry, {"line_segment"}, index)
        numeric_value = float(value.value)
        fields = (geometry.native_id, 0, _UNUSED, 0, _UNUSED, 0)
        constructor = (geometry.native_id, numeric_value)
    elif variant == "distance" and mode == "point_to_origin":
        point = resolver.point(value.point, index)
        numeric_value = float(value.value)
        fields = (*point.native, *_ORIGIN, _UNUSED, 0)
        constructor = (*point.native, *_ORIGIN, numeric_value)
    elif variant in {"distance", "distance_x", "distance_y"} and mode == "between_points":
        first_distance_point = resolver.point(value.first, index)
        second_distance_point = resolver.point(value.second, index)
        if first_distance_point.native == second_distance_point.native:
            raise _error("external_constraint_duplicate", "identical_point_references", index)
        numeric_value = float(value.value)
        fields = (*first_distance_point.native, *second_distance_point.native, _UNUSED, 0)
        constructor = (*first_distance_point.native, *second_distance_point.native, numeric_value)
        commutative = variant == "distance"
    elif variant in {"distance_x", "distance_y"} and mode == "point_to_origin":
        point = resolver.point(value.point, index)
        numeric_value = float(value.value)
        fields = (*point.native, _UNUSED, 0, _UNUSED, 0)
        constructor = (*point.native, numeric_value)
    elif variant in {"radius", "diameter"}:
        geometry = resolver.geometry(value.geometry, index)
        _require_geometry_type(geometry, {"circle", "arc_of_circle"}, index)
        numeric_value = float(value.value)
        fields = (geometry.native_id, 0, _UNUSED, 0, _UNUSED, 0)
        constructor = (geometry.native_id, numeric_value)
    elif variant == "angle" and mode == "line_angle":
        geometry = resolver.geometry(value.geometry, index)
        _require_geometry_type(geometry, {"line_segment"}, index)
        numeric_value = math.radians(float(value.value_degrees))
        fields = (geometry.native_id, 0, _UNUSED, 0, _UNUSED, 0)
        constructor = (geometry.native_id, numeric_value)
    elif variant == "angle" and mode == "between_lines":
        first_angle_line = resolver.geometry(value.first, index)
        second_angle_line = resolver.geometry(value.second, index)
        if first_angle_line.native_id == second_angle_line.native_id:
            raise _error("external_constraint_duplicate", "identical_geometry_references", index)
        _require_geometry_type(first_angle_line, {"line_segment"}, index)
        _require_geometry_type(second_angle_line, {"line_segment"}, index)
        numeric_value = math.radians(float(value.value_degrees))
        fields = (first_angle_line.native_id, 0, second_angle_line.native_id, 0, _UNUSED, 0)
        constructor = (first_angle_line.native_id, second_angle_line.native_id, numeric_value)
    else:
        raise _error(
            "external_constraint_combination_unsupported", "unsupported_operand_role", index
        )

    geometry_types = tuple(operand.geometry_type for operand in resolver.resolved)
    kinds = tuple(operand.kind for operand in resolver.resolved)
    decision = decide_reference_constraint_capability(
        variant=variant,
        mode=mode,
        operand_kinds=kinds,
        geometry_types=geometry_types,
        symmetry_about=symmetry_about,
    )
    if not decision.supported:
        code = (
            "external_constraint_read_only"
            if decision.reason in {"external_only_constraint", "driving_external_geometry"}
            else "external_constraint_combination_unsupported"
        )
        raise _error(code, decision.reason, index)

    alternate: tuple[tuple[int, int, int, int, int, int], ...] = ()
    key_fields = fields
    if commutative:
        alternate_fields = (fields[2], fields[3], fields[0], fields[1], fields[4], fields[5])
        alternate = (alternate_fields,)
        key_fields = min(fields, alternate_fields)
    semantic_key = (native_type, mode, key_fields, round(numeric_value, 12))
    return _NativeSpec(
        item,
        native_type,
        constructor,
        fields,
        numeric_value,
        semantic_key,
        alternate,
    )


def _resolved_operands(
    item: SketchReferenceConstraintInput,
    internal: tuple[SketchGeometry, ...],
    external: tuple[ExternalGeometryReferenceData, ...],
) -> tuple[_ResolvedGeometry, ...]:
    resolver = _Resolver(internal, external)

    def visit(value: Any) -> None:
        if isinstance(
            value, (InternalSketchGeometryReferenceInput, ExternalSketchGeometryReferenceInput)
        ):
            resolver.geometry(value, 0)
        elif isinstance(value, SketchReferenceConstraintPointInput):
            resolver.geometry(value.geometry, 0)
        elif hasattr(value, "model_fields"):
            for field_name in value.__class__.model_fields:
                visit(getattr(value, field_name))

    visit(item)
    unique: dict[tuple[str, int], _ResolvedGeometry] = {}
    for resolved in resolver.resolved:
        unique[(resolved.kind, resolved.public_index)] = resolved
    return tuple(unique.values())


def _mode(item: SketchReferenceConstraintInput) -> str:
    explicit = getattr(item, "mode", None)
    if isinstance(explicit, str):
        return explicit
    return {
        "horizontal": "whole_geometry",
        "vertical": "whole_geometry",
        "horizontal_points": "point/point",
        "vertical_points": "point/point",
        "parallel": "geometry/geometry",
        "perpendicular": "geometry/geometry",
        "equal": "geometry/geometry",
        "coincident": "point/point",
        "point_on_object": "point/object",
        "symmetric": "points/about",
        "tangent": "geometry/geometry",
        "radius": "whole_geometry",
        "diameter": "whole_geometry",
    }[item.type]


def _native_type(variant: str) -> str:
    return {
        "horizontal": "Horizontal",
        "horizontal_points": "Horizontal",
        "vertical": "Vertical",
        "vertical_points": "Vertical",
        "parallel": "Parallel",
        "perpendicular": "Perpendicular",
        "equal": "Equal",
        "coincident": "Coincident",
        "point_on_object": "PointOnObject",
        "symmetric": "Symmetric",
        "tangent": "Tangent",
        "distance": "Distance",
        "distance_x": "DistanceX",
        "distance_y": "DistanceY",
        "radius": "Radius",
        "diameter": "Diameter",
        "angle": "Angle",
    }[variant]


def _coincident_operand(value: Any, resolver: _Resolver, index: int) -> tuple[int, int]:
    if isinstance(value, SketchOriginReferenceInput):
        return _ORIGIN
    return resolver.point(value, index).native


def _require_geometry_type(
    geometry: _ResolvedGeometry,
    allowed: set[str],
    index: int,
) -> None:
    if geometry.geometry_type not in allowed:
        raise _error(
            "external_constraint_geometry_type_unsupported",
            "unsupported_geometry_pair",
            index,
        )


def _reject_duplicates(specs: tuple[_NativeSpec, ...], existing: tuple[Any, ...]) -> None:
    seen: set[tuple[object, ...]] = set()
    for index, spec in enumerate(specs):
        if spec.semantic_key in seen:
            raise _error("external_constraint_duplicate", "duplicate_constraint", index)
        seen.add(spec.semantic_key)
        if any(_native_matches(item, spec) for item in existing):
            raise _error("external_constraint_duplicate", "duplicate_constraint", index)


def _reject_deterministic_redundancies(
    document: Any,
    sketch: Any,
    specs: tuple[_NativeSpec, ...],
    internal: tuple[SketchGeometry, ...],
    external: tuple[ExternalGeometryReferenceData, ...],
) -> None:
    solver = sketch_inspection._inspect_solver(sketch)
    fully_constrained = solver.available and solver.fresh and solver.fully_constrained is True
    for index, spec in enumerate(specs):
        variant = spec.item.type
        redundant = False
        if variant in {"parallel", "perpendicular"}:
            first_orientation = _fixed_line_orientation(
                document,
                sketch,
                spec.fields[0],
                external,
            )
            second_orientation = _fixed_line_orientation(
                document,
                sketch,
                spec.fields[2],
                external,
            )
            if first_orientation is not None and second_orientation is not None:
                redundant = (variant == "parallel") is (first_orientation == second_orientation)
        if not redundant and fully_constrained:
            redundant = _relation_is_currently_satisfied(spec, internal, external)
        if redundant:
            raise _error("external_constraint_duplicate", "redundant_constraint", index)


def _fixed_line_orientation(
    document: Any,
    target_sketch: Any,
    native_id: int,
    external: tuple[ExternalGeometryReferenceData, ...],
) -> str | None:
    if native_id >= 0:
        return _line_orientation_constraint(target_sketch, native_id)
    if native_id > -3:
        return None
    number = -3 - native_id
    if number < 0 or number >= len(external):
        return None
    source = external[number].source
    if source is None or source.get("type") != "sketch_geometry":
        return None
    sketch_name = source.get("sketch_name")
    geometry_index = source.get("geometry_index")
    if not isinstance(sketch_name, str) or type(geometry_index) is not int:
        return None
    try:
        source_sketch = document.getObject(sketch_name)
    except Exception:
        return None
    if source_sketch is None:
        return None
    return _line_orientation_constraint(source_sketch, geometry_index)


def _line_orientation_constraint(sketch: Any, geometry_index: int) -> str | None:
    try:
        constraints = tuple(sketch.Constraints)
    except Exception:
        return None
    for constraint in constraints:
        try:
            constraint_type = str(constraint.Type)
            first = int(constraint.First)
            active = bool(constraint.IsActive)
            virtual = bool(constraint.InVirtualSpace)
        except Exception:
            continue
        if first == geometry_index and active and not virtual:
            if constraint_type == "Horizontal":
                return "horizontal"
            if constraint_type == "Vertical":
                return "vertical"
    return None


def _relation_is_currently_satisfied(
    spec: _NativeSpec,
    internal: tuple[SketchGeometry, ...],
    external: tuple[ExternalGeometryReferenceData, ...],
) -> bool:
    variant = spec.item.type
    first = _geometry_from_native_id(spec.fields[0], internal, external)
    second = _geometry_from_native_id(spec.fields[2], internal, external)
    if variant in {"parallel", "perpendicular"}:
        if not isinstance(first, SketchLineGeometry) or not isinstance(second, SketchLineGeometry):
            return False
        first_direction = _line_direction(first)
        second_direction = _line_direction(second)
        if variant == "parallel":
            return math.isclose(
                _cross(first_direction, second_direction),
                0.0,
                rel_tol=0.0,
                abs_tol=_REDUNDANCY_TOLERANCE,
            )
        return math.isclose(
            _dot(first_direction, second_direction),
            0.0,
            rel_tol=0.0,
            abs_tol=_REDUNDANCY_TOLERANCE,
        )
    if variant == "coincident":
        first_point = _geometry_point(first, spec.fields[1])
        second_point = _geometry_point(second, spec.fields[3])
        return _same_point(first_point, second_point)
    if variant == "point_on_object":
        point = _geometry_point(first, spec.fields[1])
        return _point_on_target(point, second, spec.fields[2])
    if variant == "equal":
        return _same_geometry_measure(first, second)
    if variant == "tangent":
        return _geometries_tangent(first, second)
    return False


def _geometry_from_native_id(
    native_id: int,
    internal: tuple[SketchGeometry, ...],
    external: tuple[ExternalGeometryReferenceData, ...],
) -> SketchGeometry | None:
    if native_id >= 0:
        return internal[native_id] if native_id < len(internal) else None
    if native_id > -3:
        return None
    number = -3 - native_id
    if number < 0 or number >= len(external):
        return None
    return external[number].geometry


def _line_direction(line: SketchLineGeometry) -> tuple[float, float]:
    return line.end.x - line.start.x, line.end.y - line.start.y


def _dot(first: tuple[float, float], second: tuple[float, float]) -> float:
    return first[0] * second[0] + first[1] * second[1]


def _cross(first: tuple[float, float], second: tuple[float, float]) -> float:
    return first[0] * second[1] - first[1] * second[0]


def _geometry_point(geometry: SketchGeometry | None, position: int) -> tuple[float, float] | None:
    if isinstance(geometry, SketchLineGeometry):
        point = geometry.start if position == 1 else geometry.end if position == 2 else None
    elif isinstance(geometry, (SketchCircleGeometry, SketchArcGeometry)):
        if position == 1 and isinstance(geometry, SketchArcGeometry):
            point = geometry.start
        elif position == 2 and isinstance(geometry, SketchArcGeometry):
            point = geometry.end
        else:
            point = geometry.center if position == 3 else None
    elif isinstance(geometry, SketchPointGeometry):
        point = geometry.point if position == 1 else None
    else:
        point = None
    return None if point is None else (point.x, point.y)


def _same_point(
    first: tuple[float, float] | None,
    second: tuple[float, float] | None,
) -> bool:
    if first is None or second is None:
        return False
    return math.dist(first, second) <= _REDUNDANCY_TOLERANCE


def _point_on_target(
    point: tuple[float, float] | None,
    target: SketchGeometry | None,
    native_target_id: int,
) -> bool:
    if point is None:
        return False
    if native_target_id == -1:
        return math.isclose(point[1], 0.0, rel_tol=0.0, abs_tol=_REDUNDANCY_TOLERANCE)
    if native_target_id == -2:
        return math.isclose(point[0], 0.0, rel_tol=0.0, abs_tol=_REDUNDANCY_TOLERANCE)
    if isinstance(target, SketchLineGeometry):
        direction = _line_direction(target)
        offset = (point[0] - target.start.x, point[1] - target.start.y)
        return math.isclose(
            _cross(direction, offset),
            0.0,
            rel_tol=0.0,
            abs_tol=_REDUNDANCY_TOLERANCE,
        )
    if isinstance(target, SketchCircleGeometry):
        return math.isclose(
            math.dist(point, (target.center.x, target.center.y)),
            target.radius,
            rel_tol=0.0,
            abs_tol=_REDUNDANCY_TOLERANCE,
        )
    return False


def _same_geometry_measure(
    first: SketchGeometry | None,
    second: SketchGeometry | None,
) -> bool:
    if isinstance(first, SketchLineGeometry) and isinstance(second, SketchLineGeometry):
        return math.isclose(
            math.hypot(*_line_direction(first)),
            math.hypot(*_line_direction(second)),
            rel_tol=0.0,
            abs_tol=_REDUNDANCY_TOLERANCE,
        )
    if isinstance(first, (SketchCircleGeometry, SketchArcGeometry)) and isinstance(
        second, (SketchCircleGeometry, SketchArcGeometry)
    ):
        return math.isclose(
            first.radius,
            second.radius,
            rel_tol=0.0,
            abs_tol=_REDUNDANCY_TOLERANCE,
        )
    return False


def _geometries_tangent(
    first: SketchGeometry | None,
    second: SketchGeometry | None,
) -> bool:
    if isinstance(first, SketchLineGeometry) and isinstance(second, SketchCircleGeometry):
        return _line_circle_tangent(first, second)
    if isinstance(second, SketchLineGeometry) and isinstance(first, SketchCircleGeometry):
        return _line_circle_tangent(second, first)
    if isinstance(first, SketchCircleGeometry) and isinstance(second, SketchCircleGeometry):
        center_distance = math.dist(
            (first.center.x, first.center.y),
            (second.center.x, second.center.y),
        )
        return any(
            math.isclose(
                center_distance,
                expected,
                rel_tol=0.0,
                abs_tol=_REDUNDANCY_TOLERANCE,
            )
            for expected in (first.radius + second.radius, abs(first.radius - second.radius))
        )
    return False


def _line_circle_tangent(
    line: SketchLineGeometry,
    circle: SketchCircleGeometry,
) -> bool:
    direction = _line_direction(line)
    length = math.hypot(*direction)
    if length <= _REDUNDANCY_TOLERANCE:
        return False
    offset = (circle.center.x - line.start.x, circle.center.y - line.start.y)
    distance = abs(_cross(direction, offset)) / length
    return math.isclose(
        distance,
        circle.radius,
        rel_tol=0.0,
        abs_tol=_REDUNDANCY_TOLERANCE,
    )


def _native_matches(item: Any, spec: _NativeSpec) -> bool:
    try:
        fields = tuple(
            int(getattr(item, name))
            for name in ("First", "FirstPos", "Second", "SecondPos", "Third", "ThirdPos")
        )
        native_type = str(item.Type)
        value = float(item.Value)
    except Exception:
        return False
    return (
        native_type == spec.native_type
        and fields in (spec.fields, *spec.alternate_fields)
        and math.isclose(value, spec.value, rel_tol=0.0, abs_tol=1e-12)
    )


def _verify_native_constraints(
    actual: tuple[Any, ...],
    original_count: int,
    specs: tuple[_NativeSpec, ...],
) -> None:
    if len(actual) != original_count + len(specs):
        raise _error("external_constraint_solver_conflict", "constraint_count_mismatch", None)
    for offset, spec in enumerate(specs):
        if not _native_matches(actual[original_count + offset], spec):
            raise _error("external_constraint_solver_conflict", "native_readback_mismatch", offset)


def _verify_solver(solver: Any) -> None:
    if not solver.available or not solver.fresh:
        raise _error("external_constraint_solver_conflict", "solver_state_unavailable", None)
    for field in (
        "conflicting_constraint_indices",
        "redundant_constraint_indices",
        "partially_redundant_constraint_indices",
        "malformed_constraint_indices",
    ):
        value = getattr(solver, field)
        if value:
            raise _error("external_constraint_solver_conflict", field, None)


def _verify_external_preservation(
    before: tuple[ExternalGeometryReferenceData, ...],
    after: tuple[ExternalGeometryReferenceData, ...],
    added: tuple[int, ...],
    specs: tuple[_NativeSpec, ...],
) -> None:
    if len(before) != len(after):
        raise _error("external_constraint_solver_conflict", "external_mapping_changed", None)
    expected_users: dict[int, set[int]] = {}
    for constraint_index, spec in zip(added, specs, strict=True):
        for kind, public_index in _public_operand_identities(spec.item):
            if kind == "external":
                expected_users.setdefault(public_index, set()).add(constraint_index)
    for old, new in zip(before, after, strict=True):
        old_data = old.to_dict()
        new_data = new.to_dict()
        old_data.pop("used_by_constraint_indices", None)
        new_data.pop("used_by_constraint_indices", None)
        if old_data != new_data:
            raise _error("external_constraint_solver_conflict", "external_source_changed", None)
        expected = expected_users.get(new.external_reference_number, set())
        if expected and not expected.issubset(new.used_by_constraint_indices):
            raise _error(
                "external_constraint_solver_conflict", "dependency_readback_mismatch", None
            )


def _public_operand_identities(
    item: SketchReferenceConstraintInput,
) -> tuple[tuple[OperandKind, int], ...]:
    result: set[tuple[OperandKind, int]] = set()

    def visit(value: Any) -> None:
        if isinstance(value, InternalSketchGeometryReferenceInput):
            result.add(("internal", value.geometry_index))
        elif isinstance(value, ExternalSketchGeometryReferenceInput):
            result.add(("external", value.external_reference_number))
        elif isinstance(value, SketchReferenceConstraintPointInput):
            visit(value.geometry)
        elif hasattr(value, "model_fields"):
            for field_name in value.__class__.model_fields:
                visit(getattr(value, field_name))

    visit(item)
    return tuple(sorted(result))


def _verify_context(snapshot: Any, document: Any, sketch: Any, app: Any, gui: Any) -> None:
    context = sketch_constraint_creation._sketch_context_state(document, sketch)
    if context != snapshot.base.context:
        raise _error("external_constraint_solver_conflict", "sketch_context_changed", None)
    summary = document_operations._summarize_document(
        document,
        document_operations._active_document_name(app),
        gui,
    )
    before = snapshot.base.document_summary
    if (
        summary.name != before.name
        or summary.file_path != before.file_path
        or summary.object_count != before.object_count
        or summary.active is not before.active
    ):
        raise _error("external_constraint_solver_conflict", "document_context_changed", None)
    current_gui = sketch_external_geometry._gui_state(gui, str(document.Name))
    if sketch_external_geometry._gui_state_changed(snapshot.gui_state, current_gui):
        raise _error("external_constraint_solver_conflict", "gui_state_changed", None)


def _verify_owned_history(before: Any, document: Any) -> None:
    if before is None:
        return
    after = sketch_rectangle_creation._history_state(document)
    if after is None:
        raise _error("external_constraint_solver_conflict", "history_state_unreadable", None)
    appended_names = (ADD_SKETCH_REFERENCE_CONSTRAINTS_TRANSACTION_NAME, *before[3])
    grew = after[1] == before[1] + 1 and after[3] == appended_names
    capped = before[1] > 0 and after[1] == before[1] and after[3] == appended_names[: before[1]]
    if after[0] != before[0] or not (grew or capped) or after[2] != 0 or after[4] != ():
        raise _error("external_constraint_solver_conflict", "history_verification_failed", None)


def _rollback(
    document: Any,
    sketch: Any,
    snapshot: Any,
    owned_transaction: bool,
    caller_owned: bool,
    part: Any,
    app: Any,
    gui: Any,
    previous_active_document: str | None = None,
    active_document_switched: bool = False,
) -> None:
    try:
        try:
            # An owned transaction must be aborted before any compensating sketch
            # mutation. Deleting solver-invalid constraints first can turn the
            # otherwise empty abort into a caller-visible, zero-effect undo entry.
            # Caller-owned transactions cannot be aborted here and continue to use
            # the exact inverse path inside the caller's still-open transaction.
            rollback_owns_pending_transaction = owned_transaction
            if owned_transaction:
                try:
                    with history_activity(document, "rollback"):
                        document.abortTransaction()
                except Exception:
                    # The shared inverse path will retry the abort only when the
                    # native document still reports that transaction as pending.
                    rollback_owns_pending_transaction = (
                        sketch_constraint_creation._pending_transaction(document)
                    )
                else:
                    rollback_owns_pending_transaction = False

            sketch_constraint_creation._rollback_constraint_batch(
                document=document,
                sketch=sketch,
                original_constraint_count=len(snapshot.base.constraints),
                original_constraints=snapshot.base.constraints,
                original_geometry=snapshot.base.geometry,
                original_construction=snapshot.base.construction,
                original_geometry_signature=snapshot.base.geometry_signature,
                original_context=snapshot.base.context,
                part=part,
                owned_transaction=rollback_owns_pending_transaction,
                caller_owned_transaction=caller_owned,
            )
            if snapshot.base.solver.available and snapshot.base.solver.fresh:
                recompute_result = document.recompute()
                if recompute_result is False:
                    raise SketchReferenceConstraintRollbackError("rollback_recompute_failed")
        finally:
            if active_document_switched:
                sketch_rectangle_creation._restore_active_document(
                    app,
                    previous_active_document,
                )
        sketch_rectangle_creation._restore_document_modified(
            gui,
            snapshot.base.document_summary,
        )
        try:
            sketch_external_geometry._verify_rollback_state(
                document,
                sketch,
                snapshot,
                owned_transaction,
                caller_owned,
                part,
                app,
                gui,
            )
        except SketchExternalGeometryRollbackError as exc:
            if (
                exc.reason != "rollback_history_state_mismatch"
                or not owned_transaction
                or caller_owned
            ):
                raise
            _repair_zero_effect_owned_history(document, sketch, snapshot.base.history, app)
            sketch_rectangle_creation._restore_document_modified(
                gui,
                snapshot.base.document_summary,
            )
            sketch_external_geometry._verify_rollback_state(
                document,
                sketch,
                snapshot,
                owned_transaction,
                caller_owned,
                part,
                app,
                gui,
            )
    except Exception as exc:
        reason = getattr(exc, "reason", "rollback_verification_failed")
        raise SketchReferenceConstraintRollbackError(str(reason)) from exc


def _repair_zero_effect_owned_history(
    document: Any,
    sketch: Any,
    before: Any,
    app: Any,
) -> None:
    """Remove exactly one leaked owned undo record after semantic rollback."""
    if before is None or before[2] != 0 or before[4] != ():
        raise SketchReferenceConstraintRollbackError("rollback_history_state_mismatch")
    try:
        after_abort = sketch_rectangle_creation._history_state(document)
        pending = sketch_constraint_creation._pending_transaction(document)
    except Exception as exc:
        raise SketchReferenceConstraintRollbackError(
            "rollback_history_cleanup_state_unreadable"
        ) from exc
    expected_leak = (
        before[0],
        before[1] + 1,
        0,
        (ADD_SKETCH_REFERENCE_CONSTRAINTS_TRANSACTION_NAME, *before[3]),
        (),
    )
    if pending or after_abort != expected_leak:
        raise SketchReferenceConstraintRollbackError("rollback_history_state_mismatch")

    previous_active_document: str | None = None
    active_document_switched = False
    try:
        previous_active_document, active_document_switched = (
            sketch_rectangle_creation._activate_target_document(app, str(document.Name))
        )
        try:
            with history_activity(document, "rollback"):
                undo_result = document.undo()
            if undo_result is False:
                raise RuntimeError("native undo returned false")
            after_undo = sketch_rectangle_creation._history_state(document)
            expected_undo = (
                before[0],
                before[1],
                1,
                before[3],
                (ADD_SKETCH_REFERENCE_CONSTRAINTS_TRANSACTION_NAME,),
            )
            if after_undo != expected_undo:
                raise RuntimeError("failed transaction did not move to redo exactly")

            original_label = sketch.Label
            if not isinstance(original_label, str):
                raise RuntimeError("sketch label is unreadable")
            temporary_label = f"{original_label} [MCP rollback cleanup]"
            cleanup_open = False
            try:
                with history_activity(document, "rollback"):
                    document.openTransaction(_ROLLBACK_HISTORY_CLEANUP_TRANSACTION_NAME)
                    cleanup_open = True
                    sketch.Label = temporary_label
                    document.abortTransaction()
                    cleanup_open = False
            finally:
                if cleanup_open and sketch_constraint_creation._pending_transaction(document):
                    with history_activity(document, "rollback"):
                        document.abortTransaction()
            if sketch.Label != original_label:
                raise RuntimeError("cleanup transaction did not restore the sketch label")
            if sketch_rectangle_creation._history_state(document) != before:
                raise RuntimeError("cleanup transaction did not restore history")
        finally:
            if active_document_switched:
                sketch_rectangle_creation._restore_active_document(
                    app,
                    previous_active_document,
                )
    except SketchReferenceConstraintRollbackError:
        raise
    except Exception as exc:
        raise SketchReferenceConstraintRollbackError("rollback_history_cleanup_failed") from exc


def _error(code: str, reason: str, index: int | None) -> SketchReferenceConstraintError:
    return SketchReferenceConstraintError(code=code, reason=reason, index=index)


__all__ = ["add_sketch_reference_constraints"]
