"""Read-only inspection of Sketcher sketches through controlled public models."""

from __future__ import annotations

import math
import re
from numbers import Integral, Real
from typing import Any

from freecad_mcp.constraint_expression_language import (
    ConstraintExpressionError,
    parse_constraint_expression,
)
from freecad_mcp.exceptions import (
    DocumentNotFoundError,
    ObjectNotFoundError,
    SketchConstraintMalformedError,
    SketchGeometryMalformedError,
    SketchInspectionError,
    SketchTypeMismatchError,
)
from freecad_mcp.freecad.object_inspection import (
    _extract_placement,
    _extract_placement_value,
    _object_visibility,
)
from freecad_mcp.models import (
    OriginPlane,
    SketchArcGeometry,
    SketchArcOfEllipseGeometry,
    SketchArcOfHyperbolaGeometry,
    SketchArcOfParabolaGeometry,
    SketchAttachmentData,
    SketchBSplineGeometry,
    SketchCircleGeometry,
    SketchConstraint,
    SketchConstraintData,
    SketchConstraintReference,
    SketchConstraintValue,
    SketchEllipseGeometry,
    SketchGeometry,
    SketchInspectionResult,
    SketchLineGeometry,
    SketchPoint2D,
    SketchPointGeometry,
    SketchSolverData,
    UnsupportedSketchConstraint,
    UnsupportedSketchGeometry,
)

_SUPPORTED_CONSTRAINTS = {
    "Coincident": "coincident",
    "PointOnObject": "point_on_object",
    "Symmetric": "symmetric",
    "Tangent": "tangent",
    "Horizontal": "horizontal",
    "Vertical": "vertical",
    "Parallel": "parallel",
    "Perpendicular": "perpendicular",
    "Equal": "equal",
    "Distance": "distance",
    "DistanceX": "distance_x",
    "DistanceY": "distance_y",
    "Radius": "radius",
    "Diameter": "diameter",
    "Angle": "angle",
}
_DIMENSIONAL_CONSTRAINTS = {
    "Distance",
    "DistanceX",
    "DistanceY",
    "Radius",
    "Diameter",
    "Angle",
}
_REFERENCE_COUNTS = {
    "Coincident": {2},
    "PointOnObject": {2},
    "Symmetric": {3},
    "Tangent": {2},
    "Horizontal": {1, 2},
    "Vertical": {1, 2},
    "Parallel": {2},
    "Perpendicular": {2},
    "Equal": {2},
    "Distance": {1, 2},
    "DistanceX": {1, 2},
    "DistanceY": {1, 2},
    "Radius": {1},
    "Diameter": {1},
    "Angle": {1, 2},
}
_POSITION_NAMES = {0: "edge", 1: "start", 2: "end", 3: "center"}
_AXIS_NAMES = {-1: "x", -2: "y"}
_UNUSED_GEOMETRY_REFERENCE = -2000


def get_sketch(document_name: str, sketch_name: str) -> SketchInspectionResult:
    """Return a controlled snapshot without solving, recomputing, or saving."""
    import FreeCAD as App  # type: ignore[import-not-found]
    import Part  # type: ignore[import-not-found]

    try:
        document = App.listDocuments().get(document_name)
        if document is None:
            raise DocumentNotFoundError(document_name)

        sketch = document.getObject(sketch_name)
        if sketch is None:
            raise ObjectNotFoundError(sketch_name)

        try:
            is_sketch = bool(sketch.isDerivedFrom("Sketcher::SketchObject"))
        except Exception as exc:
            raise SketchInspectionError("sketch_type_check_failed") from exc
        if not is_sketch:
            raise SketchTypeMismatchError(sketch_name)

        body = _owning_body(sketch)
        geometry = _inspect_geometry(sketch, Part)
        external_geometry = _inspect_external_geometry(sketch, Part)
        constraints = _inspect_constraints(sketch, geometry, external_geometry)
        map_mode, attachment = _inspect_attachment(sketch, body)

        return SketchInspectionResult(
            name=str(sketch.Name),
            label=str(sketch.Label),
            body_name=None if body is None else str(body.Name),
            visibility=_object_visibility(sketch),
            map_mode=map_mode,
            attachment=attachment,
            placement=_extract_placement(sketch),
            geometry_count=len(geometry),
            external_geometry_count=_external_geometry_count(sketch),
            constraint_count=len(constraints),
            geometry=geometry,
            constraints=constraints,
            solver=_inspect_solver(sketch),
        )
    except (
        DocumentNotFoundError,
        ObjectNotFoundError,
        SketchConstraintMalformedError,
        SketchGeometryMalformedError,
        SketchInspectionError,
        SketchTypeMismatchError,
    ):
        raise
    except Exception as exc:
        raise SketchInspectionError("freecad_api_failure") from exc


def _owning_body(sketch: Any) -> Any | None:
    try:
        parent = sketch.getParentGeoFeatureGroup()
    except Exception:
        return None
    if parent is None or str(getattr(parent, "TypeId", "")) != "PartDesign::Body":
        return None
    return parent


def _inspect_geometry(sketch: Any, part: Any) -> tuple[SketchGeometry, ...]:
    try:
        raw_geometry = tuple(sketch.Geometry)
        reported_count = _required_integer(sketch.GeometryCount)
    except SketchGeometryMalformedError:
        raise
    except Exception as exc:
        raise SketchGeometryMalformedError(
            index=None, reason="geometry_collection_unreadable"
        ) from exc
    if reported_count != len(raw_geometry):
        raise SketchGeometryMalformedError(index=None, reason="geometry_count_mismatch")

    result: list[SketchGeometry] = []
    for index, item in enumerate(raw_geometry):
        try:
            construction = bool(sketch.getConstruction(index))
        except Exception as exc:
            raise SketchGeometryMalformedError(
                index=index, reason="construction_flag_unreadable"
            ) from exc

        try:
            result.append(_inspect_geometry_item(item, index, construction, part))
        except SketchGeometryMalformedError:
            raise
        except Exception as exc:
            raise SketchGeometryMalformedError(
                index=index, reason="geometry_attributes_unreadable"
            ) from exc
    return tuple(result)


def _inspect_geometry_item(
    item: Any,
    index: int,
    construction: bool,
    part: Any,
) -> SketchGeometry:
    """Convert one native geometry item into the existing controlled union."""
    if _part_instance(item, part, "LineSegment"):
        return SketchLineGeometry(
            index=index,
            construction=construction,
            start=_point_from_vector(item.StartPoint, index),
            end=_point_from_vector(item.EndPoint, index),
        )
    if _part_instance(item, part, "Circle"):
        return SketchCircleGeometry(
            index=index,
            construction=construction,
            center=_point_from_vector(item.Center, index),
            radius=_radius(item.Radius, index),
        )
    if _part_instance(item, part, "ArcOfCircle"):
        return SketchArcGeometry(
            index=index,
            construction=construction,
            center=_point_from_vector(item.Center, index),
            radius=_radius(item.Radius, index),
            start=_point_from_vector(item.StartPoint, index),
            end=_point_from_vector(item.EndPoint, index),
            start_angle_degrees=math.degrees(_geometry_number(item.FirstParameter, index)),
            end_angle_degrees=math.degrees(_geometry_number(item.LastParameter, index)),
        )
    if _part_instance(item, part, "Point"):
        return SketchPointGeometry(
            index=index,
            construction=construction,
            point=SketchPoint2D(
                x=_geometry_number(item.X, index),
                y=_geometry_number(item.Y, index),
            ),
        )
    if _part_instance(item, part, "ArcOfEllipse"):
        try:
            return SketchArcOfEllipseGeometry(
                index=index,
                construction=construction,
                center=SketchPoint2D(
                    x=_geometry_number(item.Center.x, index),
                    y=_geometry_number(item.Center.y, index),
                ),
                major_radius=_radius(item.MajorRadius, index),
                minor_radius=_radius(item.MinorRadius, index),
                angle_xu_degrees=math.degrees(_geometry_number(item.AngleXU, index)) % 180.0,
                start=SketchPoint2D(
                    x=_geometry_number(item.StartPoint.x, index),
                    y=_geometry_number(item.StartPoint.y, index),
                ),
                end=SketchPoint2D(
                    x=_geometry_number(item.EndPoint.x, index),
                    y=_geometry_number(item.EndPoint.y, index),
                ),
                start_parameter_degrees=math.degrees(_geometry_number(item.FirstParameter, index)),
                end_parameter_degrees=math.degrees(_geometry_number(item.LastParameter, index)),
            )
        except Exception as exc:
            raise SketchGeometryMalformedError(
                index=index, reason="arc_of_ellipse_attributes_unreadable"
            ) from exc
    if _part_instance(item, part, "Ellipse"):
        try:
            return SketchEllipseGeometry(
                index=index,
                construction=construction,
                center=SketchPoint2D(
                    x=_geometry_number(item.Center.x, index),
                    y=_geometry_number(item.Center.y, index),
                ),
                major_radius=_radius(item.MajorRadius, index),
                minor_radius=_radius(item.MinorRadius, index),
                angle_xu_degrees=math.degrees(_geometry_number(item.AngleXU, index)) % 180.0,
            )
        except Exception as exc:
            raise SketchGeometryMalformedError(
                index=index, reason="ellipse_attributes_unreadable"
            ) from exc
    if _part_instance(item, part, "ArcOfHyperbola"):
        try:
            angle_xu_rad = _geometry_number(item.AngleXU, index)
            major_axis_angle_degrees = math.degrees(angle_xu_rad) % 360.0
            if hasattr(item.Hyperbola, "Focus"):
                focus_vec = item.Hyperbola.Focus
                focus = SketchPoint2D(
                    x=_geometry_number(focus_vec.x, index),
                    y=_geometry_number(focus_vec.y, index),
                )
            else:
                major_radius = _geometry_number(item.MajorRadius, index)
                minor_radius = _geometry_number(item.MinorRadius, index)
                focal_dist = math.sqrt(major_radius**2 + minor_radius**2)
                focus = SketchPoint2D(
                    x=_geometry_number(item.Center.x, index)
                    + _geometry_number(item.XAxis.x, index) * focal_dist,
                    y=_geometry_number(item.Center.y, index)
                    + _geometry_number(item.XAxis.y, index) * focal_dist,
                )
            return SketchArcOfHyperbolaGeometry(
                index=index,
                construction=construction,
                center=SketchPoint2D(
                    x=_geometry_number(item.Center.x, index),
                    y=_geometry_number(item.Center.y, index),
                ),
                major_radius=_radius(item.MajorRadius, index),
                minor_radius=_radius(item.MinorRadius, index),
                major_axis_angle_degrees=major_axis_angle_degrees,
                focus=focus,
                start=SketchPoint2D(
                    x=_geometry_number(item.StartPoint.x, index),
                    y=_geometry_number(item.StartPoint.y, index),
                ),
                end=SketchPoint2D(
                    x=_geometry_number(item.EndPoint.x, index),
                    y=_geometry_number(item.EndPoint.y, index),
                ),
                start_parameter=_geometry_number(item.FirstParameter, index),
                end_parameter=_geometry_number(item.LastParameter, index),
            )
        except Exception as exc:
            raise SketchGeometryMalformedError(
                index=index, reason="arc_of_hyperbola_attributes_unreadable"
            ) from exc
    if _part_instance(item, part, "ArcOfParabola"):
        try:
            center_x = _geometry_number(item.Center.x, index)
            center_y = _geometry_number(item.Center.y, index)
            focal = _geometry_number(item.Focal, index)
            axis_x = _geometry_number(item.XAxis.x, index)
            axis_y = _geometry_number(item.XAxis.y, index)
            focus = SketchPoint2D(
                x=center_x + axis_x * focal,
                y=center_y + axis_y * focal,
            )
            return SketchArcOfParabolaGeometry(
                index=index,
                construction=construction,
                vertex=SketchPoint2D(x=center_x, y=center_y),
                focus=focus,
                start=SketchPoint2D(
                    x=_geometry_number(item.StartPoint.x, index),
                    y=_geometry_number(item.StartPoint.y, index),
                ),
                end=SketchPoint2D(
                    x=_geometry_number(item.EndPoint.x, index),
                    y=_geometry_number(item.EndPoint.y, index),
                ),
                start_parameter=_geometry_number(item.FirstParameter, index),
                end_parameter=_geometry_number(item.LastParameter, index),
            )
        except Exception as exc:
            raise SketchGeometryMalformedError(
                index=index, reason="arc_of_parabola_attributes_unreadable"
            ) from exc
    if _part_instance(item, part, "BSplineCurve"):
        try:
            poles = tuple(
                SketchPoint2D(
                    x=_geometry_number(vector.x, index),
                    y=_geometry_number(vector.y, index),
                )
                for vector in item.getPoles()
            )
            raw_weights = list(item.getWeights())
            all_unit = all(abs(w - 1.0) < 1e-9 for w in raw_weights) if raw_weights else True
            weights = None if (all_unit or not item.isRational()) else tuple(raw_weights)
            return SketchBSplineGeometry(
                index=index,
                construction=construction,
                poles=poles,
                weights=weights,
                degree=int(item.Degree),
                periodic=bool(item.isPeriodic()),
                rational=bool(item.isRational()),
                closed=bool(item.isClosed()),
                knot_sequence=tuple(float(k) for k in item.KnotSequence),
                start=SketchPoint2D(
                    x=_geometry_number(item.StartPoint.x, index),
                    y=_geometry_number(item.StartPoint.y, index),
                ),
                end=SketchPoint2D(
                    x=_geometry_number(item.EndPoint.x, index),
                    y=_geometry_number(item.EndPoint.y, index),
                ),
            )
        except Exception as exc:
            raise SketchGeometryMalformedError(
                index=index, reason="b_spline_attributes_unreadable"
            ) from exc
    return UnsupportedSketchGeometry(
        index=index,
        construction=construction,
        freecad_type=_controlled_type_name(type(item).__name__),
    )


def _inspect_external_geometry(sketch: Any, part: Any) -> tuple[SketchGeometry, ...]:
    try:
        raw = tuple(sketch.ExternalGeo)[2:]
    except Exception as exc:
        raise SketchGeometryMalformedError(
            index=None,
            reason="external_geometry_collection_unreadable",
        ) from exc
    return tuple(_inspect_geometry_item(item, index, True, part) for index, item in enumerate(raw))


def _inspect_constraints(
    sketch: Any,
    geometry: tuple[SketchGeometry, ...],
    external_geometry: tuple[SketchGeometry, ...] = (),
) -> tuple[SketchConstraint, ...]:
    try:
        raw_constraints = tuple(sketch.Constraints)
        reported_count = _required_integer(sketch.ConstraintCount)
    except SketchConstraintMalformedError:
        raise
    except Exception as exc:
        raise SketchConstraintMalformedError(
            index=None, reason="constraint_collection_unreadable"
        ) from exc
    if reported_count != len(raw_constraints):
        raise SketchConstraintMalformedError(index=None, reason="constraint_count_mismatch")
    expressions = _constraint_expressions(sketch, raw_constraints)

    result: list[SketchConstraint] = []
    for index, item in enumerate(raw_constraints):
        freecad_type = _constraint_type(item, index)
        name = _constraint_name(item, index)
        active = _constraint_bool(item, "IsActive", index)
        virtual_space = _constraint_bool(item, "InVirtualSpace", index)
        expression, expression_supported = expressions.get(index, (None, None))

        if freecad_type not in _SUPPORTED_CONSTRAINTS:
            result.append(
                UnsupportedSketchConstraint(
                    index=index,
                    freecad_type=freecad_type,
                    name=name,
                    active=active,
                    virtual_space=virtual_space,
                    expression=expression,
                    expression_supported=expression_supported,
                )
            )
            continue

        references, unsupported_reference = _constraint_references(
            item,
            index,
            geometry,
            external_geometry,
        )
        if unsupported_reference:
            result.append(
                UnsupportedSketchConstraint(
                    index=index,
                    freecad_type=freecad_type,
                    name=name,
                    active=active,
                    virtual_space=virtual_space,
                    expression=expression,
                    expression_supported=expression_supported,
                )
            )
            continue
        if len(references) not in _REFERENCE_COUNTS[freecad_type]:
            raise SketchConstraintMalformedError(index=index, reason="invalid_reference_count")

        driving: bool | None = None
        value: SketchConstraintValue | None = None
        if freecad_type in _DIMENSIONAL_CONSTRAINTS:
            driving = _constraint_bool(item, "Driving", index)
            raw_value = _constraint_number(getattr(item, "Value", None), index)
            if freecad_type == "Angle":
                value = SketchConstraintValue(value=math.degrees(raw_value), unit="degree")
            else:
                value = SketchConstraintValue(value=raw_value, unit="millimeter")

        result.append(
            SketchConstraintData(
                index=index,
                type=_controlled_constraint_type(freecad_type, references),
                name=name,
                active=active,
                virtual_space=virtual_space,
                driving=driving,
                references=references,
                value=value,
                expression=expression,
                expression_supported=expression_supported,
            )
        )
    return tuple(result)


def _constraint_expressions(
    sketch: Any,
    constraints: tuple[Any, ...],
) -> dict[int, tuple[str | None, bool | None]]:
    """Map native constraint expression paths to controlled current indices."""
    try:
        entries = tuple(sketch.ExpressionEngine)
    except Exception as exc:
        raise SketchConstraintMalformedError(
            index=None, reason="constraint_expression_state_unreadable"
        ) from exc
    names: dict[str, int] = {}
    for index, constraint in enumerate(constraints):
        name = _constraint_name(constraint, index)
        if name is not None:
            names[name] = index
    result: dict[int, tuple[str | None, bool | None]] = {}
    for entry in entries:
        try:
            path, expression = entry
        except Exception as exc:
            raise SketchConstraintMalformedError(
                index=None, reason="constraint_expression_entry_unreadable"
            ) from exc
        if not isinstance(path, str) or not isinstance(expression, str):
            raise SketchConstraintMalformedError(
                index=None, reason="constraint_expression_entry_unreadable"
            )
        normalized = path.lstrip(".")
        numeric = re.fullmatch(r"Constraints\[(\d+)\]", normalized)
        named = re.fullmatch(r"Constraints\.([A-Za-z_][A-Za-z0-9_]*)", normalized)
        if numeric is not None:
            index = int(numeric.group(1))
        elif named is not None and named.group(1) in names:
            index = names[named.group(1)]
        else:
            continue
        if index < 0 or index >= len(constraints):
            continue
        if index in result:
            result[index] = (None, False)
            continue
        try:
            parsed = parse_constraint_expression(
                expression,
                allow_native_leading_dot=True,
            )
        except ConstraintExpressionError:
            result[index] = (None, False)
        else:
            result[index] = (parsed.canonical, True)
    return result


def _constraint_references(
    constraint: Any,
    constraint_index: int,
    geometry: tuple[SketchGeometry, ...],
    external_geometry: tuple[SketchGeometry, ...] = (),
) -> tuple[tuple[SketchConstraintReference, ...], bool]:
    tangent = _tangent_references(constraint, geometry, external_geometry)
    if tangent is not None:
        return tangent

    symmetric = _symmetric_references(
        constraint,
        constraint_index,
        geometry,
        external_geometry,
    )
    if symmetric is not None:
        return symmetric

    point_alignment = _point_alignment_references(
        constraint,
        constraint_index,
        geometry,
        external_geometry,
    )
    if point_alignment is not None:
        return point_alignment

    origin_coincidence = _coincident_origin_references(
        constraint,
        constraint_index,
        geometry,
        external_geometry,
    )
    if origin_coincidence is not None:
        return origin_coincidence

    point_on_object = _point_on_object_references(
        constraint,
        constraint_index,
        geometry,
        external_geometry,
    )
    if point_on_object is not None:
        return point_on_object

    origin_distance = _distance_to_origin_reference(
        constraint,
        constraint_index,
        geometry,
        external_geometry,
    )
    if origin_distance is not None:
        return origin_distance

    references: list[SketchConstraintReference] = []
    for geometry_field, position_field in (
        ("First", "FirstPos"),
        ("Second", "SecondPos"),
        ("Third", "ThirdPos"),
    ):
        try:
            geometry_index = _required_integer(getattr(constraint, geometry_field))
            position_index = _required_integer(getattr(constraint, position_field))
        except Exception as exc:
            raise SketchConstraintMalformedError(
                index=constraint_index, reason="reference_unreadable"
            ) from exc

        if geometry_index == _UNUSED_GEOMETRY_REFERENCE:
            continue
        if geometry_index in _AXIS_NAMES:
            if position_index != 0:
                return (), True
            references.append(
                SketchConstraintReference(
                    kind="axis",
                    axis=_AXIS_NAMES[geometry_index],
                    position="edge",
                )
            )
            continue
        if geometry_index < 0 and geometry_index > -3:
            return (), True
        reference = _whole_or_point_reference(
            geometry_index,
            position_index,
            constraint_index,
            geometry,
            external_geometry,
        )
        if reference is None:
            return (), True
        references.append(reference)
    return tuple(references), False


def _tangent_references(
    constraint: Any,
    geometry: tuple[SketchGeometry, ...],
    external_geometry: tuple[SketchGeometry, ...] = (),
) -> tuple[tuple[SketchConstraintReference, ...], bool] | None:
    try:
        if constraint.Type != "Tangent":
            return None
        first = _required_integer(constraint.First)
        first_position = _required_integer(constraint.FirstPos)
        second = _required_integer(constraint.Second)
        second_position = _required_integer(constraint.SecondPos)
        third = _required_integer(constraint.Third)
        third_position = _required_integer(constraint.ThirdPos)
    except Exception:
        return (), True

    if (
        first_position != 0
        or second_position != 0
        or third != _UNUSED_GEOMETRY_REFERENCE
        or third_position != 0
        or first == second
    ):
        return (), True

    supported = (SketchLineGeometry, SketchCircleGeometry, SketchArcGeometry)
    first_geometry = _geometry_for_native_reference(
        first,
        0,
        geometry,
        external_geometry,
    )
    second_geometry = _geometry_for_native_reference(
        second,
        0,
        geometry,
        external_geometry,
    )
    if first_geometry is None or second_geometry is None:
        return (), True
    if not isinstance(first_geometry, supported) or not isinstance(second_geometry, supported):
        return (), True
    if isinstance(first_geometry, SketchLineGeometry) and isinstance(
        second_geometry, SketchLineGeometry
    ):
        return (), True
    return (
        (
            _geometry_reference(first, "edge"),
            _geometry_reference(second, "edge"),
        ),
        False,
    )


def _controlled_constraint_type(
    freecad_type: str,
    references: tuple[SketchConstraintReference, ...],
) -> str:
    if freecad_type == "Horizontal" and len(references) == 2:
        return "horizontal_points"
    if freecad_type == "Vertical" and len(references) == 2:
        return "vertical_points"
    return _SUPPORTED_CONSTRAINTS[freecad_type]


def _symmetric_references(
    constraint: Any,
    constraint_index: int,
    geometry: tuple[SketchGeometry, ...],
    external_geometry: tuple[SketchGeometry, ...] = (),
) -> tuple[tuple[SketchConstraintReference, ...], bool] | None:
    try:
        if constraint.Type != "Symmetric":
            return None
        first = (_required_integer(constraint.First), _required_integer(constraint.FirstPos))
        second = (_required_integer(constraint.Second), _required_integer(constraint.SecondPos))
        third = (_required_integer(constraint.Third), _required_integer(constraint.ThirdPos))
    except Exception:
        return (), True

    try:
        first_reference = _geometry_point_reference(
            *first,
            constraint_index,
            geometry,
            external_geometry,
        )
        second_reference = _geometry_point_reference(
            *second,
            constraint_index,
            geometry,
            external_geometry,
        )
    except SketchConstraintMalformedError:
        return (), True
    if first_reference is None or second_reference is None or first == second:
        return (), True

    third_geometry, third_position = third
    about: SketchConstraintReference | None = None
    if third_position == 0:
        axis_references = {-1: "horizontal_axis", -2: "vertical_axis"}
        if third_geometry in axis_references:
            about = SketchConstraintReference(reference=axis_references[third_geometry])
        elif third_geometry >= 0 or third_geometry <= -3:
            about_geometry = _geometry_for_native_reference(
                third_geometry,
                0,
                geometry,
                external_geometry,
            )
            if not isinstance(about_geometry, SketchLineGeometry):
                return (), True
            if third_geometry in {first[0], second[0]}:
                return (), True
            about = _geometry_reference(third_geometry, "edge")
    elif third == (-1, 1):
        about = SketchConstraintReference(reference="origin")
    else:
        try:
            about = _geometry_point_reference(
                third_geometry,
                third_position,
                constraint_index,
                geometry,
                external_geometry,
            )
        except SketchConstraintMalformedError:
            return (), True
        if third in {first, second}:
            return (), True

    if about is None:
        return (), True
    return ((first_reference, second_reference, about), False)


def _coincident_origin_references(
    constraint: Any,
    constraint_index: int,
    geometry: tuple[SketchGeometry, ...],
    external_geometry: tuple[SketchGeometry, ...] = (),
) -> tuple[tuple[SketchConstraintReference, ...], bool] | None:
    try:
        if constraint.Type != "Coincident":
            return None
        raw_references = (
            (_required_integer(constraint.First), _required_integer(constraint.FirstPos)),
            (_required_integer(constraint.Second), _required_integer(constraint.SecondPos)),
        )
    except Exception as exc:
        raise SketchConstraintMalformedError(
            index=constraint_index,
            reason="reference_unreadable",
        ) from exc

    root_reference = (-1, 1)
    if root_reference not in raw_references:
        if any(geometry_index in _AXIS_NAMES for geometry_index, _ in raw_references):
            return (), True
        return None
    if raw_references[0] == root_reference and raw_references[1] == root_reference:
        return (), True

    references: list[SketchConstraintReference] = []
    for geometry_index, position_index in raw_references:
        if (geometry_index, position_index) == root_reference:
            references.append(SketchConstraintReference(reference="origin"))
            continue
        controlled = _geometry_point_reference(
            geometry_index,
            position_index,
            constraint_index,
            geometry,
            external_geometry,
        )
        if controlled is None:
            return (), True
        references.append(controlled)
    return tuple(references), False


def _point_alignment_references(
    constraint: Any,
    constraint_index: int,
    geometry: tuple[SketchGeometry, ...],
    external_geometry: tuple[SketchGeometry, ...] = (),
) -> tuple[tuple[SketchConstraintReference, ...], bool] | None:
    try:
        if constraint.Type not in {"Horizontal", "Vertical"}:
            return None
        first = (_required_integer(constraint.First), _required_integer(constraint.FirstPos))
        second = (_required_integer(constraint.Second), _required_integer(constraint.SecondPos))
    except Exception:
        return (), True

    if first[1] == 0 and second == (_UNUSED_GEOMETRY_REFERENCE, 0):
        return None

    try:
        first_reference = _geometry_point_reference(
            *first,
            constraint_index,
            geometry,
            external_geometry,
        )
        second_reference = _geometry_point_reference(
            *second,
            constraint_index,
            geometry,
            external_geometry,
        )
    except SketchConstraintMalformedError:
        return (), True
    if first_reference is None or second_reference is None or first == second:
        return (), True
    return ((first_reference, second_reference), False)


def _point_on_object_references(
    constraint: Any,
    constraint_index: int,
    geometry: tuple[SketchGeometry, ...],
    external_geometry: tuple[SketchGeometry, ...] = (),
) -> tuple[tuple[SketchConstraintReference, ...], bool] | None:
    try:
        if constraint.Type != "PointOnObject":
            return None
        geometry_index = _required_integer(constraint.First)
        position_index = _required_integer(constraint.FirstPos)
        target_index = _required_integer(constraint.Second)
        target_position = _required_integer(constraint.SecondPos)
    except Exception as exc:
        raise SketchConstraintMalformedError(
            index=constraint_index,
            reason="reference_unreadable",
        ) from exc

    if target_position != 0:
        return (), True
    try:
        point = _geometry_point_reference(
            geometry_index,
            position_index,
            constraint_index,
            geometry,
            external_geometry,
        )
    except SketchConstraintMalformedError:
        return (), True
    if point is None:
        return (), True

    axis_references = {-1: "horizontal_axis", -2: "vertical_axis"}
    if target_index in axis_references:
        return (
            (
                point,
                SketchConstraintReference(reference=axis_references[target_index]),
            ),
            False,
        )
    target_geometry = _geometry_for_native_reference(
        target_index,
        0,
        geometry,
        external_geometry,
    )
    if target_index == geometry_index or not isinstance(
        target_geometry,
        (SketchLineGeometry, SketchCircleGeometry, SketchArcGeometry),
    ):
        return (), True
    return (
        (
            point,
            _geometry_reference(target_index, "edge"),
        ),
        False,
    )


def _geometry_point_reference(
    geometry_index: int,
    position_index: int,
    constraint_index: int,
    geometry: tuple[SketchGeometry, ...],
    external_geometry: tuple[SketchGeometry, ...] = (),
) -> SketchConstraintReference | None:
    item = _geometry_for_native_reference(
        geometry_index,
        position_index,
        geometry,
        external_geometry,
    )
    if item is None:
        if geometry_index >= len(geometry):
            raise SketchConstraintMalformedError(
                index=constraint_index,
                reason="geometry_reference_out_of_range",
            )
        return None
    position = _controlled_position(item, position_index)
    if position is None or position == "edge":
        return None
    return _geometry_reference(geometry_index, position)


def _distance_to_origin_reference(
    constraint: Any,
    constraint_index: int,
    geometry: tuple[SketchGeometry, ...],
    external_geometry: tuple[SketchGeometry, ...] = (),
) -> tuple[tuple[SketchConstraintReference, ...], bool] | None:
    try:
        if constraint.Type != "Distance":
            return None
        first = _required_integer(constraint.First)
        first_pos = _required_integer(constraint.FirstPos)
        second = _required_integer(constraint.Second)
        second_pos = _required_integer(constraint.SecondPos)
    except Exception as exc:
        raise SketchConstraintMalformedError(
            index=constraint_index,
            reason="reference_unreadable",
        ) from exc

    if (first, first_pos) == (-1, 1):
        geometry_index, position_index = second, second_pos
    elif (second, second_pos) == (-1, 1):
        geometry_index, position_index = first, first_pos
    else:
        return None

    reference = _geometry_point_reference(
        geometry_index,
        position_index,
        constraint_index,
        geometry,
        external_geometry,
    )
    if reference is None:
        return (), True
    return ((reference,), False)


def _geometry_for_native_reference(
    geometry_index: int,
    _position_index: int,
    geometry: tuple[SketchGeometry, ...],
    external_geometry: tuple[SketchGeometry, ...],
) -> SketchGeometry | None:
    if geometry_index >= 0:
        return geometry[geometry_index] if geometry_index < len(geometry) else None
    if geometry_index <= -3:
        number = -3 - geometry_index
        return external_geometry[number] if number < len(external_geometry) else None
    return None


def _geometry_reference(geometry_index: int, position: str) -> SketchConstraintReference:
    if geometry_index >= 0:
        return SketchConstraintReference(
            kind="geometry",
            geometry_index=geometry_index,
            position=position,
        )
    return SketchConstraintReference(
        kind="external_geometry",
        external_reference_number=-3 - geometry_index,
        position=position,
    )


def _whole_or_point_reference(
    geometry_index: int,
    position_index: int,
    constraint_index: int,
    geometry: tuple[SketchGeometry, ...],
    external_geometry: tuple[SketchGeometry, ...],
) -> SketchConstraintReference | None:
    item = _geometry_for_native_reference(
        geometry_index,
        position_index,
        geometry,
        external_geometry,
    )
    if item is None:
        if geometry_index >= len(geometry):
            raise SketchConstraintMalformedError(
                index=constraint_index,
                reason="geometry_reference_out_of_range",
            )
        return None
    position = _controlled_position(item, position_index)
    if position is None:
        return None
    return _geometry_reference(geometry_index, position)


def _controlled_position(item: SketchGeometry, position_index: int) -> str | None:
    if isinstance(item, UnsupportedSketchGeometry):
        return None
    if isinstance(item, SketchPointGeometry):
        return "point" if position_index == 1 else None
    return _POSITION_NAMES.get(position_index)


def _inspect_attachment(sketch: Any, body: Any | None) -> tuple[str, SketchAttachmentData | None]:
    try:
        raw_map_mode = str(sketch.MapMode)
    except Exception as exc:
        raise SketchInspectionError("map_mode_unreadable") from exc
    map_mode = _snake_case(raw_map_mode)

    try:
        support = sketch.AttachmentSupport
    except Exception:
        try:
            support = sketch.Support
        except Exception as exc:
            raise SketchInspectionError("attachment_support_unreadable") from exc

    target = _support_target(support)
    if target is None or body is None or raw_map_mode != "FlatFace":
        return map_mode, None

    try:
        target_name = str(target.Name)
        features = tuple(body.Origin.OriginFeatures)
    except Exception:
        return map_mode, None

    role_to_plane = {
        "XY_Plane": OriginPlane.XY,
        "XZ_Plane": OriginPlane.XZ,
        "YZ_Plane": OriginPlane.YZ,
    }
    for feature in features:
        try:
            same_feature = str(feature.Name) == target_name
            plane = role_to_plane.get(str(feature.Role))
        except Exception:
            continue
        if same_feature and plane is not None:
            try:
                offset_value = sketch.AttachmentOffset
            except Exception as exc:
                raise SketchInspectionError("attachment_offset_unreadable") from exc
            offset = _extract_placement_value(offset_value)
            if offset is None:
                raise SketchInspectionError("attachment_offset_unreadable")
            return map_mode, SketchAttachmentData(
                plane=plane,
                offset=offset,
            )
    return map_mode, None


def _support_target(support: Any) -> Any | None:
    if support is None:
        return None
    try:
        if len(support) == 0:
            return None
        entry = support[0]
    except Exception:
        return None
    if isinstance(entry, (tuple, list)):
        return None if len(entry) == 0 else entry[0]
    return entry


def _external_geometry_count(sketch: Any) -> int:
    try:
        return max(0, len(sketch.ExternalGeo) - 2)
    except Exception as exc:
        raise SketchInspectionError("external_geometry_unreadable") from exc


def _inspect_solver(sketch: Any) -> SketchSolverData:
    unavailable = SketchSolverData(
        available=False,
        fresh=False,
        degrees_of_freedom=None,
        fully_constrained=None,
        conflicting_constraint_indices=None,
        redundant_constraint_indices=None,
        partially_redundant_constraint_indices=None,
        malformed_constraint_indices=None,
    )
    try:
        state = {str(item) for item in sketch.State}
    except Exception:
        return unavailable

    fresh = "Up-to-date" in state and "Touched" not in state
    if not fresh:
        return SketchSolverData(
            available=True,
            fresh=False,
            degrees_of_freedom=None,
            fully_constrained=None,
            conflicting_constraint_indices=None,
            redundant_constraint_indices=None,
            partially_redundant_constraint_indices=None,
            malformed_constraint_indices=None,
        )

    try:
        return SketchSolverData(
            available=True,
            fresh=True,
            degrees_of_freedom=_required_integer(sketch.DoF),
            fully_constrained=bool(sketch.FullyConstrained),
            conflicting_constraint_indices=_solver_indices(sketch.ConflictingConstraints),
            redundant_constraint_indices=_solver_indices(sketch.RedundantConstraints),
            partially_redundant_constraint_indices=_solver_indices(
                sketch.PartiallyRedundantConstraints
            ),
            malformed_constraint_indices=_solver_indices(sketch.MalformedConstraints),
        )
    except Exception:
        return unavailable


def _solver_indices(value: Any) -> tuple[int, ...]:
    return tuple(_required_integer(item) for item in value)


def _point_from_vector(value: Any, geometry_index: int) -> SketchPoint2D:
    try:
        return SketchPoint2D(
            x=_geometry_number(value.x, geometry_index),
            y=_geometry_number(value.y, geometry_index),
        )
    except SketchGeometryMalformedError:
        raise
    except Exception as exc:
        raise SketchGeometryMalformedError(index=geometry_index, reason="point_unreadable") from exc


def _radius(value: Any, geometry_index: int) -> float:
    radius = _geometry_number(value, geometry_index)
    if radius <= 0:
        raise SketchGeometryMalformedError(index=geometry_index, reason="invalid_radius")
    return radius


def _geometry_number(value: Any, geometry_index: int) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise SketchGeometryMalformedError(
            index=geometry_index, reason="non_numeric_geometry_value"
        )
    result = float(value)
    if not math.isfinite(result):
        raise SketchGeometryMalformedError(index=geometry_index, reason="non_finite_geometry_value")
    return result


def _constraint_number(value: Any, constraint_index: int) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise SketchConstraintMalformedError(
            index=constraint_index, reason="non_numeric_constraint_value"
        )
    result = float(value)
    if not math.isfinite(result):
        raise SketchConstraintMalformedError(
            index=constraint_index, reason="non_finite_constraint_value"
        )
    return result


def _required_integer(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise TypeError("integer required")
    return int(value)


def _constraint_type(constraint: Any, index: int) -> str:
    try:
        value = constraint.Type
    except Exception as exc:
        raise SketchConstraintMalformedError(
            index=index, reason="constraint_type_unreadable"
        ) from exc
    if not isinstance(value, str) or not value:
        raise SketchConstraintMalformedError(index=index, reason="invalid_constraint_type")
    return _controlled_type_name(value)


def _constraint_name(constraint: Any, index: int) -> str | None:
    try:
        value = constraint.Name
    except Exception as exc:
        raise SketchConstraintMalformedError(
            index=index, reason="constraint_name_unreadable"
        ) from exc
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise SketchConstraintMalformedError(index=index, reason="invalid_constraint_name")
    return value


def _constraint_bool(constraint: Any, field: str, index: int) -> bool:
    try:
        value = getattr(constraint, field)
    except Exception as exc:
        raise SketchConstraintMalformedError(
            index=index, reason=f"{_snake_case(field)}_unreadable"
        ) from exc
    if not isinstance(value, bool):
        raise SketchConstraintMalformedError(index=index, reason=f"invalid_{_snake_case(field)}")
    return value


def _part_instance(value: Any, part: Any, type_name: str) -> bool:
    expected = getattr(part, type_name, None)
    return isinstance(expected, type) and isinstance(value, expected)


def _controlled_type_name(value: str) -> str:
    # Keep existing function unchanged
    normalized = re.sub(r"[^A-Za-z0-9_:]", "_", value)[:80]
    return normalized or "Unknown"


def _snake_case(value: str) -> str:
    with_boundaries = re.sub(r"(?<!^)(?=[A-Z])", "_", value)
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", with_boundaries)
    return normalized.strip("_").lower() or "unknown"


__all__ = ["get_sketch"]
