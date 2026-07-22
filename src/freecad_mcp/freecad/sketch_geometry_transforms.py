"""Evidence-bounded copy-only sketch geometry transforms for Milestone 24."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Literal, cast

from freecad_mcp.exceptions import (
    SketchControlledMutationError,
    SketchControlledMutationRollbackError,
    SketchMutationIndexNotFoundError,
    SketchTopologyEditUnsafeError,
)
from freecad_mcp.freecad import (
    sketch_dependencies,
    sketch_removal,
    sketch_topology_editing,
)
from freecad_mcp.freecad.sketch_constraint_creation import (
    _constraint_state,
    _construction_state,
)
from freecad_mcp.freecad.sketch_topology import TOPOLOGY_TOLERANCE
from freecad_mcp.models import (
    SketchArcGeometry,
    SketchCircleGeometry,
    SketchGeometry,
    SketchGeometryTransformResult,
    SketchLineGeometry,
    SketchMirrorConstructionLineReferenceInput,
    SketchMirrorInternalPointReferenceInput,
    SketchMirrorReferenceInput,
    SketchPoint2D,
    SketchPoint2DInput,
    SketchPointGeometry,
    SketchTransformCreatedGeometry,
    SketchTransformGeometryMapping,
    SketchTransformInstance,
    UnsupportedSketchGeometry,
)
from freecad_mcp.transaction_names import (
    MIRROR_SKETCH_GEOMETRY_TRANSACTION_NAME,
    POLAR_ARRAY_SKETCH_GEOMETRY_TRANSACTION_NAME,
    RECTANGULAR_ARRAY_SKETCH_GEOMETRY_TRANSACTION_NAME,
    ROTATE_SKETCH_GEOMETRY_TRANSACTION_NAME,
    SCALE_SKETCH_GEOMETRY_TRANSACTION_NAME,
    TRANSLATE_SKETCH_GEOMETRY_TRANSACTION_NAME,
)

_PublicOperation = Literal[
    "mirror",
    "translate",
    "rotate",
    "scale",
    "rectangular_array",
    "polar_array",
]


@dataclass(frozen=True, slots=True)
class _AffineTransform:
    instance_index: int
    a: float
    b: float
    c: float
    d: float
    tx: float
    ty: float
    radius_scale: float
    orientation_reversed: bool
    parameters: dict[str, object]

    def point(self, value: SketchPoint2D) -> SketchPoint2D:
        return SketchPoint2D(
            x=self.a * value.x + self.b * value.y + self.tx,
            y=self.c * value.x + self.d * value.y + self.ty,
        )


def mirror_sketch_geometry(
    document_name: str,
    sketch_name: str,
    geometry_indices: tuple[int, ...],
    reference: SketchMirrorReferenceInput,
) -> SketchGeometryTransformResult:
    """Append mirror copies about one controlled sketch-local reference."""
    operation: _PublicOperation = "mirror"
    App, Gui, Part = _runtime_modules()
    document, sketch = sketch_removal._context(App, document_name, sketch_name)
    snapshot = sketch_removal._snapshot(document, sketch, Part, App, Gui, cast(Any, operation))
    sources = _preflight_selection(document, sketch, snapshot, geometry_indices, operation)
    transform, reference_details = _mirror_transform(snapshot, geometry_indices, reference)
    invariant = [
        source.index
        for source in sources
        if _geometry_overlap_equal(
            source,
            _transform_geometry(source, transform, source.index),
        )
    ]
    if invariant:
        raise _unsafe(
            operation,
            "ambiguous_overlapping_copy",
            geometry_indices[0],
            invariant_geometry_indices=invariant,
        )
    return _execute_copy(
        document,
        sketch,
        snapshot,
        sources,
        (transform,),
        operation,
        MIRROR_SKETCH_GEOMETRY_TRANSACTION_NAME,
        {"mirror_reference": reference_details},
        Part,
        App,
        Gui,
    )


def translate_sketch_geometry(
    document_name: str,
    sketch_name: str,
    geometry_indices: tuple[int, ...],
    displacement: SketchPoint2DInput,
) -> SketchGeometryTransformResult:
    """Append independent copies displaced by one finite sketch-local vector."""
    operation: _PublicOperation = "translate"
    App, Gui, Part = _runtime_modules()
    document, sketch = sketch_removal._context(App, document_name, sketch_name)
    snapshot = sketch_removal._snapshot(document, sketch, Part, App, Gui, cast(Any, operation))
    sources = _preflight_selection(document, sketch, snapshot, geometry_indices, operation)
    if math.hypot(displacement.x, displacement.y) <= TOPOLOGY_TOLERANCE:
        raise _unsafe(operation, "ambiguous_overlapping_copy", geometry_indices[0])
    transform = _translation(1, displacement.x, displacement.y)
    return _execute_copy(
        document,
        sketch,
        snapshot,
        sources,
        (transform,),
        operation,
        TRANSLATE_SKETCH_GEOMETRY_TRANSACTION_NAME,
        {"displacement": {"x": displacement.x, "y": displacement.y}},
        Part,
        App,
        Gui,
    )


def rotate_sketch_geometry(
    document_name: str,
    sketch_name: str,
    geometry_indices: tuple[int, ...],
    center: SketchPoint2DInput,
    angle_degrees: float,
) -> SketchGeometryTransformResult:
    """Append independent copies rotated by one signed degree angle."""
    operation: _PublicOperation = "rotate"
    App, Gui, Part = _runtime_modules()
    document, sketch = sketch_removal._context(App, document_name, sketch_name)
    snapshot = sketch_removal._snapshot(document, sketch, Part, App, Gui, cast(Any, operation))
    sources = _preflight_selection(document, sketch, snapshot, geometry_indices, operation)
    normalized = _normalized_signed_degrees(angle_degrees)
    if abs(normalized) <= math.degrees(TOPOLOGY_TOLERANCE):
        raise _unsafe(operation, "ambiguous_overlapping_copy", geometry_indices[0])
    transform = _rotation(1, center.x, center.y, normalized)
    invariant = _invariant_geometry_indices(sources, transform)
    if invariant:
        raise _unsafe(
            operation,
            "ambiguous_overlapping_copy",
            geometry_indices[0],
            invariant_geometry_indices=invariant,
        )
    return _execute_copy(
        document,
        sketch,
        snapshot,
        sources,
        (transform,),
        operation,
        ROTATE_SKETCH_GEOMETRY_TRANSACTION_NAME,
        {
            "center": {"x": center.x, "y": center.y},
            "angle_degrees": angle_degrees,
            "normalized_angle_degrees": normalized,
        },
        Part,
        App,
        Gui,
    )


def scale_sketch_geometry(
    document_name: str,
    sketch_name: str,
    geometry_indices: tuple[int, ...],
    center: SketchPoint2DInput,
    factor: float,
) -> SketchGeometryTransformResult:
    """Append independent copies uniformly scaled by one positive factor."""
    operation: _PublicOperation = "scale"
    App, Gui, Part = _runtime_modules()
    document, sketch = sketch_removal._context(App, document_name, sketch_name)
    snapshot = sketch_removal._snapshot(document, sketch, Part, App, Gui, cast(Any, operation))
    sources = _preflight_selection(document, sketch, snapshot, geometry_indices, operation)
    if abs(factor - 1.0) <= TOPOLOGY_TOLERANCE:
        raise _unsafe(operation, "ambiguous_overlapping_copy", geometry_indices[0])
    transform = _scaling(1, center.x, center.y, factor)
    invariant = [
        source.index
        for source in sources
        if _geometry_overlap_equal(
            source,
            _transform_geometry(source, transform, source.index),
        )
    ]
    if invariant:
        raise _unsafe(
            operation,
            "ambiguous_overlapping_copy",
            geometry_indices[0],
            invariant_geometry_indices=invariant,
        )
    return _execute_copy(
        document,
        sketch,
        snapshot,
        sources,
        (transform,),
        operation,
        SCALE_SKETCH_GEOMETRY_TRANSACTION_NAME,
        {"center": {"x": center.x, "y": center.y}, "factor": factor},
        Part,
        App,
        Gui,
    )


def rectangular_array_sketch_geometry(
    document_name: str,
    sketch_name: str,
    geometry_indices: tuple[int, ...],
    rows: int,
    columns: int,
    row_displacement: SketchPoint2DInput,
    column_displacement: SketchPoint2DInput,
) -> SketchGeometryTransformResult:
    """Append source-inclusive row-major rectangular-array copies."""
    operation: _PublicOperation = "rectangular_array"
    App, Gui, Part = _runtime_modules()
    document, sketch = sketch_removal._context(App, document_name, sketch_name)
    snapshot = sketch_removal._snapshot(document, sketch, Part, App, Gui, cast(Any, operation))
    sources = _preflight_selection(
        document,
        sketch,
        snapshot,
        geometry_indices,
        operation,
        require_mutation=rows * columns > 1,
    )
    details = {
        "rows": rows,
        "columns": columns,
        "source_included": True,
        "ordering": "row_major_then_selection_order",
        "row_displacement": {"x": row_displacement.x, "y": row_displacement.y},
        "column_displacement": {
            "x": column_displacement.x,
            "y": column_displacement.y,
        },
    }
    if rows == 1 and columns == 1:
        return _no_change_result(
            snapshot,
            geometry_indices,
            operation,
            RECTANGULAR_ARRAY_SKETCH_GEOMETRY_TRANSACTION_NAME,
            details,
        )
    if rows > 1 and math.hypot(row_displacement.x, row_displacement.y) <= TOPOLOGY_TOLERANCE:
        raise _unsafe(operation, "zero_row_displacement", geometry_indices[0])
    if columns > 1 and (
        math.hypot(column_displacement.x, column_displacement.y) <= TOPOLOGY_TOLERANCE
    ):
        raise _unsafe(operation, "zero_column_displacement", geometry_indices[0])
    transforms: list[_AffineTransform] = []
    offsets: list[tuple[float, float]] = [(0.0, 0.0)]
    for row in range(rows):
        for column in range(columns):
            instance = row * columns + column
            if instance == 0:
                continue
            dx = row * row_displacement.x + column * column_displacement.x
            dy = row * row_displacement.y + column * column_displacement.y
            if any(math.hypot(dx - x, dy - y) <= TOPOLOGY_TOLERANCE for x, y in offsets):
                raise _unsafe(
                    operation,
                    "duplicate_array_instance",
                    geometry_indices[0],
                    row=row,
                    column=column,
                )
            offsets.append((dx, dy))
            transform = _translation(instance, dx, dy)
            transform.parameters.update({"row": row, "column": column})
            transforms.append(transform)
    return _execute_copy(
        document,
        sketch,
        snapshot,
        sources,
        tuple(transforms),
        operation,
        RECTANGULAR_ARRAY_SKETCH_GEOMETRY_TRANSACTION_NAME,
        details,
        Part,
        App,
        Gui,
    )


def polar_array_sketch_geometry(
    document_name: str,
    sketch_name: str,
    geometry_indices: tuple[int, ...],
    center: SketchPoint2DInput,
    instance_count: int,
    step_angle_degrees: float,
) -> SketchGeometryTransformResult:
    """Append source-inclusive polar-array copies in ascending instance order."""
    operation: _PublicOperation = "polar_array"
    App, Gui, Part = _runtime_modules()
    document, sketch = sketch_removal._context(App, document_name, sketch_name)
    snapshot = sketch_removal._snapshot(document, sketch, Part, App, Gui, cast(Any, operation))
    sources = _preflight_selection(document, sketch, snapshot, geometry_indices, operation)
    seen = [0.0]
    transforms: list[_AffineTransform] = []
    for instance in range(1, instance_count):
        angle = _normalized_positive_degrees(instance * step_angle_degrees)
        if any(
            _angle_distance_degrees(angle, prior) <= math.degrees(TOPOLOGY_TOLERANCE)
            for prior in seen
        ):
            raise _unsafe(
                operation,
                "duplicate_array_instance",
                geometry_indices[0],
                instance_index=instance,
            )
        seen.append(angle)
        transform = _rotation(instance, center.x, center.y, instance * step_angle_degrees)
        invariant = _invariant_geometry_indices(sources, transform)
        if invariant:
            raise _unsafe(
                operation,
                "ambiguous_overlapping_copy",
                geometry_indices[0],
                instance_index=instance,
                invariant_geometry_indices=invariant,
            )
        transforms.append(transform)
    return _execute_copy(
        document,
        sketch,
        snapshot,
        sources,
        tuple(transforms),
        operation,
        POLAR_ARRAY_SKETCH_GEOMETRY_TRANSACTION_NAME,
        {
            "center": {"x": center.x, "y": center.y},
            "instance_count": instance_count,
            "step_angle_degrees": step_angle_degrees,
            "source_included": True,
            "ordering": "ascending_instance_then_selection_order",
            "full_circle_duplicate_policy": "refuse",
        },
        Part,
        App,
        Gui,
    )


def _runtime_modules() -> tuple[Any, Any, Any]:
    import FreeCAD as App  # type: ignore[import-not-found]
    import FreeCADGui as Gui  # type: ignore[import-not-found]
    import Part  # type: ignore[import-not-found]

    return App, Gui, Part


def _preflight_selection(
    document: Any,
    sketch: Any,
    snapshot: Any,
    geometry_indices: tuple[int, ...],
    operation: _PublicOperation,
    *,
    require_mutation: bool = True,
) -> tuple[SketchGeometry, ...]:
    sources: list[SketchGeometry] = []
    for index in geometry_indices:
        if index >= snapshot.sketch.geometry_count:
            raise SketchMutationIndexNotFoundError(selection="geometry", index=index)
        source = snapshot.sketch.geometry[index]
        if isinstance(source, UnsupportedSketchGeometry):
            raise _unsafe(
                operation,
                "unsupported_geometry_type",
                index,
                geometry_type=source.freecad_type,
                supported_geometry_types=["line_segment", "point", "circle", "arc_of_circle"],
            )
        sources.append(source)
    sketch_topology_editing._require_healthy_solver_data(
        snapshot.sketch.solver,
        cast(Any, operation),
        geometry_indices[0],
    )
    if not require_mutation:
        return tuple(sources)
    dependencies = sketch_removal._geometry_dependencies(
        snapshot.base.constraints, geometry_indices
    )
    if dependencies:
        constraint_indices = tuple(
            sorted(
                {
                    cast(int, index)
                    for item in dependencies
                    for index in cast(list[object], item["dependent_constraint_indices"])
                }
            )
        )
        constraints = tuple(snapshot.sketch.constraints[index] for index in constraint_indices)
        reason = "dependent_constraints"
        if any(getattr(item, "expression", None) for item in constraints):
            reason = "expression_bound_constraint"
        elif any(getattr(item, "name", None) for item in constraints):
            reason = "named_constraint"
        raise _unsafe(
            operation,
            reason,
            geometry_indices[0],
            affected_constraint_indices=list(constraint_indices),
            affected_constraints=[item.to_dict() for item in constraints],
            dependencies=list(dependencies),
        )
    try:
        relationship = sketch_dependencies.get_sketch_dependencies(
            str(document.Name),
            str(sketch.Name),
        )
    except Exception as exc:
        raise SketchControlledMutationError(
            operation=operation,
            phase="preflight",
            reason="dependency_inspection_failed",
        ) from exc
    if relationship.broken_references or relationship.cross_document_references:
        raise _unsafe(
            operation,
            "broken_or_cross_document_dependency",
            geometry_indices[0],
            broken_references=[dict(item) for item in relationship.broken_references],
            cross_document_references=[
                dict(item) for item in relationship.cross_document_references
            ],
        )
    if relationship.downstream_consumers:
        raise _unsafe(
            operation,
            "downstream_consumer_topology_unproven",
            geometry_indices[0],
            downstream_consumers=[dict(item) for item in relationship.downstream_consumers],
        )
    return tuple(sources)


def _mirror_transform(
    snapshot: Any,
    selection: tuple[int, ...],
    reference: SketchMirrorReferenceInput,
) -> tuple[_AffineTransform, dict[str, object]]:
    if reference.kind == "horizontal_axis":
        return _affine(1, 1.0, 0.0, 0.0, -1.0, 0.0, 0.0, True, {}), {"kind": reference.kind}
    if reference.kind == "vertical_axis":
        return _affine(1, -1.0, 0.0, 0.0, 1.0, 0.0, 0.0, True, {}), {"kind": reference.kind}
    if reference.kind == "origin":
        return _affine(1, -1.0, 0.0, 0.0, -1.0, 0.0, 0.0, False, {}), {"kind": reference.kind}
    index = reference.geometry_index
    if index >= snapshot.sketch.geometry_count:
        raise SketchMutationIndexNotFoundError(selection="geometry", index=index)
    if index in selection:
        raise _unsafe(
            "mirror", "reference_geometry_selected", selection[0], reference_geometry_index=index
        )
    item = snapshot.sketch.geometry[index]
    if isinstance(reference, SketchMirrorConstructionLineReferenceInput):
        if not isinstance(item, SketchLineGeometry) or not item.construction:
            raise _unsafe(
                "mirror",
                "construction_line_reference_required",
                selection[0],
                reference_geometry_index=index,
            )
        dx = item.end.x - item.start.x
        dy = item.end.y - item.start.y
        length = math.hypot(dx, dy)
        if length <= TOPOLOGY_TOLERANCE:
            raise _unsafe(
                "mirror", "degenerate_reference", selection[0], reference_geometry_index=index
            )
        ux, uy = dx / length, dy / length
        a = 2.0 * ux * ux - 1.0
        b = 2.0 * ux * uy
        c = b
        d = 2.0 * uy * uy - 1.0
        tx = item.start.x - a * item.start.x - b * item.start.y
        ty = item.start.y - c * item.start.x - d * item.start.y
        return (
            _affine(1, a, b, c, d, tx, ty, True, {}),
            {"kind": reference.kind, "geometry_index": index},
        )
    assert isinstance(reference, SketchMirrorInternalPointReferenceInput)
    if not isinstance(item, SketchPointGeometry):
        raise _unsafe(
            "mirror",
            "internal_point_reference_required",
            selection[0],
            reference_geometry_index=index,
        )
    return (
        _affine(1, -1.0, 0.0, 0.0, -1.0, 2.0 * item.point.x, 2.0 * item.point.y, False, {}),
        {"kind": reference.kind, "geometry_index": index},
    )


def _translation(instance: int, dx: float, dy: float) -> _AffineTransform:
    return _affine(
        instance,
        1.0,
        0.0,
        0.0,
        1.0,
        dx,
        dy,
        False,
        {"displacement": {"x": dx, "y": dy}},
    )


def _rotation(instance: int, center_x: float, center_y: float, degrees: float) -> _AffineTransform:
    radians = math.radians(degrees)
    cosine, sine = math.cos(radians), math.sin(radians)
    return _affine(
        instance,
        cosine,
        -sine,
        sine,
        cosine,
        center_x - cosine * center_x + sine * center_y,
        center_y - sine * center_x - cosine * center_y,
        False,
        {"angle_degrees": degrees},
    )


def _scaling(instance: int, center_x: float, center_y: float, factor: float) -> _AffineTransform:
    return _affine(
        instance,
        factor,
        0.0,
        0.0,
        factor,
        center_x * (1.0 - factor),
        center_y * (1.0 - factor),
        False,
        {"factor": factor},
        radius_scale=factor,
    )


def _affine(
    instance: int,
    a: float,
    b: float,
    c: float,
    d: float,
    tx: float,
    ty: float,
    reversed_orientation: bool,
    parameters: dict[str, object],
    *,
    radius_scale: float = 1.0,
) -> _AffineTransform:
    return _AffineTransform(
        instance,
        a,
        b,
        c,
        d,
        tx,
        ty,
        radius_scale,
        reversed_orientation,
        parameters,
    )


def _execute_copy(
    document: Any,
    sketch: Any,
    snapshot: Any,
    sources: tuple[SketchGeometry, ...],
    transforms: tuple[_AffineTransform, ...],
    operation: _PublicOperation,
    transaction_name: str,
    details: dict[str, object],
    part: Any,
    app: Any,
    gui: Any,
) -> SketchGeometryTransformResult:
    expected: list[tuple[int, int, _AffineTransform, SketchGeometry]] = []
    next_index = snapshot.sketch.geometry_count
    for transform in transforms:
        for source in sources:
            expected.append(
                (
                    source.index,
                    transform.instance_index,
                    transform,
                    _transform_geometry(source, transform, next_index),
                )
            )
            next_index += 1
    caller_owned, owned, histories, active = sketch_topology_editing._begin(
        document,
        snapshot,
        app,
        transaction_name,
        cast(Any, operation),
    )
    try:
        for _source_index, _instance, _transform, geometry in expected:
            assigned = sketch.addGeometry(
                _native_geometry(geometry, part, app), geometry.construction
            )
            if (
                isinstance(assigned, bool)
                or not isinstance(assigned, int)
                or assigned != geometry.index
            ):
                raise _error(operation, "mutation", "invalid_assigned_geometry_index")
        sketch_removal._recompute(document, cast(Any, operation))
        inspected, summary = sketch_removal._controlled_readback(
            str(document.Name),
            str(sketch.Name),
            cast(Any, operation),
        )
        created = _verify_copy(sketch, snapshot, inspected, expected, operation)
        active = sketch_topology_editing._restore_active(app, active, cast(Any, operation))
        sketch_removal._verify_common(
            document,
            sketch,
            snapshot,
            part,
            app,
            gui,
            cast(Any, operation),
        )
        sketch_topology_editing._verify_dependency_health(
            document,
            sketch,
            cast(Any, operation),
        )
        summary = sketch_topology_editing._final_document_summary(
            document,
            cast(Any, operation),
        )
        result = _result(
            snapshot,
            inspected,
            summary,
            tuple(source.index for source in sources),
            operation,
            transaction_name,
            caller_owned,
            created,
            transforms,
            details,
        )
        sketch_topology_editing._finish(
            document,
            snapshot,
            app,
            histories,
            caller_owned,
            owned,
            transaction_name,
            cast(Any, operation),
        )
        return result
    except SketchControlledMutationRollbackError:
        raise
    except Exception as exc:
        sketch_topology_editing._fail(
            document,
            sketch,
            snapshot,
            part,
            app,
            gui,
            owned,
            caller_owned,
            active,
            cast(Any, operation),
            exc,
        )


def _verify_copy(
    sketch: Any,
    snapshot: Any,
    inspected: Any,
    expected: list[tuple[int, int, _AffineTransform, SketchGeometry]],
    operation: _PublicOperation,
) -> tuple[SketchTransformCreatedGeometry, ...]:
    if inspected.geometry_count != snapshot.sketch.geometry_count + len(expected):
        raise _error(operation, "verification", "geometry_count_mismatch")
    if inspected.constraint_count != snapshot.sketch.constraint_count:
        raise _error(operation, "verification", "constraint_count_changed")
    if _constraint_state(sketch) != snapshot.base.constraints:
        raise _error(operation, "verification", "constraint_state_changed")
    expected_construction = snapshot.base.construction + tuple(
        geometry.construction for _source, _instance, _transform, geometry in expected
    )
    if _construction_state(sketch, inspected.geometry_count) != expected_construction:
        raise _error(operation, "verification", "construction_state_changed")
    for index, before in enumerate(snapshot.sketch.geometry):
        if not _geometry_equal(before, inspected.geometry[index]):
            raise _error(operation, "verification", "unrelated_geometry_changed")
    created: list[SketchTransformCreatedGeometry] = []
    for source_index, instance, transform, geometry in expected:
        actual = inspected.geometry[geometry.index]
        if not _geometry_equal(geometry, actual):
            raise _error(operation, "verification", "created_geometry_mismatch")
        orientation: Literal["preserved", "reversed", "not_applicable"] = "preserved"
        if isinstance(actual, (SketchPointGeometry, SketchCircleGeometry)):
            orientation = "not_applicable"
        elif isinstance(actual, SketchArcGeometry) and transform.orientation_reversed:
            orientation = "reversed"
        created.append(
            SketchTransformCreatedGeometry(
                index=geometry.index,
                source_geometry_index=source_index,
                instance_index=instance,
                orientation_relationship=orientation,
                geometry=actual,
            )
        )
    sketch_topology_editing._verify_post_solver(
        inspected.solver,
        cast(Any, operation),
        cast(Any, operation),
        expected[0][0],
    )
    return tuple(created)


def _result(
    snapshot: Any,
    inspected: Any,
    summary: Any,
    selection: tuple[int, ...],
    operation: _PublicOperation,
    transaction_name: str,
    caller_owned: bool,
    created: tuple[SketchTransformCreatedGeometry, ...],
    transforms: tuple[_AffineTransform, ...],
    details: dict[str, object],
) -> SketchGeometryTransformResult:
    copied_by_source = {
        index: tuple(item.index for item in created if item.source_geometry_index == index)
        for index in selection
    }
    instances = tuple(
        SketchTransformInstance(
            instance_index=transform.instance_index,
            source_geometry_indices=selection,
            created_geometry_indices=tuple(
                item.index for item in created if item.instance_index == transform.instance_index
            ),
            parameters=transform.parameters,
        )
        for transform in transforms
    )
    details = {
        **details,
        "profile_impact": {
            "before": snapshot.profile,
            "after": sketch_removal._profile_summary(inspected, summary),
        },
    }
    return SketchGeometryTransformResult(
        operation=operation,
        selected_geometry_indices=selection,
        changed=True,
        transaction_name=transaction_name,
        transaction_committed=not caller_owned,
        geometry_mappings=tuple(
            SketchTransformGeometryMapping(
                original_index=index,
                resulting_indices=(index, *copied_by_source.get(index, ())),
                copied_indices=copied_by_source.get(index, ()),
            )
            for index in range(snapshot.sketch.geometry_count)
        ),
        constraint_mappings=sketch_topology_editing._identity_constraint_mappings(snapshot),
        created_geometry=created,
        instances=instances,
        details=details,
        sketch=inspected,
        document=summary,
    )


def _no_change_result(
    snapshot: Any,
    selection: tuple[int, ...],
    operation: _PublicOperation,
    transaction_name: str,
    details: dict[str, object],
) -> SketchGeometryTransformResult:
    return SketchGeometryTransformResult(
        operation=operation,
        selected_geometry_indices=selection,
        changed=False,
        transaction_name=transaction_name,
        transaction_committed=False,
        geometry_mappings=tuple(
            SketchTransformGeometryMapping(
                original_index=index,
                resulting_indices=(index,),
                copied_indices=(),
            )
            for index in range(snapshot.sketch.geometry_count)
        ),
        constraint_mappings=sketch_topology_editing._identity_constraint_mappings(snapshot),
        created_geometry=(),
        instances=(),
        details={
            **details,
            "profile_impact": {"before": snapshot.profile, "after": snapshot.profile},
        },
        sketch=snapshot.sketch,
        document=snapshot.base.document_summary,
    )


def _transform_geometry(
    source: SketchGeometry,
    transform: _AffineTransform,
    index: int,
) -> SketchGeometry:
    if isinstance(source, SketchLineGeometry):
        return SketchLineGeometry(
            index=index,
            construction=source.construction,
            start=transform.point(source.start),
            end=transform.point(source.end),
        )
    if isinstance(source, SketchPointGeometry):
        return SketchPointGeometry(
            index=index,
            construction=source.construction,
            point=transform.point(source.point),
        )
    if isinstance(source, SketchCircleGeometry):
        return SketchCircleGeometry(
            index=index,
            construction=source.construction,
            center=transform.point(source.center),
            radius=source.radius * transform.radius_scale,
        )
    assert isinstance(source, SketchArcGeometry)
    center = transform.point(source.center)
    mapped_start = transform.point(source.start)
    mapped_end = transform.point(source.end)
    start, end = (
        (mapped_end, mapped_start) if transform.orientation_reversed else (mapped_start, mapped_end)
    )
    start_angle = math.degrees(math.atan2(start.y - center.y, start.x - center.x))
    end_angle = math.degrees(math.atan2(end.y - center.y, end.x - center.x))
    while end_angle <= start_angle:
        end_angle += 360.0
    return SketchArcGeometry(
        index=index,
        construction=source.construction,
        center=center,
        radius=source.radius * transform.radius_scale,
        start=start,
        end=end,
        start_angle_degrees=start_angle,
        end_angle_degrees=end_angle,
    )


def _native_geometry(geometry: SketchGeometry, part: Any, app: Any) -> Any:
    if isinstance(geometry, SketchLineGeometry):
        return part.LineSegment(
            app.Vector(geometry.start.x, geometry.start.y, 0.0),
            app.Vector(geometry.end.x, geometry.end.y, 0.0),
        )
    if isinstance(geometry, SketchPointGeometry):
        return part.Point(app.Vector(geometry.point.x, geometry.point.y, 0.0))
    assert isinstance(geometry, (SketchCircleGeometry, SketchArcGeometry))
    circle = part.Circle(
        app.Vector(geometry.center.x, geometry.center.y, 0.0),
        app.Vector(0.0, 0.0, 1.0),
        geometry.radius,
    )
    if isinstance(geometry, SketchCircleGeometry):
        return circle
    assert isinstance(geometry, SketchArcGeometry)
    return part.ArcOfCircle(
        circle,
        math.radians(geometry.start_angle_degrees),
        math.radians(geometry.end_angle_degrees),
    )


def _geometry_equal(first: SketchGeometry, second: SketchGeometry) -> bool:
    if type(first) is not type(second) or first.index != second.index:
        return False
    if first.construction is not second.construction:
        return False
    if isinstance(first, SketchLineGeometry) and isinstance(second, SketchLineGeometry):
        return _point_equal(first.start, second.start) and _point_equal(first.end, second.end)
    if isinstance(first, SketchPointGeometry) and isinstance(second, SketchPointGeometry):
        return _point_equal(first.point, second.point)
    if isinstance(first, SketchCircleGeometry) and isinstance(second, SketchCircleGeometry):
        return _point_equal(first.center, second.center) and _number_equal(
            first.radius, second.radius
        )
    if isinstance(first, SketchArcGeometry) and isinstance(second, SketchArcGeometry):
        return (
            _point_equal(first.center, second.center)
            and _point_equal(first.start, second.start)
            and _point_equal(first.end, second.end)
            and _number_equal(first.radius, second.radius)
        )
    return False


def _geometry_overlap_equal(first: SketchGeometry, second: SketchGeometry) -> bool:
    """Compare exact curve loci while tolerating reversed line orientation."""
    if _geometry_equal(first, second):
        return True
    return (
        isinstance(first, SketchLineGeometry)
        and isinstance(second, SketchLineGeometry)
        and first.index == second.index
        and first.construction is second.construction
        and _point_equal(first.start, second.end)
        and _point_equal(first.end, second.start)
    )


def _invariant_geometry_indices(
    sources: tuple[SketchGeometry, ...],
    transform: _AffineTransform,
) -> list[int]:
    return [
        source.index
        for source in sources
        if _geometry_overlap_equal(
            source,
            _transform_geometry(source, transform, source.index),
        )
    ]


def _point_equal(first: SketchPoint2D, second: SketchPoint2D) -> bool:
    return math.hypot(first.x - second.x, first.y - second.y) <= TOPOLOGY_TOLERANCE


def _number_equal(first: float, second: float) -> bool:
    return math.isclose(first, second, rel_tol=0.0, abs_tol=TOPOLOGY_TOLERANCE)


def _normalized_signed_degrees(value: float) -> float:
    result = math.fmod(value, 360.0)
    if result <= -180.0:
        result += 360.0
    elif result > 180.0:
        result -= 360.0
    return result


def _normalized_positive_degrees(value: float) -> float:
    result = math.fmod(value, 360.0)
    return result + 360.0 if result < 0.0 else result


def _angle_distance_degrees(first: float, second: float) -> float:
    delta = abs(first - second) % 360.0
    return min(delta, 360.0 - delta)


def _unsafe(
    operation: _PublicOperation,
    reason: str,
    geometry_index: int,
    **details: object,
) -> SketchTopologyEditUnsafeError:
    return SketchTopologyEditUnsafeError(
        operation=operation,
        code="sketch_geometry_transform_unsafe",
        reason=reason,
        geometry_index=geometry_index,
        details=details,
    )


def _error(operation: _PublicOperation, phase: str, reason: str) -> SketchControlledMutationError:
    return SketchControlledMutationError(operation=operation, phase=phase, reason=reason)


__all__ = [
    "mirror_sketch_geometry",
    "polar_array_sketch_geometry",
    "rectangular_array_sketch_geometry",
    "rotate_sketch_geometry",
    "scale_sketch_geometry",
    "translate_sketch_geometry",
]
