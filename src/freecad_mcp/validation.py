"""Explicit pure-Python validation for controlled MCP requests."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping

from pydantic import TypeAdapter, ValidationError

from freecad_mcp.core.result import CommandResult
from freecad_mcp.models import (
    MAX_SKETCH_CONSTRAINT_BATCH_SIZE,
    MAX_SKETCH_GEOMETRY_BATCH_SIZE,
    MAX_SKETCH_MUTATION_SELECTION_SIZE,
    AngleBetweenLinesConstraintInput,
    ArcOfCircleGeometryInput,
    CircleGeometryInput,
    CoincidentConstraintInput,
    DistanceBetweenPointsConstraintInput,
    DistanceXBetweenPointsConstraintInput,
    DistanceYBetweenPointsConstraintInput,
    EqualConstraintInput,
    ExternalGeometrySourceInput,
    HorizontalPointsConstraintInput,
    LineSegmentGeometryInput,
    ObjectSubelementExternalGeometrySourceInput,
    OriginPlane,
    ParallelConstraintInput,
    PerpendicularConstraintInput,
    PointGeometryInput,
    PointOnObjectConstraintInput,
    SketchAnalysisRequestInput,
    SketchCenteredRectangleRequestInput,
    SketchConstraintGeometryReferenceInput,
    SketchConstraintInput,
    SketchConstraintPointReferenceInput,
    SketchEquilateralTriangleRequestInput,
    SketchGeometryExternalGeometrySourceInput,
    SketchGeometryInput,
    SketchHorizontalAxisReferenceInput,
    SketchProfileAnalysisRequestInput,
    SketchRectangleRequestInput,
    SketchRegularPolygonRequestInput,
    SketchRoundedRectangleRequestInput,
    SketchSlotRequestInput,
    SketchVerticalAxisReferenceInput,
    SymmetricConstraintInput,
    TangentConstraintInput,
    VerticalPointsConstraintInput,
)

_INTERNAL_NAME_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_EXTERNAL_SUBELEMENT_PATTERN = re.compile(r"(?:Edge|Vertex)[1-9][0-9]*\Z")
_INTERNAL_NAME_RULE = "ASCII letter or underscore, followed by letters, digits, or underscores"
_SUPPORTED_SKETCH_GEOMETRY_INPUT_TYPES = {
    "arc_of_circle",
    "circle",
    "line_segment",
    "point",
}
_SUPPORTED_SKETCH_CONSTRAINT_INPUT_TYPES = {
    "angle",
    "coincident",
    "diameter",
    "distance",
    "distance_x",
    "distance_y",
    "equal",
    "horizontal",
    "horizontal_points",
    "parallel",
    "perpendicular",
    "point_on_object",
    "radius",
    "symmetric",
    "tangent",
    "vertical",
    "vertical_points",
}
_SKETCH_GEOMETRY_INPUT_ADAPTER: TypeAdapter[SketchGeometryInput] = TypeAdapter(SketchGeometryInput)
_SKETCH_CONSTRAINT_INPUT_ADAPTER: TypeAdapter[SketchConstraintInput] = TypeAdapter(
    SketchConstraintInput
)
_SKETCH_RECTANGLE_REQUEST_ADAPTER: TypeAdapter[SketchRectangleRequestInput] = TypeAdapter(
    SketchRectangleRequestInput
)
_SKETCH_CENTERED_RECTANGLE_REQUEST_ADAPTER: TypeAdapter[SketchCenteredRectangleRequestInput] = (
    TypeAdapter(SketchCenteredRectangleRequestInput)
)
_SKETCH_EQUILATERAL_TRIANGLE_REQUEST_ADAPTER: TypeAdapter[SketchEquilateralTriangleRequestInput] = (
    TypeAdapter(SketchEquilateralTriangleRequestInput)
)
_SKETCH_REGULAR_POLYGON_REQUEST_ADAPTER: TypeAdapter[SketchRegularPolygonRequestInput] = (
    TypeAdapter(SketchRegularPolygonRequestInput)
)
_SKETCH_SLOT_REQUEST_ADAPTER: TypeAdapter[SketchSlotRequestInput] = TypeAdapter(
    SketchSlotRequestInput
)
_SKETCH_ROUNDED_RECTANGLE_REQUEST_ADAPTER: TypeAdapter[SketchRoundedRectangleRequestInput] = (
    TypeAdapter(SketchRoundedRectangleRequestInput)
)
_EXTERNAL_GEOMETRY_SOURCE_ADAPTER: TypeAdapter[ExternalGeometrySourceInput] = TypeAdapter(
    ExternalGeometrySourceInput
)


def _validate_object_name(value: object, *, field: str, subject: str) -> CommandResult | None:
    if not isinstance(value, str):
        return CommandResult.failure(
            code="validation_error",
            message=f"{subject} name must be a non-empty string.",
            data={"field": field, "actual_type": type(value).__name__},
        )
    if not value.strip():
        return CommandResult.failure(
            code="validation_error",
            message=f"{subject} name must not be empty or whitespace.",
            data={"field": field},
        )
    if _INTERNAL_NAME_PATTERN.fullmatch(value) is None:
        return CommandResult.failure(
            code="validation_error",
            message=f"{subject} name does not satisfy the MCP object-name policy.",
            data={"field": field, "name": value, "rule": _INTERNAL_NAME_RULE},
        )
    return None


def _validate_optional_label(
    label: object | None, *, subject: str, code: str
) -> CommandResult | None:
    if label is not None and not isinstance(label, str):
        return CommandResult.failure(
            code=code,
            message=f"{subject} label must be a string when supplied.",
            data={"field": "label", "actual_type": type(label).__name__},
        )
    return None


def validate_document_reference(name: object) -> CommandResult | None:
    """Validate an internal document name used for lookup or saving."""
    if not isinstance(name, str):
        return CommandResult.failure(
            code="validation_error",
            message="Document name must be a non-empty string.",
            data={"field": "name", "actual_type": type(name).__name__},
        )
    if not name.strip():
        return CommandResult.failure(
            code="validation_error",
            message="Document name must not be empty or whitespace.",
            data={"field": "name"},
        )
    if _INTERNAL_NAME_PATTERN.fullmatch(name) is None:
        return CommandResult.failure(
            code="validation_error",
            message="Document name does not satisfy the MCP document-name policy.",
            data={"field": "name", "name": name, "rule": _INTERNAL_NAME_RULE},
        )
    return None


def validate_document_history_request(
    document_name: object,
    expected_transaction_name: object | None = None,
) -> CommandResult | None:
    """Validate one history inspection or mutation request."""
    document_error = validate_document_reference(document_name)
    if document_error is not None:
        return document_error
    if expected_transaction_name is None:
        return None
    if not isinstance(expected_transaction_name, str):
        return CommandResult.failure(
            code="validation_error",
            message="Expected transaction name must be a non-empty string when supplied.",
            data={
                "field": "expected_transaction_name",
                "actual_type": type(expected_transaction_name).__name__,
            },
        )
    if not expected_transaction_name.strip():
        return CommandResult.failure(
            code="validation_error",
            message="Expected transaction name must not be empty or whitespace.",
            data={"field": "expected_transaction_name"},
        )
    return None


def validate_object_reference(document_name: object, object_name: object) -> CommandResult | None:
    """Validate document- and object-name arguments used for object lookup."""
    doc_error = validate_document_reference(document_name)
    if doc_error is not None:
        return doc_error
    return _validate_object_name(object_name, field="object_name", subject="Object")


def validate_add_external_geometry_request(
    document_name: object,
    sketch_name: object,
    source: object,
) -> CommandResult | ExternalGeometrySourceInput:
    """Validate one narrow same-document external-geometry source union."""
    reference_error = validate_object_reference(document_name, sketch_name)
    if reference_error is not None:
        return reference_error
    if isinstance(source, Mapping):
        discriminator = source.get("type")
        if isinstance(discriminator, str) and discriminator not in {
            "object_subelement",
            "sketch_geometry",
        }:
            return CommandResult.failure(
                code="validation_error",
                message="External geometry source uses an unsupported type.",
                data={
                    "field": "source.type",
                    "actual_value": discriminator,
                    "allowed": ["object_subelement", "sketch_geometry"],
                },
            )
    try:
        parsed = _EXTERNAL_GEOMETRY_SOURCE_ADAPTER.validate_python(source)
    except ValidationError as exc:
        first = exc.errors(include_url=False)[0]
        path = ".".join(str(item) for item in first.get("loc", ()))
        return CommandResult.failure(
            code="validation_error",
            message="External geometry source does not satisfy the strict schema.",
            data={
                "field": f"source.{path}" if path else "source",
                "reason": str(first.get("type", "invalid_source")),
            },
        )

    assert isinstance(sketch_name, str)
    if isinstance(parsed, ObjectSubelementExternalGeometrySourceInput):
        name_error = _validate_object_name(
            parsed.object_name,
            field="source.object_name",
            subject="Source object",
        )
        if name_error is not None:
            return name_error
        if _EXTERNAL_SUBELEMENT_PATTERN.fullmatch(parsed.subelement) is None:
            return CommandResult.failure(
                code="validation_error",
                message="Source subelement must be a canonical EdgeN or VertexN name.",
                data={
                    "field": "source.subelement",
                    "actual_value": parsed.subelement,
                    "rule": "Edge or Vertex followed by a positive decimal integer",
                },
            )
        return parsed

    assert isinstance(parsed, SketchGeometryExternalGeometrySourceInput)
    name_error = _validate_object_name(
        parsed.sketch_name,
        field="source.sketch_name",
        subject="Source sketch",
    )
    if name_error is not None:
        return name_error
    if parsed.sketch_name == sketch_name:
        return CommandResult.failure(
            code="validation_error",
            message="A sketch cannot add its own geometry as an external reference.",
            data={
                "field": "source.sketch_name",
                "reason": "target_sketch_is_source",
            },
        )
    return parsed


def validate_external_geometry_reference_request(
    document_name: object,
    sketch_name: object,
    external_reference_number: object,
) -> CommandResult | int:
    """Validate one controlled non-negative sketch-local reference number."""
    reference_error = validate_object_reference(document_name, sketch_name)
    if reference_error is not None:
        return reference_error
    if type(external_reference_number) is not int:
        return CommandResult.failure(
            code="validation_error",
            message="External reference number must be a non-negative strict integer.",
            data={
                "field": "external_reference_number",
                "actual_type": type(external_reference_number).__name__,
            },
        )
    if external_reference_number < 0:
        return CommandResult.failure(
            code="validation_error",
            message="External reference number must be non-negative.",
            data={
                "field": "external_reference_number",
                "value": external_reference_number,
            },
        )
    return external_reference_number


def validate_analyze_sketch_request(
    document_name: object,
    sketch_name: object,
    include_construction: object = False,
    include_external: object = False,
) -> CommandResult | SketchAnalysisRequestInput:
    """Validate the strict broad-analysis request."""
    reference_error = validate_object_reference(document_name, sketch_name)
    if reference_error is not None:
        return reference_error
    flag_error = _validate_analysis_flags(include_construction, include_external)
    if flag_error is not None:
        return flag_error
    assert isinstance(document_name, str)
    assert isinstance(sketch_name, str)
    assert isinstance(include_construction, bool)
    assert isinstance(include_external, bool)
    return SketchAnalysisRequestInput(
        document_name=document_name,
        sketch_name=sketch_name,
        include_construction=include_construction,
        include_external=include_external,
    )


def validate_sketch_profile_analysis_request(
    document_name: object,
    sketch_name: object,
    geometry_indices: object = None,
    include_construction: object = False,
    include_external: object = False,
) -> CommandResult | SketchProfileAnalysisRequestInput:
    """Validate shared profile-validation/open-vertex selection semantics."""
    reference_error = validate_object_reference(document_name, sketch_name)
    if reference_error is not None:
        return reference_error
    flag_error = _validate_analysis_flags(include_construction, include_external)
    if flag_error is not None:
        return flag_error

    controlled_indices: tuple[int, ...] | None = None
    if geometry_indices is not None:
        if not isinstance(geometry_indices, list):
            return CommandResult.failure(
                code="validation_error",
                message="Geometry indices must be a non-empty array when supplied.",
                data={
                    "field": "geometry_indices",
                    "actual_type": type(geometry_indices).__name__,
                },
            )
        if not geometry_indices:
            return CommandResult.failure(
                code="validation_error",
                message="Geometry indices must not be an empty array.",
                data={"field": "geometry_indices", "reason": "empty_selection"},
            )
        parsed: list[int] = []
        for position, value in enumerate(geometry_indices):
            if type(value) is not int:
                return CommandResult.failure(
                    code="validation_error",
                    message="Each geometry index must be a non-negative strict integer.",
                    data={
                        "field": f"geometry_indices[{position}]",
                        "actual_type": type(value).__name__,
                    },
                )
            if value < 0:
                return CommandResult.failure(
                    code="validation_error",
                    message="Each geometry index must be non-negative.",
                    data={"field": f"geometry_indices[{position}]", "value": value},
                )
            if value in parsed:
                return CommandResult.failure(
                    code="validation_error",
                    message="Geometry indices must be unique.",
                    data={
                        "field": f"geometry_indices[{position}]",
                        "geometry_index": value,
                        "reason": "duplicate_geometry_index",
                    },
                )
            parsed.append(value)
        controlled_indices = tuple(parsed)

    assert isinstance(document_name, str)
    assert isinstance(sketch_name, str)
    assert isinstance(include_construction, bool)
    assert isinstance(include_external, bool)
    return SketchProfileAnalysisRequestInput(
        document_name=document_name,
        sketch_name=sketch_name,
        geometry_indices=controlled_indices,
        include_construction=include_construction,
        include_external=include_external,
    )


def _validate_analysis_flags(
    include_construction: object,
    include_external: object,
) -> CommandResult | None:
    for field, value in (
        ("include_construction", include_construction),
        ("include_external", include_external),
    ):
        if type(value) is not bool:
            return CommandResult.failure(
                code="validation_error",
                message=f"{field} must be a strict boolean.",
                data={"field": field, "actual_type": type(value).__name__},
            )
    return None


def validate_create_document_request(name: object, label: object | None) -> CommandResult | None:
    """Validate create-document arguments without changing its error contract."""
    if name is None:
        return CommandResult.failure(
            code="name_required",
            message="Document name is required.",
            data={"field": "name"},
        )
    if not isinstance(name, str):
        return CommandResult.failure(
            code="invalid_name_type",
            message="Document name must be a string.",
            data={"field": "name", "actual_type": type(name).__name__},
        )
    if not name.strip():
        return CommandResult.failure(
            code="name_required",
            message="Document name must not be empty or whitespace.",
            data={"field": "name"},
        )
    if _INTERNAL_NAME_PATTERN.fullmatch(name) is None:
        return CommandResult.failure(
            code="invalid_document_name",
            message="Document name does not satisfy the MCP document-name policy.",
            data={"field": "name", "name": name, "rule": _INTERNAL_NAME_RULE},
        )
    return _validate_optional_label(label, subject="Document", code="invalid_label_type")


def validate_create_body_request(
    document_name: object, name: object, label: object | None
) -> CommandResult | None:
    """Validate create-body arguments with its existing field-specific messages."""
    doc_error = validate_document_reference(document_name)
    if doc_error is not None:
        return doc_error
    name_error = _validate_object_name(name, field="name", subject="Body")
    if name_error is not None:
        return name_error
    return _validate_optional_label(label, subject="Body", code="validation_error")


def validate_create_sketch_request(
    document_name: object,
    body_name: object,
    name: object,
    label: object | None,
    support_plane: object | None,
) -> CommandResult | None:
    """Validate create-sketch arguments without changing its public contract."""
    doc_error = validate_document_reference(document_name)
    if doc_error is not None:
        return doc_error

    body_error = _validate_object_name(body_name, field="body_name", subject="Body")
    if body_error is not None:
        return body_error
    sketch_error = _validate_object_name(name, field="name", subject="Sketch")
    if sketch_error is not None:
        return sketch_error
    label_error = _validate_optional_label(label, subject="Sketch", code="validation_error")
    if label_error is not None:
        return label_error

    if support_plane is not None:
        valid_planes = {plane.value for plane in OriginPlane}
        if not isinstance(support_plane, str) or support_plane not in valid_planes:
            return CommandResult.failure(
                code="validation_error",
                message=(
                    "support_plane must be one of 'xy_plane', 'xz_plane', 'yz_plane' or omitted."
                ),
                data={
                    "field": "support_plane",
                    "actual_value": support_plane,
                    "allowed": sorted(valid_planes),
                },
            )
    return None


def validate_create_sketch_rectangle_request(
    document_name: object,
    sketch_name: object,
    width: object,
    height: object,
    placement: object,
) -> CommandResult | SketchRectangleRequestInput:
    """Validate and parse one complete lower-left rectangle request."""
    document_error = validate_document_reference(document_name)
    if document_error is not None:
        return document_error
    sketch_error = _validate_object_name(
        sketch_name,
        field="sketch_name",
        subject="Sketch",
    )
    if sketch_error is not None:
        return sketch_error

    try:
        parsed = _SKETCH_RECTANGLE_REQUEST_ADAPTER.validate_python(
            {
                "document_name": document_name,
                "sketch_name": sketch_name,
                "width": width,
                "height": height,
                "placement": placement,
            }
        )
    except ValidationError as exc:
        first_error = exc.errors(include_url=False)[0]
        location = ".".join(str(item) for item in first_error.get("loc", ()))
        if location in {"width", "height"}:
            invalid_value = width if location == "width" else height
            return CommandResult.failure(
                code="invalid_rectangle_dimensions",
                message=(
                    "Rectangle width and height must be finite strict numbers greater than zero."
                ),
                data={
                    "field": location,
                    "reason": "invalid_rectangle_dimensions",
                    "actual_type": type(invalid_value).__name__,
                },
            )
        return CommandResult.failure(
            code="validation_error",
            message="Rectangle placement must be a strict finite lower-left placement.",
            data={
                "field": location or "placement",
                "reason": "invalid_rectangle_placement",
            },
        )

    if not math.isfinite(parsed.placement.x + parsed.width) or not math.isfinite(
        parsed.placement.y + parsed.height
    ):
        return CommandResult.failure(
            code="invalid_rectangle_dimensions",
            message="Rectangle dimensions and placement must produce finite corner coordinates.",
            data={
                "field": "placement",
                "reason": "rectangle_coordinate_overflow",
            },
        )
    return parsed


def validate_create_sketch_centered_rectangle_request(
    document_name: object,
    sketch_name: object,
    width: object,
    height: object,
    center: object,
) -> CommandResult | SketchCenteredRectangleRequestInput:
    """Validate and parse one complete direct-centre rectangle request."""
    document_error = validate_document_reference(document_name)
    if document_error is not None:
        return document_error
    sketch_error = _validate_object_name(
        sketch_name,
        field="sketch_name",
        subject="Sketch",
    )
    if sketch_error is not None:
        return sketch_error

    try:
        parsed = _SKETCH_CENTERED_RECTANGLE_REQUEST_ADAPTER.validate_python(
            {
                "document_name": document_name,
                "sketch_name": sketch_name,
                "width": width,
                "height": height,
                "center": center,
            }
        )
    except ValidationError as exc:
        first_error = exc.errors(include_url=False)[0]
        location = ".".join(str(item) for item in first_error.get("loc", ()))
        if location in {"width", "height"}:
            invalid_value = width if location == "width" else height
            return CommandResult.failure(
                code="invalid_centered_rectangle_dimensions",
                message=(
                    "Centered rectangle width and height must be finite strict numbers "
                    "greater than zero."
                ),
                data={
                    "field": location,
                    "reason": "invalid_centered_rectangle_dimensions",
                    "actual_type": type(invalid_value).__name__,
                },
            )
        return CommandResult.failure(
            code="validation_error",
            message="Centered rectangle center must contain exactly finite strict x and y values.",
            data={
                "field": location or "center",
                "reason": "invalid_centered_rectangle_center",
            },
        )

    half_width = float(parsed.width) / 2.0
    half_height = float(parsed.height) / 2.0
    corners = (
        parsed.center.x - half_width,
        parsed.center.x + half_width,
        parsed.center.y - half_height,
        parsed.center.y + half_height,
    )
    if not all(math.isfinite(value) for value in corners):
        return CommandResult.failure(
            code="invalid_centered_rectangle_dimensions",
            message="Centered rectangle dimensions and center must produce finite corners.",
            data={
                "field": "center",
                "reason": "centered_rectangle_coordinate_overflow",
            },
        )
    return parsed


def validate_create_sketch_equilateral_triangle_request(
    document_name: object,
    sketch_name: object,
    circumradius: object,
    center: object,
    first_vertex_angle_degrees: object = 90.0,
) -> CommandResult | SketchEquilateralTriangleRequestInput:
    """Validate and parse one complete equilateral-triangle request."""
    name_error = _validate_polygon_names(document_name, sketch_name)
    if name_error is not None:
        return name_error
    try:
        parsed = _SKETCH_EQUILATERAL_TRIANGLE_REQUEST_ADAPTER.validate_python(
            {
                "document_name": document_name,
                "sketch_name": sketch_name,
                "circumradius": circumradius,
                "center": center,
                "first_vertex_angle_degrees": first_vertex_angle_degrees,
            }
        )
    except ValidationError as exc:
        return _polygon_validation_failure(
            exc,
            profile_type="equilateral_triangle",
            code="invalid_triangle_parameters",
        )
    if not _polygon_coordinates_are_finite(parsed.center.x, parsed.center.y, parsed.circumradius):
        return CommandResult.failure(
            code="invalid_triangle_parameters",
            message="Triangle parameters must produce finite sketch coordinates.",
            data={"field": "center", "reason": "triangle_coordinate_overflow"},
        )
    return parsed


def validate_create_sketch_regular_polygon_request(
    document_name: object,
    sketch_name: object,
    side_count: object,
    circumradius: object,
    center: object,
    first_vertex_angle_degrees: object = 0.0,
) -> CommandResult | SketchRegularPolygonRequestInput:
    """Validate and parse one complete bounded regular-polygon request."""
    name_error = _validate_polygon_names(document_name, sketch_name)
    if name_error is not None:
        return name_error
    try:
        parsed = _SKETCH_REGULAR_POLYGON_REQUEST_ADAPTER.validate_python(
            {
                "document_name": document_name,
                "sketch_name": sketch_name,
                "side_count": side_count,
                "circumradius": circumradius,
                "center": center,
                "first_vertex_angle_degrees": first_vertex_angle_degrees,
            }
        )
    except ValidationError as exc:
        return _polygon_validation_failure(
            exc,
            profile_type="regular_polygon",
            code="invalid_polygon_parameters",
        )
    if not _polygon_coordinates_are_finite(parsed.center.x, parsed.center.y, parsed.circumradius):
        return CommandResult.failure(
            code="invalid_polygon_parameters",
            message="Polygon parameters must produce finite sketch coordinates.",
            data={"field": "center", "reason": "polygon_coordinate_overflow"},
        )
    return parsed


def validate_create_sketch_slot_request(
    document_name: object,
    sketch_name: object,
    overall_length: object,
    overall_width: object,
    center: object,
    angle_degrees: object = 0.0,
) -> CommandResult | SketchSlotRequestInput:
    """Validate one strict centre-defined slot request without native imports."""
    name_error = _validate_polygon_names(document_name, sketch_name)
    if name_error is not None:
        return name_error
    try:
        parsed = _SKETCH_SLOT_REQUEST_ADAPTER.validate_python(
            {
                "document_name": document_name,
                "sketch_name": sketch_name,
                "overall_length": overall_length,
                "overall_width": overall_width,
                "center": center,
                "angle_degrees": angle_degrees,
            }
        )
    except ValidationError as exc:
        first_error = exc.errors(include_url=False)[0]
        location = ".".join(str(item) for item in first_error.get("loc", ()))
        return CommandResult.failure(
            code="invalid_slot_dimensions",
            message=(
                "Slot length, width, centre, and angle must be strict finite numbers with "
                "only the documented fields."
            ),
            data={
                "field": location or "request",
                "profile_type": "slot",
                "reason": str(first_error.get("type", "invalid_parameters")),
            },
        )
    if parsed.overall_length <= parsed.overall_width:
        return CommandResult.failure(
            code="invalid_slot_dimensions",
            message="Slot overall_length must be strictly greater than overall_width.",
            data={
                "field": "overall_length",
                "profile_type": "slot",
                "reason": "slot_length_not_greater_than_width",
            },
        )
    extent = float(parsed.overall_length) / 2.0
    if not all(
        math.isfinite(value)
        for value in (
            parsed.center.x - extent,
            parsed.center.x + extent,
            parsed.center.y - extent,
            parsed.center.y + extent,
        )
    ):
        return CommandResult.failure(
            code="invalid_slot_dimensions",
            message="Slot dimensions and centre must produce finite profile coordinates.",
            data={
                "field": "center",
                "profile_type": "slot",
                "reason": "slot_coordinate_overflow",
            },
        )
    return parsed


def validate_create_sketch_rounded_rectangle_request(
    document_name: object,
    sketch_name: object,
    width: object,
    height: object,
    corner_radius: object,
    placement: object,
) -> CommandResult | SketchRoundedRectangleRequestInput:
    """Validate one strict two-variant rounded-rectangle request."""
    name_error = _validate_polygon_names(document_name, sketch_name)
    if name_error is not None:
        return name_error
    try:
        parsed = _SKETCH_ROUNDED_RECTANGLE_REQUEST_ADAPTER.validate_python(
            {
                "document_name": document_name,
                "sketch_name": sketch_name,
                "width": width,
                "height": height,
                "corner_radius": corner_radius,
                "placement": placement,
            }
        )
    except ValidationError as exc:
        first_error = exc.errors(include_url=False)[0]
        location = ".".join(str(item) for item in first_error.get("loc", ()))
        return CommandResult.failure(
            code="invalid_rounded_rectangle_dimensions",
            message=(
                "Rounded-rectangle dimensions and placement must be strict, finite, and "
                "contain only the documented fields."
            ),
            data={
                "field": location or "request",
                "profile_type": "rounded_rectangle",
                "reason": str(first_error.get("type", "invalid_parameters")),
            },
        )
    if parsed.corner_radius >= min(parsed.width, parsed.height) / 2.0:
        return CommandResult.failure(
            code="invalid_rounded_rectangle_dimensions",
            message="corner_radius must be strictly less than half the smaller dimension.",
            data={
                "field": "corner_radius",
                "profile_type": "rounded_rectangle",
                "reason": "corner_radius_not_strictly_inside_bounds",
            },
        )
    if parsed.placement.type == "lower_left":
        coordinates = (
            parsed.placement.x,
            parsed.placement.x + parsed.width,
            parsed.placement.y,
            parsed.placement.y + parsed.height,
        )
    else:
        coordinates = (
            parsed.placement.x - parsed.width / 2.0,
            parsed.placement.x + parsed.width / 2.0,
            parsed.placement.y - parsed.height / 2.0,
            parsed.placement.y + parsed.height / 2.0,
        )
    if not all(math.isfinite(float(value)) for value in coordinates):
        return CommandResult.failure(
            code="invalid_rounded_rectangle_dimensions",
            message="Rounded-rectangle dimensions and placement must produce finite bounds.",
            data={
                "field": "placement",
                "profile_type": "rounded_rectangle",
                "reason": "rounded_rectangle_coordinate_overflow",
            },
        )
    return parsed


def _validate_polygon_names(document_name: object, sketch_name: object) -> CommandResult | None:
    document_error = validate_document_reference(document_name)
    if document_error is not None:
        return document_error
    return _validate_object_name(sketch_name, field="sketch_name", subject="Sketch")


def _polygon_validation_failure(
    error: ValidationError,
    *,
    profile_type: str,
    code: str,
) -> CommandResult:
    first_error = error.errors(include_url=False)[0]
    location = ".".join(str(item) for item in first_error.get("loc", ()))
    return CommandResult.failure(
        code=code,
        message=(
            "Triangle parameters must be strict, finite, and contain only the documented fields."
            if profile_type == "equilateral_triangle"
            else (
                "Polygon parameters must be strict, finite, bounded, and contain only the "
                "documented fields."
            )
        ),
        data={
            "field": location or "request",
            "profile_type": profile_type,
            "reason": str(first_error.get("type", "invalid_parameters")),
        },
    )


def _polygon_coordinates_are_finite(x: float, y: float, radius: float) -> bool:
    return all(math.isfinite(value) for value in (x - radius, x + radius, y - radius, y + radius))


def validate_add_sketch_geometry_request(
    document_name: object,
    sketch_name: object,
    geometry: object,
) -> CommandResult | tuple[SketchGeometryInput, ...]:
    """Validate and parse one ordered controlled geometry batch."""
    document_error = validate_document_reference(document_name)
    if document_error is not None:
        return document_error
    sketch_error = _validate_object_name(
        sketch_name,
        field="sketch_name",
        subject="Sketch",
    )
    if sketch_error is not None:
        return sketch_error

    if not isinstance(geometry, list):
        return CommandResult.failure(
            code="validation_error",
            message="Geometry must be a non-empty array.",
            data={"field": "geometry", "actual_type": type(geometry).__name__},
        )
    if not geometry:
        return CommandResult.failure(
            code="validation_error",
            message="Geometry must contain at least one item.",
            data={"field": "geometry", "minimum_items": 1},
        )
    if len(geometry) > MAX_SKETCH_GEOMETRY_BATCH_SIZE:
        return CommandResult.failure(
            code="validation_error",
            message=(
                "Geometry batch exceeds the maximum supported size of "
                f"{MAX_SKETCH_GEOMETRY_BATCH_SIZE} items."
            ),
            data={
                "field": "geometry",
                "maximum_items": MAX_SKETCH_GEOMETRY_BATCH_SIZE,
                "actual_items": len(geometry),
            },
        )

    parsed_items: list[SketchGeometryInput] = []
    for index, item in enumerate(geometry):
        if isinstance(item, Mapping):
            discriminator = item.get("type")
            if isinstance(discriminator, str) and (
                discriminator not in _SUPPORTED_SKETCH_GEOMETRY_INPUT_TYPES
            ):
                return CommandResult.failure(
                    code="validation_error",
                    message=f"Geometry item {index} uses an unsupported type.",
                    data={
                        "field": f"geometry[{index}].type",
                        "geometry_index": index,
                        "actual_value": discriminator,
                        "allowed": sorted(_SUPPORTED_SKETCH_GEOMETRY_INPUT_TYPES),
                    },
                )
        try:
            parsed = _SKETCH_GEOMETRY_INPUT_ADAPTER.validate_python(item)
        except ValidationError as exc:
            return _geometry_model_validation_error(index, exc)

        semantic_error = _validate_geometry_semantics(index, parsed)
        if semantic_error is not None:
            return semantic_error
        parsed_items.append(parsed)

    return tuple(parsed_items)


def validate_add_sketch_constraints_request(
    document_name: object,
    sketch_name: object,
    constraints: object,
) -> CommandResult | tuple[SketchConstraintInput, ...]:
    """Validate and parse one ordered controlled constraint batch."""
    document_error = validate_document_reference(document_name)
    if document_error is not None:
        return document_error
    sketch_error = _validate_object_name(
        sketch_name,
        field="sketch_name",
        subject="Sketch",
    )
    if sketch_error is not None:
        return sketch_error

    if not isinstance(constraints, list):
        return CommandResult.failure(
            code="validation_error",
            message="Constraints must be a non-empty array.",
            data={"field": "constraints", "actual_type": type(constraints).__name__},
        )
    if not constraints:
        return CommandResult.failure(
            code="validation_error",
            message="Constraints must contain at least one item.",
            data={
                "field": "constraints",
                "minimum_items": 1,
                "reason": "empty_constraint_batch",
            },
        )
    if len(constraints) > MAX_SKETCH_CONSTRAINT_BATCH_SIZE:
        return CommandResult.failure(
            code="validation_error",
            message=(
                "Constraint batch exceeds the maximum supported size of "
                f"{MAX_SKETCH_CONSTRAINT_BATCH_SIZE} items."
            ),
            data={
                "field": "constraints",
                "maximum_items": MAX_SKETCH_CONSTRAINT_BATCH_SIZE,
                "actual_items": len(constraints),
                "reason": "constraint_batch_too_large",
            },
        )

    parsed_items: list[SketchConstraintInput] = []
    for index, item in enumerate(constraints):
        if isinstance(item, Mapping):
            discriminator = item.get("type")
            if isinstance(discriminator, str) and (
                discriminator not in _SUPPORTED_SKETCH_CONSTRAINT_INPUT_TYPES
            ):
                return CommandResult.failure(
                    code="validation_error",
                    message=f"Constraint item {index} uses an unsupported type.",
                    data={
                        "field": f"constraints[{index}].type",
                        "constraint_index": index,
                        "actual_value": discriminator,
                        "allowed": sorted(_SUPPORTED_SKETCH_CONSTRAINT_INPUT_TYPES),
                        "reason": "unsupported_constraint_type",
                    },
                )
        try:
            parsed = _SKETCH_CONSTRAINT_INPUT_ADAPTER.validate_python(item)
        except ValidationError as exc:
            return _constraint_model_validation_error(index, item, exc)

        semantic_error = _validate_constraint_semantics(index, parsed)
        if semantic_error is not None:
            return semantic_error
        parsed_items.append(parsed)

    return tuple(parsed_items)


def normalize_arc_angles_degrees(start: float, end: float) -> tuple[float, float]:
    """Return one canonical counter-clockwise arc span shorter than 360 degrees."""
    normalized_start = start % 360.0
    normalized_end = end % 360.0
    if normalized_start == normalized_end:
        raise ValueError("arc_angles_collapse")
    if normalized_end < normalized_start:
        normalized_end += 360.0
    return normalized_start, normalized_end


def _geometry_model_validation_error(index: int, exc: ValidationError) -> CommandResult:
    error = exc.errors(include_url=False, include_context=False, include_input=False)[0]
    location = [str(part) for part in error.get("loc", ())]
    if location and location[0] in _SUPPORTED_SKETCH_GEOMETRY_INPUT_TYPES:
        location.pop(0)
    field = f"geometry[{index}]"
    if location:
        field = f"{field}." + ".".join(location)
    return CommandResult.failure(
        code="validation_error",
        message=f"Geometry item {index} is malformed.",
        data={
            "field": field,
            "geometry_index": index,
            "reason": str(error.get("type", "invalid_geometry_input")),
        },
    )


def _constraint_model_validation_error(
    index: int,
    item: object,
    exc: ValidationError,
) -> CommandResult:
    error = exc.errors(include_url=False, include_context=False, include_input=False)[0]
    raw_location = [str(part) for part in error.get("loc", ())]
    location = [
        part
        for part in raw_location
        if part not in _SUPPORTED_SKETCH_CONSTRAINT_INPUT_TYPES
        and part
        not in {"line_length", "point_to_origin", "between_points", "line_angle", "between_lines"}
    ]
    field = f"constraints[{index}]"
    if location:
        field = f"{field}." + ".".join(location)

    leaf = location[-1] if location else ""
    validation_type = str(error.get("type", "invalid_constraint_input"))
    reference_reason = _malformed_reference_reason(item)
    if reference_reason is not None:
        reason = reference_reason
    elif validation_type == "missing":
        reason = "invalid_constraint_input"
    elif leaf == "position":
        reason = "invalid_position_reference"
    elif leaf in {"value", "value_degrees"}:
        reason = "invalid_constraint_value"
    elif leaf.endswith("geometry_index"):
        reason = "invalid_geometry_reference"
    else:
        reason = "invalid_constraint_input"
    return CommandResult.failure(
        code="validation_error",
        message=f"Constraint item {index} is malformed.",
        data={
            "field": field,
            "constraint_index": index,
            "reason": reason,
            "validation_type": validation_type,
        },
    )


def _malformed_reference_reason(item: object) -> str | None:
    if not isinstance(item, Mapping):
        return None
    constraint_type = item.get("type")
    if constraint_type == "tangent":
        for field in ("first", "second"):
            reference = item.get(field)
            if isinstance(reference, Mapping) and set(reference) != {"geometry_index"}:
                return "invalid_geometry_reference"
        return None

    allowed_references: set[str] = set()
    if constraint_type == "coincident":
        allowed_references = {"origin"}
    elif constraint_type == "point_on_object":
        allowed_references = {"horizontal_axis", "vertical_axis"}
    elif constraint_type == "symmetric":
        allowed_references = {"origin", "horizontal_axis", "vertical_axis"}

    for field in ("first", "second", "point", "about"):
        reference = item.get(field)
        if not isinstance(reference, Mapping):
            continue
        if "reference" in reference:
            if set(reference) != {"reference"}:
                return "invalid_point_reference"
            literal = reference.get("reference")
            reference_allowed_here = constraint_type != "symmetric" or field == "about"
            if (
                not reference_allowed_here
                or not isinstance(literal, str)
                or literal not in allowed_references
            ):
                return "unsupported_reference"
            continue
        whole_geometry_reference = (constraint_type == "symmetric" and field == "about") or (
            constraint_type == "point_on_object" and field == "second"
        )
        if whole_geometry_reference and set(reference) == {"geometry_index"}:
            continue
        if not {"geometry_index", "position"}.issubset(reference):
            return "invalid_point_reference"
        if set(reference) != {"geometry_index", "position"}:
            return "invalid_point_reference"
    return None


def _validate_constraint_semantics(
    index: int,
    item: SketchConstraintInput,
) -> CommandResult | None:
    pair: tuple[int, int] | None = None
    if isinstance(
        item,
        (
            ParallelConstraintInput,
            PerpendicularConstraintInput,
            EqualConstraintInput,
            AngleBetweenLinesConstraintInput,
        ),
    ):
        pair = (item.first_geometry_index, item.second_geometry_index)
    elif isinstance(
        item,
        (
            DistanceBetweenPointsConstraintInput,
            DistanceXBetweenPointsConstraintInput,
            DistanceYBetweenPointsConstraintInput,
        ),
    ):
        pair = (item.first.geometry_index, item.second.geometry_index)
    elif (
        isinstance(item, TangentConstraintInput)
        and item.first.geometry_index == item.second.geometry_index
    ):
        return CommandResult.failure(
            code="validation_error",
            message=f"Constraint item {index} must reference distinct tangent geometry.",
            data={
                "field": f"constraints[{index}]",
                "constraint_index": index,
                "geometry_index": item.first.geometry_index,
                "reason": "identical_tangent_geometry",
            },
        )

    if (
        isinstance(item, (HorizontalPointsConstraintInput, VerticalPointsConstraintInput))
        and item.first == item.second
    ):
        return CommandResult.failure(
            code="validation_error",
            message=f"Constraint item {index} must reference two distinct points.",
            data={
                "field": f"constraints[{index}]",
                "constraint_index": index,
                "reason": "identical_point_references",
            },
        )

    if isinstance(item, CoincidentConstraintInput):
        first_is_point = isinstance(item.first, SketchConstraintPointReferenceInput)
        second_is_point = isinstance(item.second, SketchConstraintPointReferenceInput)
        if not first_is_point and not second_is_point:
            return CommandResult.failure(
                code="validation_error",
                message=f"Constraint item {index} cannot reference the origin twice.",
                data={
                    "field": f"constraints[{index}]",
                    "constraint_index": index,
                    "reason": "same_origin_reference",
                },
            )
        if isinstance(item.first, SketchConstraintPointReferenceInput) and isinstance(
            item.second,
            SketchConstraintPointReferenceInput,
        ):
            pair = (item.first.geometry_index, item.second.geometry_index)

    if isinstance(item, PointOnObjectConstraintInput):
        if isinstance(item.second, SketchConstraintGeometryReferenceInput):
            if not isinstance(item.first, SketchConstraintPointReferenceInput):
                return CommandResult.failure(
                    code="validation_error",
                    message=(
                        f"Constraint item {index} must place a selected point "
                        "on the target geometry."
                    ),
                    data={
                        "field": f"constraints[{index}]",
                        "constraint_index": index,
                        "reason": "unsupported_reference",
                    },
                )
            if item.first.geometry_index == item.second.geometry_index:
                return CommandResult.failure(
                    code="validation_error",
                    message=(f"Constraint item {index} cannot place a point on its own geometry."),
                    data={
                        "field": f"constraints[{index}].second",
                        "constraint_index": index,
                        "geometry_index": item.second.geometry_index,
                        "reason": "point_on_object_self_target",
                    },
                )
        else:
            references = (item.first, item.second)
            point_count = sum(
                isinstance(reference, SketchConstraintPointReferenceInput)
                for reference in references
            )
            axis_count = sum(
                isinstance(
                    reference,
                    (SketchHorizontalAxisReferenceInput, SketchVerticalAxisReferenceInput),
                )
                for reference in references
            )
            if point_count == 1 and axis_count == 1:
                return None
            return CommandResult.failure(
                code="validation_error",
                message=(
                    f"Constraint item {index} must reference one geometry point "
                    "and one supported target object."
                ),
                data={
                    "field": f"constraints[{index}]",
                    "constraint_index": index,
                    "reason": "unsupported_reference",
                },
            )

    if isinstance(item, SymmetricConstraintInput):
        if item.first == item.second:
            return CommandResult.failure(
                code="validation_error",
                message=f"Constraint item {index} must reference two distinct points.",
                data={
                    "field": f"constraints[{index}]",
                    "constraint_index": index,
                    "reason": "identical_symmetric_points",
                },
            )
        if isinstance(item.about, SketchConstraintPointReferenceInput) and item.about in {
            item.first,
            item.second,
        }:
            return CommandResult.failure(
                code="validation_error",
                message=(
                    f"Constraint item {index} cannot use either selected point "
                    "as its symmetry centre."
                ),
                data={
                    "field": f"constraints[{index}].about",
                    "constraint_index": index,
                    "reason": "identical_symmetry_centre",
                },
            )
        if isinstance(item.about, SketchConstraintGeometryReferenceInput) and (
            item.about.geometry_index in {item.first.geometry_index, item.second.geometry_index}
        ):
            return CommandResult.failure(
                code="validation_error",
                message=(
                    f"Constraint item {index} cannot select a point from its own symmetry line."
                ),
                data={
                    "field": f"constraints[{index}].about",
                    "constraint_index": index,
                    "reason": "degenerate_symmetry_line",
                },
            )

    if pair is not None and pair[0] == pair[1]:
        return CommandResult.failure(
            code="validation_error",
            message=f"Constraint item {index} must reference distinct geometry.",
            data={
                "field": f"constraints[{index}]",
                "constraint_index": index,
                "geometry_index": pair[0],
                "reason": "same_geometry_reference",
            },
        )
    return None


def _validate_geometry_semantics(
    index: int,
    item: SketchGeometryInput,
) -> CommandResult | None:
    if isinstance(item, LineSegmentGeometryInput):
        if item.start.x == item.end.x and item.start.y == item.end.y:
            return CommandResult.failure(
                code="validation_error",
                message=f"Geometry item {index} is a zero-length line segment.",
                data={
                    "field": f"geometry[{index}]",
                    "geometry_index": index,
                    "reason": "zero_length_line",
                },
            )
        return None

    if isinstance(item, ArcOfCircleGeometryInput):
        try:
            normalize_arc_angles_degrees(
                item.start_angle_degrees,
                item.end_angle_degrees,
            )
        except ValueError:
            return CommandResult.failure(
                code="validation_error",
                message=f"Geometry item {index} has collapsing arc angles.",
                data={
                    "field": f"geometry[{index}]",
                    "geometry_index": index,
                    "reason": "arc_angles_collapse",
                },
            )
        return None

    if isinstance(item, (CircleGeometryInput, PointGeometryInput)):
        return None

    return CommandResult.failure(
        code="validation_error",
        message=f"Geometry item {index} uses an unsupported type.",
        data={
            "field": f"geometry[{index}].type",
            "geometry_index": index,
            "allowed": sorted(_SUPPORTED_SKETCH_GEOMETRY_INPUT_TYPES),
        },
    )


def validate_sketch_mutation_selection_request(
    document_name: object,
    sketch_name: object,
    indices: object,
    *,
    field: str,
) -> tuple[int, ...] | CommandResult:
    """Validate and canonicalize a non-empty strict internal-index selection."""
    reference_error = validate_object_reference(document_name, sketch_name)
    if reference_error is not None:
        return reference_error
    if not isinstance(indices, list):
        return CommandResult.failure(
            code="validation_error",
            message=f"{field} must be a non-empty array of unique non-negative integers.",
            data={"field": field, "actual_type": type(indices).__name__},
        )
    if not indices:
        return CommandResult.failure(
            code="validation_error",
            message=f"{field} must not be empty.",
            data={"field": field, "reason": "empty_selection"},
        )
    if len(indices) > MAX_SKETCH_MUTATION_SELECTION_SIZE:
        return CommandResult.failure(
            code="validation_error",
            message=f"{field} exceeds the supported selection size.",
            data={
                "field": field,
                "maximum": MAX_SKETCH_MUTATION_SELECTION_SIZE,
                "actual": len(indices),
            },
        )
    seen: set[int] = set()
    validated: list[int] = []
    for position, value in enumerate(indices):
        item_field = f"{field}[{position}]"
        if isinstance(value, bool) or not isinstance(value, int):
            return CommandResult.failure(
                code="validation_error",
                message=f"{item_field} must be a strict non-negative integer.",
                data={"field": item_field, "actual_type": type(value).__name__},
            )
        if value < 0:
            return CommandResult.failure(
                code="validation_error",
                message=f"{item_field} must be non-negative.",
                data={"field": item_field, "value": value},
            )
        if value in seen:
            return CommandResult.failure(
                code="validation_error",
                message=f"{field} entries must be unique.",
                data={"field": item_field, "value": value, "reason": "duplicate_index"},
            )
        seen.add(value)
        validated.append(value)
    return tuple(sorted(validated))


def validate_set_sketch_geometry_construction_request(
    document_name: object,
    sketch_name: object,
    geometry_indices: object,
    construction: object,
) -> tuple[tuple[int, ...], bool] | CommandResult:
    """Validate desired-state construction input with a strict Boolean."""
    selection = validate_sketch_mutation_selection_request(
        document_name,
        sketch_name,
        geometry_indices,
        field="geometry_indices",
    )
    if isinstance(selection, CommandResult):
        return selection
    if not isinstance(construction, bool):
        return CommandResult.failure(
            code="validation_error",
            message="construction must be a strict Boolean.",
            data={"field": "construction", "actual_type": type(construction).__name__},
        )
    return selection, construction


__all__ = [
    "normalize_arc_angles_degrees",
    "validate_add_external_geometry_request",
    "validate_add_sketch_constraints_request",
    "validate_add_sketch_geometry_request",
    "validate_analyze_sketch_request",
    "validate_create_body_request",
    "validate_create_document_request",
    "validate_create_sketch_centered_rectangle_request",
    "validate_create_sketch_equilateral_triangle_request",
    "validate_create_sketch_rectangle_request",
    "validate_create_sketch_regular_polygon_request",
    "validate_create_sketch_request",
    "validate_create_sketch_rounded_rectangle_request",
    "validate_create_sketch_slot_request",
    "validate_document_history_request",
    "validate_document_reference",
    "validate_external_geometry_reference_request",
    "validate_object_reference",
    "validate_set_sketch_geometry_construction_request",
    "validate_sketch_mutation_selection_request",
    "validate_sketch_profile_analysis_request",
]
