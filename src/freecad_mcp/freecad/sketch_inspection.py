"""Read-only inspection of Sketcher sketches through controlled public models."""

from __future__ import annotations

import math
import re
from numbers import Integral, Real
from typing import Any

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
    SketchAttachmentData,
    SketchCircleGeometry,
    SketchConstraint,
    SketchConstraintData,
    SketchConstraintReference,
    SketchConstraintValue,
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
    "Horizontal": {1},
    "Vertical": {1},
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
        constraints = _inspect_constraints(sketch, len(geometry))
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
            if _part_instance(item, part, "LineSegment"):
                result.append(
                    SketchLineGeometry(
                        index=index,
                        construction=construction,
                        start=_point_from_vector(item.StartPoint, index),
                        end=_point_from_vector(item.EndPoint, index),
                    )
                )
            elif _part_instance(item, part, "Circle"):
                result.append(
                    SketchCircleGeometry(
                        index=index,
                        construction=construction,
                        center=_point_from_vector(item.Center, index),
                        radius=_radius(item.Radius, index),
                    )
                )
            elif _part_instance(item, part, "ArcOfCircle"):
                result.append(
                    SketchArcGeometry(
                        index=index,
                        construction=construction,
                        center=_point_from_vector(item.Center, index),
                        radius=_radius(item.Radius, index),
                        start=_point_from_vector(item.StartPoint, index),
                        end=_point_from_vector(item.EndPoint, index),
                        start_angle_degrees=math.degrees(
                            _geometry_number(item.FirstParameter, index)
                        ),
                        end_angle_degrees=math.degrees(_geometry_number(item.LastParameter, index)),
                    )
                )
            elif _part_instance(item, part, "Point"):
                result.append(
                    SketchPointGeometry(
                        index=index,
                        construction=construction,
                        point=SketchPoint2D(
                            x=_geometry_number(item.X, index),
                            y=_geometry_number(item.Y, index),
                        ),
                    )
                )
            else:
                result.append(
                    UnsupportedSketchGeometry(
                        index=index,
                        construction=construction,
                        freecad_type=_controlled_type_name(type(item).__name__),
                    )
                )
        except SketchGeometryMalformedError:
            raise
        except Exception as exc:
            raise SketchGeometryMalformedError(
                index=index, reason="geometry_attributes_unreadable"
            ) from exc
    return tuple(result)


def _inspect_constraints(sketch: Any, geometry_count: int) -> tuple[SketchConstraint, ...]:
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

    result: list[SketchConstraint] = []
    for index, item in enumerate(raw_constraints):
        freecad_type = _constraint_type(item, index)
        name = _constraint_name(item, index)
        active = _constraint_bool(item, "IsActive", index)
        virtual_space = _constraint_bool(item, "InVirtualSpace", index)

        if freecad_type not in _SUPPORTED_CONSTRAINTS:
            result.append(
                UnsupportedSketchConstraint(
                    index=index,
                    freecad_type=freecad_type,
                    name=name,
                    active=active,
                    virtual_space=virtual_space,
                )
            )
            continue

        references, unsupported_reference = _constraint_references(item, index, geometry_count)
        if unsupported_reference:
            result.append(
                UnsupportedSketchConstraint(
                    index=index,
                    freecad_type=freecad_type,
                    name=name,
                    active=active,
                    virtual_space=virtual_space,
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
                type=_SUPPORTED_CONSTRAINTS[freecad_type],
                name=name,
                active=active,
                virtual_space=virtual_space,
                driving=driving,
                references=references,
                value=value,
            )
        )
    return tuple(result)


def _constraint_references(
    constraint: Any, constraint_index: int, geometry_count: int
) -> tuple[tuple[SketchConstraintReference, ...], bool]:
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
        if geometry_index <= -3:
            return (), True
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
        if geometry_index < 0 or position_index not in _POSITION_NAMES:
            return (), True
        if geometry_index >= geometry_count:
            raise SketchConstraintMalformedError(
                index=constraint_index, reason="geometry_reference_out_of_range"
            )
        references.append(
            SketchConstraintReference(
                kind="geometry",
                geometry_index=geometry_index,
                position=_POSITION_NAMES[position_index],
            )
        )
    return tuple(references), False


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
    normalized = re.sub(r"[^A-Za-z0-9_:]", "_", value)[:80]
    return normalized or "Unknown"


def _snake_case(value: str) -> str:
    with_boundaries = re.sub(r"(?<!^)(?=[A-Z])", "_", value)
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", with_boundaries)
    return normalized.strip("_").lower() or "unknown"


__all__ = ["get_sketch"]
