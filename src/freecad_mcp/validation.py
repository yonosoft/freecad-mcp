"""Explicit pure-Python validation for controlled MCP requests."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping

from pydantic import TypeAdapter, ValidationError

from freecad_mcp.constraint_expression_language import (
    ConstraintExpressionError,
    parse_constraint_expression,
    validate_constraint_identifier,
)
from freecad_mcp.core.result import CommandResult
from freecad_mcp.models import (
    MAX_SKETCH_CONSTRAINT_BATCH_SIZE,
    MAX_SKETCH_GEOMETRY_BATCH_SIZE,
    MAX_SKETCH_MUTATION_SELECTION_SIZE,
    MAX_SKETCH_RECTANGULAR_ARRAY_AXIS_COUNT,
    MAX_SKETCH_TRANSFORM_GENERATED_GEOMETRY,
    MAX_SKETCH_TRANSFORM_INSTANCES,
    MAX_SKETCH_TRANSFORM_SELECTION_SIZE,
    MIN_SKETCH_SCALE_FACTOR,
    AngleBetweenLinesConstraintInput,
    ArcOfCircleGeometryInput,
    ArcOfCircleGeometryUpdateInput,
    CircleGeometryInput,
    CircleGeometryUpdateInput,
    CoincidentConstraintInput,
    DistanceBetweenPointsConstraintInput,
    DistanceXBetweenPointsConstraintInput,
    DistanceYBetweenPointsConstraintInput,
    EqualConstraintInput,
    ExternalGeometrySourceInput,
    HorizontalPointsConstraintInput,
    LineSegmentGeometryInput,
    LineSegmentGeometryUpdateInput,
    ObjectSubelementExternalGeometrySourceInput,
    OriginPlane,
    ParallelConstraintInput,
    PerpendicularConstraintInput,
    PointGeometryInput,
    PointGeometryUpdateInput,
    PointOnObjectConstraintInput,
    SketchAnalysisRequestInput,
    SketchCenteredRectangleRequestInput,
    SketchConstraintGeometryReferenceInput,
    SketchConstraintInput,
    SketchConstraintPointReferenceInput,
    SketchEquilateralTriangleRequestInput,
    SketchGeometryExternalGeometrySourceInput,
    SketchGeometryInput,
    SketchGeometryUpdateInput,
    SketchHorizontalAxisReferenceInput,
    SketchMirrorReferenceInput,
    SketchPoint2DInput,
    SketchProfileAnalysisRequestInput,
    SketchRectangleRequestInput,
    SketchReferenceConstraintInput,
    SketchRegularPolygonRequestInput,
    SketchRoundedRectangleRequestInput,
    SketchSlotRequestInput,
    SketchTopologyEndpoint,
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
_SKETCH_REFERENCE_CONSTRAINT_INPUT_ADAPTER: TypeAdapter[SketchReferenceConstraintInput] = (
    TypeAdapter(SketchReferenceConstraintInput)
)
_SKETCH_GEOMETRY_UPDATE_INPUT_ADAPTER: TypeAdapter[SketchGeometryUpdateInput] = TypeAdapter(
    SketchGeometryUpdateInput
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
_SKETCH_POINT_2D_INPUT_ADAPTER: TypeAdapter[SketchPoint2DInput] = TypeAdapter(SketchPoint2DInput)
_SKETCH_MIRROR_REFERENCE_ADAPTER: TypeAdapter[SketchMirrorReferenceInput] = TypeAdapter(
    SketchMirrorReferenceInput
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


def validate_add_sketch_reference_constraints_request(
    document_name: object,
    sketch_name: object,
    constraints: object,
) -> CommandResult | tuple[SketchReferenceConstraintInput, ...]:
    """Validate the strict 17-way reference-aware batch before adapter access."""
    document_error = validate_document_reference(document_name)
    if document_error is not None:
        return document_error
    sketch_error = _validate_object_name(sketch_name, field="sketch_name", subject="Sketch")
    if sketch_error is not None:
        return sketch_error
    if not isinstance(constraints, list):
        return CommandResult.failure(
            code="validation_error",
            message="Constraints must be a non-empty array.",
            data={"field": "constraints", "actual_type": type(constraints).__name__},
        )
    if not constraints or len(constraints) > MAX_SKETCH_CONSTRAINT_BATCH_SIZE:
        reason = "empty_constraint_batch" if not constraints else "constraint_batch_too_large"
        return CommandResult.failure(
            code="validation_error",
            message="Constraints must contain between 1 and 100 items.",
            data={
                "field": "constraints",
                "minimum_items": 1,
                "maximum_items": MAX_SKETCH_CONSTRAINT_BATCH_SIZE,
                "actual_items": len(constraints),
                "reason": reason,
            },
        )

    parsed_items: list[SketchReferenceConstraintInput] = []
    serialized: set[str] = set()
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
            parsed = _SKETCH_REFERENCE_CONSTRAINT_INPUT_ADAPTER.validate_python(item)
        except ValidationError as exc:
            return _reference_constraint_model_validation_error(index, exc)

        semantic_error = _validate_reference_constraint_semantics(index, parsed)
        if semantic_error is not None:
            return semantic_error
        key = parsed.model_dump_json()
        if key in serialized:
            return CommandResult.failure(
                code="validation_error",
                message="The reference-constraint batch contains a duplicate item.",
                data={
                    "field": f"constraints[{index}]",
                    "constraint_index": index,
                    "reason": "duplicate_constraint",
                },
            )
        serialized.add(key)
        parsed_items.append(parsed)
    return tuple(parsed_items)


def _reference_constraint_model_validation_error(
    index: int,
    exc: ValidationError,
) -> CommandResult:
    error = exc.errors(include_url=False, include_context=False, include_input=False)[0]
    location = [
        str(part)
        for part in error.get("loc", ())
        if str(part) not in _SUPPORTED_SKETCH_CONSTRAINT_INPUT_TYPES
        and str(part)
        not in {"line_length", "point_to_origin", "between_points", "line_angle", "between_lines"}
    ]
    field = f"constraints[{index}]" + ("." + ".".join(location) if location else "")
    return CommandResult.failure(
        code="validation_error",
        message=f"Reference constraint item {index} is malformed.",
        data={
            "field": field,
            "constraint_index": index,
            "reason": str(error.get("type", "invalid_reference_constraint_input")),
        },
    )


def _validate_reference_constraint_semantics(
    index: int,
    item: SketchReferenceConstraintInput,
) -> CommandResult | None:
    first = getattr(item, "first", None)
    second = getattr(item, "second", None)
    if first is not None and second is not None and first == second:
        return _reference_semantic_error(index, "identical_operands")

    if item.type == "coincident":
        point_count = sum(hasattr(value, "geometry") for value in (first, second))
        if point_count == 0:
            return _reference_semantic_error(index, "same_origin_reference")
    elif item.type == "point_on_object":
        first_is_point = hasattr(first, "geometry")
        second_is_point = hasattr(second, "geometry")
        first_is_axis = getattr(first, "reference", None) in {
            "horizontal_axis",
            "vertical_axis",
        }
        second_is_axis = getattr(second, "reference", None) in {
            "horizontal_axis",
            "vertical_axis",
        }
        second_is_geometry = getattr(second, "kind", None) in {"internal", "external"}
        if not (
            (first_is_point and (second_is_axis or second_is_geometry))
            or (first_is_axis and second_is_point)
        ):
            return _reference_semantic_error(index, "unsupported_operand_role")
    elif item.type == "symmetric":
        about = item.about
        if about in {first, second}:
            return _reference_semantic_error(index, "identical_symmetry_reference")
    return None


def _reference_semantic_error(index: int, reason: str) -> CommandResult:
    return CommandResult.failure(
        code="validation_error",
        message="The reference constraint operands are not semantically distinct.",
        data={
            "field": f"constraints[{index}]",
            "constraint_index": index,
            "reason": reason,
        },
    )


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


def _validate_strict_mutation_index(value: object, *, field: str) -> int | CommandResult:
    if isinstance(value, bool) or not isinstance(value, int):
        return CommandResult.failure(
            code="validation_error",
            message=f"{field} must be a strict non-negative integer.",
            data={"field": field, "actual_type": type(value).__name__},
        )
    if value < 0:
        return CommandResult.failure(
            code="validation_error",
            message=f"{field} must be non-negative.",
            data={"field": field, "value": value},
        )
    return value


def validate_update_sketch_geometry_request(
    document_name: object,
    sketch_name: object,
    geometry_index: object,
    geometry: object,
) -> tuple[int, SketchGeometryUpdateInput] | CommandResult:
    """Validate one same-type complete geometry replacement state."""
    reference_error = validate_object_reference(document_name, sketch_name)
    if reference_error is not None:
        return reference_error
    index = _validate_strict_mutation_index(geometry_index, field="geometry_index")
    if isinstance(index, CommandResult):
        return index
    if isinstance(geometry, Mapping):
        discriminator = geometry.get("type")
        if (
            isinstance(discriminator, str)
            and discriminator not in _SUPPORTED_SKETCH_GEOMETRY_INPUT_TYPES
        ):
            return CommandResult.failure(
                code="validation_error",
                message="geometry uses an unsupported type.",
                data={
                    "field": "geometry.type",
                    "actual_value": discriminator,
                    "allowed": sorted(_SUPPORTED_SKETCH_GEOMETRY_INPUT_TYPES),
                },
            )
    try:
        parsed = _SKETCH_GEOMETRY_UPDATE_INPUT_ADAPTER.validate_python(geometry)
    except ValidationError as exc:
        error = exc.errors(include_url=False, include_context=False, include_input=False)[0]
        location = [
            str(part)
            for part in error.get("loc", ())
            if str(part) not in _SUPPORTED_SKETCH_GEOMETRY_INPUT_TYPES
        ]
        return CommandResult.failure(
            code="validation_error",
            message="geometry is malformed.",
            data={
                "field": "geometry" + ("." + ".".join(location) if location else ""),
                "geometry_index": index,
                "reason": str(error.get("type", "invalid_geometry_input")),
            },
        )
    if isinstance(parsed, LineSegmentGeometryUpdateInput) and (
        parsed.start.x == parsed.end.x and parsed.start.y == parsed.end.y
    ):
        return CommandResult.failure(
            code="validation_error",
            message="geometry is a zero-length line segment.",
            data={"field": "geometry", "geometry_index": index, "reason": "zero_length_line"},
        )
    if isinstance(parsed, ArcOfCircleGeometryUpdateInput):
        try:
            normalize_arc_angles_degrees(parsed.start_angle_degrees, parsed.end_angle_degrees)
        except ValueError:
            return CommandResult.failure(
                code="validation_error",
                message="geometry has collapsing arc angles.",
                data={
                    "field": "geometry",
                    "geometry_index": index,
                    "reason": "arc_angles_collapse",
                },
            )
    if not isinstance(
        parsed,
        (
            LineSegmentGeometryUpdateInput,
            PointGeometryUpdateInput,
            CircleGeometryUpdateInput,
            ArcOfCircleGeometryUpdateInput,
        ),
    ):
        return CommandResult.failure(
            code="validation_error",
            message="geometry uses an unsupported type.",
            data={"field": "geometry.type"},
        )
    return index, parsed


def validate_sketch_topology_point_request(
    document_name: object,
    sketch_name: object,
    geometry_index: object,
    point: object,
    *,
    field: str,
) -> tuple[int, SketchPoint2DInput] | CommandResult:
    """Validate a strict internal index and one finite sketch-coordinate point."""
    reference_error = validate_object_reference(document_name, sketch_name)
    if reference_error is not None:
        return reference_error
    index = _validate_strict_mutation_index(geometry_index, field="geometry_index")
    if isinstance(index, CommandResult):
        return index
    try:
        parsed = _SKETCH_POINT_2D_INPUT_ADAPTER.validate_python(point)
    except ValidationError as exc:
        error = exc.errors(include_url=False, include_context=False, include_input=False)[0]
        location = ".".join(str(part) for part in error.get("loc", ()))
        return CommandResult.failure(
            code="validation_error",
            message=f"{field} must contain exactly finite strict x and y coordinates.",
            data={
                "field": field + (f".{location}" if location else ""),
                "geometry_index": index,
                "reason": str(error.get("type", "invalid_point")),
            },
        )
    return index, parsed


def validate_fillet_sketch_geometry_request(
    document_name: object,
    sketch_name: object,
    first_geometry_index: object,
    radius: object,
) -> tuple[int, float] | CommandResult:
    """Validate one strict line-line fillet request."""
    reference_error = validate_object_reference(document_name, sketch_name)
    if reference_error is not None:
        return reference_error
    index = _validate_strict_mutation_index(first_geometry_index, field="first_geometry_index")
    if isinstance(index, CommandResult):
        return index
    if isinstance(radius, bool) or not isinstance(radius, (int, float)):
        return CommandResult.failure(
            code="validation_error",
            message="radius must be a finite positive number.",
            data={
                "field": "radius",
                "actual_type": type(radius).__name__,
            },
        )
    value = float(radius)
    if not math.isfinite(value) or value <= 0:
        return CommandResult.failure(
            code="validation_error",
            message="radius must be a finite positive number.",
            data={
                "field": "radius",
                "reason": "non_positive_or_non_finite",
            },
        )
    return index, value


def validate_chamfer_sketch_geometry_request(
    document_name: object,
    sketch_name: object,
    first_geometry_index: object,
    distance: object,
) -> tuple[int, float] | CommandResult:
    """Validate one strict line-line chamfer request."""
    reference_error = validate_object_reference(document_name, sketch_name)
    if reference_error is not None:
        return reference_error
    index = _validate_strict_mutation_index(first_geometry_index, field="first_geometry_index")
    if isinstance(index, CommandResult):
        return index
    if isinstance(distance, bool) or not isinstance(distance, (int, float)):
        return CommandResult.failure(
            code="validation_error",
            message="distance must be a finite positive number.",
            data={
                "field": "distance",
                "actual_type": type(distance).__name__,
            },
        )
    value = float(distance)
    if not math.isfinite(value) or value <= 0:
        return CommandResult.failure(
            code="validation_error",
            message="distance must be a finite positive number.",
            data={
                "field": "distance",
                "reason": "non_positive_or_non_finite",
            },
        )
    return index, value


def validate_extend_sketch_geometry_request(
    document_name: object,
    sketch_name: object,
    geometry_index: object,
    endpoint: object,
    target_point: object,
) -> tuple[int, SketchTopologyEndpoint, SketchPoint2DInput] | CommandResult:
    """Validate the strict line-extension endpoint and explicit target point."""
    validated = validate_sketch_topology_point_request(
        document_name,
        sketch_name,
        geometry_index,
        target_point,
        field="target_point",
    )
    if isinstance(validated, CommandResult):
        return validated
    index, point = validated
    if not isinstance(endpoint, str) or endpoint not in {
        SketchTopologyEndpoint.START.value,
        SketchTopologyEndpoint.END.value,
    }:
        return CommandResult.failure(
            code="validation_error",
            message="endpoint must be exactly 'start' or 'end'.",
            data={
                "field": "endpoint",
                "actual_type": type(endpoint).__name__,
                "allowed": ["start", "end"],
            },
        )
    return index, SketchTopologyEndpoint(endpoint), point


def validate_mirror_sketch_geometry_request(
    document_name: object,
    sketch_name: object,
    geometry_indices: object,
    reference: object,
) -> tuple[tuple[int, ...], SketchMirrorReferenceInput] | CommandResult:
    """Validate a bounded unique selection and strict discriminated mirror reference."""
    selection = _validate_transform_selection(document_name, sketch_name, geometry_indices)
    if isinstance(selection, CommandResult):
        return selection
    try:
        parsed = _SKETCH_MIRROR_REFERENCE_ADAPTER.validate_python(reference)
    except ValidationError as exc:
        return _transform_model_validation_error("reference", exc)
    return selection, parsed


def validate_translate_sketch_geometry_request(
    document_name: object,
    sketch_name: object,
    geometry_indices: object,
    displacement: object,
) -> tuple[tuple[int, ...], SketchPoint2DInput] | CommandResult:
    """Validate one bounded transform selection and finite displacement vector."""
    selection = _validate_transform_selection(document_name, sketch_name, geometry_indices)
    if isinstance(selection, CommandResult):
        return selection
    parsed = _validate_transform_point(displacement, field="displacement")
    if isinstance(parsed, CommandResult):
        return parsed
    return selection, parsed


def validate_rotate_sketch_geometry_request(
    document_name: object,
    sketch_name: object,
    geometry_indices: object,
    center: object,
    angle_degrees: object,
) -> tuple[tuple[int, ...], SketchPoint2DInput, float] | CommandResult:
    """Validate one bounded selection, finite centre, and finite signed degree angle."""
    selection = _validate_transform_selection(document_name, sketch_name, geometry_indices)
    if isinstance(selection, CommandResult):
        return selection
    parsed_center = _validate_transform_point(center, field="center")
    if isinstance(parsed_center, CommandResult):
        return parsed_center
    angle = _validate_transform_number(angle_degrees, field="angle_degrees")
    if isinstance(angle, CommandResult):
        return angle
    return selection, parsed_center, angle


def validate_scale_sketch_geometry_request(
    document_name: object,
    sketch_name: object,
    geometry_indices: object,
    center: object,
    factor: object,
) -> tuple[tuple[int, ...], SketchPoint2DInput, float] | CommandResult:
    """Validate one bounded selection, finite centre, and supported positive scale."""
    selection = _validate_transform_selection(document_name, sketch_name, geometry_indices)
    if isinstance(selection, CommandResult):
        return selection
    parsed_center = _validate_transform_point(center, field="center")
    if isinstance(parsed_center, CommandResult):
        return parsed_center
    parsed_factor = _validate_transform_number(factor, field="factor")
    if isinstance(parsed_factor, CommandResult):
        return parsed_factor
    if parsed_factor < MIN_SKETCH_SCALE_FACTOR:
        return CommandResult.failure(
            code="validation_error",
            message="factor must be at least the controlled positive minimum.",
            data={
                "field": "factor",
                "minimum": MIN_SKETCH_SCALE_FACTOR,
                "actual": parsed_factor,
                "reason": "unsupported_scale_factor",
            },
        )
    return selection, parsed_center, parsed_factor


def validate_rectangular_array_sketch_geometry_request(
    document_name: object,
    sketch_name: object,
    geometry_indices: object,
    rows: object,
    columns: object,
    row_displacement: object,
    column_displacement: object,
) -> (
    tuple[
        tuple[int, ...],
        int,
        int,
        SketchPoint2DInput,
        SketchPoint2DInput,
    ]
    | CommandResult
):
    """Validate bounded row-major rectangular-array inputs."""
    selection = _validate_transform_selection(document_name, sketch_name, geometry_indices)
    if isinstance(selection, CommandResult):
        return selection
    parsed_rows = _validate_array_count(rows, field="rows", minimum=1)
    if isinstance(parsed_rows, CommandResult):
        return parsed_rows
    parsed_columns = _validate_array_count(columns, field="columns", minimum=1)
    if isinstance(parsed_columns, CommandResult):
        return parsed_columns
    instances = parsed_rows * parsed_columns
    generated = len(selection) * (instances - 1)
    if instances > MAX_SKETCH_TRANSFORM_INSTANCES or (
        generated > MAX_SKETCH_TRANSFORM_GENERATED_GEOMETRY
    ):
        return _array_limit_error(instances, generated)
    parsed_row = _validate_transform_point(row_displacement, field="row_displacement")
    if isinstance(parsed_row, CommandResult):
        return parsed_row
    parsed_column = _validate_transform_point(
        column_displacement,
        field="column_displacement",
    )
    if isinstance(parsed_column, CommandResult):
        return parsed_column
    return selection, parsed_rows, parsed_columns, parsed_row, parsed_column


def validate_polar_array_sketch_geometry_request(
    document_name: object,
    sketch_name: object,
    geometry_indices: object,
    center: object,
    instance_count: object,
    step_angle_degrees: object,
) -> tuple[tuple[int, ...], SketchPoint2DInput, int, float] | CommandResult:
    """Validate bounded source-inclusive polar-array inputs."""
    selection = _validate_transform_selection(document_name, sketch_name, geometry_indices)
    if isinstance(selection, CommandResult):
        return selection
    parsed_center = _validate_transform_point(center, field="center")
    if isinstance(parsed_center, CommandResult):
        return parsed_center
    parsed_count = _validate_array_count(instance_count, field="instance_count", minimum=2)
    if isinstance(parsed_count, CommandResult):
        return parsed_count
    generated = len(selection) * (parsed_count - 1)
    if generated > MAX_SKETCH_TRANSFORM_GENERATED_GEOMETRY:
        return _array_limit_error(parsed_count, generated)
    angle = _validate_transform_number(step_angle_degrees, field="step_angle_degrees")
    if isinstance(angle, CommandResult):
        return angle
    return selection, parsed_center, parsed_count, angle


def _validate_transform_selection(
    document_name: object,
    sketch_name: object,
    geometry_indices: object,
) -> tuple[int, ...] | CommandResult:
    selection = validate_sketch_mutation_selection_request(
        document_name,
        sketch_name,
        geometry_indices,
        field="geometry_indices",
    )
    if isinstance(selection, CommandResult):
        return selection
    if len(selection) > MAX_SKETCH_TRANSFORM_SELECTION_SIZE:
        return CommandResult.failure(
            code="validation_error",
            message="geometry_indices exceeds the transform selection limit.",
            data={
                "field": "geometry_indices",
                "maximum": MAX_SKETCH_TRANSFORM_SELECTION_SIZE,
                "actual": len(selection),
            },
        )
    return selection


def _validate_transform_point(value: object, *, field: str) -> SketchPoint2DInput | CommandResult:
    try:
        return _SKETCH_POINT_2D_INPUT_ADAPTER.validate_python(value)
    except ValidationError as exc:
        return _transform_model_validation_error(field, exc)


def _validate_transform_number(value: object, *, field: str) -> float | CommandResult:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return CommandResult.failure(
            code="validation_error",
            message=f"{field} must be a finite number.",
            data={"field": field, "actual_type": type(value).__name__},
        )
    result = float(value)
    if not math.isfinite(result):
        return CommandResult.failure(
            code="validation_error",
            message=f"{field} must be finite.",
            data={"field": field, "reason": "non_finite"},
        )
    return result


def _validate_array_count(value: object, *, field: str, minimum: int) -> int | CommandResult:
    if isinstance(value, bool) or not isinstance(value, int):
        return CommandResult.failure(
            code="validation_error",
            message=f"{field} must be a strict integer.",
            data={"field": field, "actual_type": type(value).__name__},
        )
    maximum = (
        MAX_SKETCH_RECTANGULAR_ARRAY_AXIS_COUNT
        if field in {"rows", "columns"}
        else MAX_SKETCH_TRANSFORM_INSTANCES
    )
    if value < minimum or value > maximum:
        return CommandResult.failure(
            code="validation_error",
            message=f"{field} is outside the controlled array limit.",
            data={"field": field, "minimum": minimum, "maximum": maximum, "actual": value},
        )
    return value


def _array_limit_error(instances: int, generated: int) -> CommandResult:
    return CommandResult.failure(
        code="validation_error",
        message="The requested array exceeds the controlled instance or geometry limit.",
        data={
            "field": "geometry_indices",
            "instance_count": instances,
            "generated_geometry_count": generated,
            "maximum_instances": MAX_SKETCH_TRANSFORM_INSTANCES,
            "maximum_generated_geometry": MAX_SKETCH_TRANSFORM_GENERATED_GEOMETRY,
            "reason": "array_limit_exceeded",
        },
    )


def _transform_model_validation_error(field: str, exc: ValidationError) -> CommandResult:
    error = exc.errors(include_url=False, include_context=False, include_input=False)[0]
    location = ".".join(str(item) for item in error.get("loc", ()))
    return CommandResult.failure(
        code="validation_error",
        message=f"{field} must contain only the documented strict finite fields.",
        data={
            "field": field + (f".{location}" if location else ""),
            "reason": str(error.get("type", "invalid_transform_input")),
        },
    )


def validate_replace_sketch_constraint_request(
    document_name: object,
    sketch_name: object,
    constraint_index: object,
    replacement: object,
) -> tuple[int, SketchConstraintInput] | CommandResult:
    """Validate one index and one existing controlled 17-way constraint input."""
    index = _validate_strict_mutation_index(constraint_index, field="constraint_index")
    if isinstance(index, CommandResult):
        reference_error = validate_object_reference(document_name, sketch_name)
        return reference_error if reference_error is not None else index
    parsed = validate_add_sketch_constraints_request(
        document_name,
        sketch_name,
        [replacement],
    )
    if isinstance(parsed, CommandResult):
        data = dict(parsed.data)
        field = data.get("field")
        if isinstance(field, str):
            data["field"] = field.replace("constraints[0]", "replacement", 1)
        data["constraint_index"] = index
        return CommandResult.failure(
            code=parsed.code,
            message=parsed.message.replace("Constraint item 0", "replacement"),
            data=data,
        )
    return index, parsed[0]


def validate_set_sketch_constraint_driving_request(
    document_name: object,
    sketch_name: object,
    constraint_index: object,
    driving: object,
) -> tuple[int, bool] | CommandResult:
    """Validate strict index and Boolean driving intent."""
    reference_error = validate_object_reference(document_name, sketch_name)
    if reference_error is not None:
        return reference_error
    index = _validate_strict_mutation_index(constraint_index, field="constraint_index")
    if isinstance(index, CommandResult):
        return index
    if not isinstance(driving, bool):
        return CommandResult.failure(
            code="validation_error",
            message="driving must be a strict Boolean.",
            data={"field": "driving", "actual_type": type(driving).__name__},
        )
    return index, driving


def validate_set_sketch_constraint_active_request(
    document_name: object,
    sketch_name: object,
    constraint_index: object,
    active: object,
) -> tuple[int, bool] | CommandResult:
    reference_error = validate_object_reference(document_name, sketch_name)
    if reference_error is not None:
        return reference_error
    index = _validate_strict_mutation_index(constraint_index, field="constraint_index")
    if isinstance(index, CommandResult):
        return index
    if not isinstance(active, bool):
        return CommandResult.failure(
            code="validation_error",
            message="active must be a strict Boolean.",
            data={"field": "active", "actual_type": type(active).__name__},
        )
    return index, active


def validate_set_sketch_constraint_virtual_space_request(
    document_name: object,
    sketch_name: object,
    constraint_index: object,
    virtual: object,
) -> tuple[int, bool] | CommandResult:
    reference_error = validate_object_reference(document_name, sketch_name)
    if reference_error is not None:
        return reference_error
    index = _validate_strict_mutation_index(constraint_index, field="constraint_index")
    if isinstance(index, CommandResult):
        return index
    if not isinstance(virtual, bool):
        return CommandResult.failure(
            code="validation_error",
            message="virtual must be a strict Boolean.",
            data={"field": "virtual", "actual_type": type(virtual).__name__},
        )
    return index, virtual


def validate_update_sketch_constraint_value_request(
    document_name: object,
    sketch_name: object,
    constraint_index: object,
    value: object,
) -> tuple[int, float] | CommandResult:
    """Validate an absolute finite numeric datum using public degree/mm conventions."""
    reference_error = validate_object_reference(document_name, sketch_name)
    if reference_error is not None:
        return reference_error
    index = _validate_strict_mutation_index(constraint_index, field="constraint_index")
    if isinstance(index, CommandResult):
        return index
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return CommandResult.failure(
            code="validation_error",
            message="value must be a finite number.",
            data={"field": "value", "actual_type": type(value).__name__},
        )
    converted = float(value)
    if not math.isfinite(converted):
        return CommandResult.failure(
            code="validation_error",
            message="value must be finite.",
            data={"field": "value", "reason": "non_finite_value"},
        )
    return index, converted


def validate_set_sketch_constraint_name_request(
    document_name: object,
    sketch_name: object,
    constraint_index: object,
    name: object,
) -> tuple[int, str | None] | CommandResult:
    """Validate one exact scalar constraint name assignment or null clear."""
    reference_error = validate_object_reference(document_name, sketch_name)
    if reference_error is not None:
        return reference_error
    index = _validate_strict_mutation_index(constraint_index, field="constraint_index")
    if isinstance(index, CommandResult):
        return index
    if name is None:
        return index, None
    if not isinstance(name, str):
        return CommandResult.failure(
            code="validation_error",
            message="name must be a controlled identifier or null.",
            data={"field": "name", "actual_type": type(name).__name__},
        )
    if not validate_constraint_identifier(name):
        return CommandResult.failure(
            code="validation_error",
            message="name must be a controlled ASCII identifier of at most 64 characters.",
            data={"field": "name", "reason": "invalid_constraint_name"},
        )
    return index, name


def validate_set_sketch_constraint_expression_request(
    document_name: object,
    sketch_name: object,
    constraint_index: object,
    expression: object,
) -> tuple[int, str] | CommandResult:
    """Parse and canonicalize one finite public expression before dispatch."""
    reference_error = validate_object_reference(document_name, sketch_name)
    if reference_error is not None:
        return reference_error
    index = _validate_strict_mutation_index(constraint_index, field="constraint_index")
    if isinstance(index, CommandResult):
        return index
    if not isinstance(expression, str):
        return CommandResult.failure(
            code="validation_error",
            message="expression must be a string in the controlled expression grammar.",
            data={"field": "expression", "actual_type": type(expression).__name__},
        )
    try:
        parsed = parse_constraint_expression(expression)
    except ConstraintExpressionError as exc:
        data: dict[str, object] = {
            "field": "expression",
            "reason": exc.reason,
        }
        if exc.position is not None:
            data["position"] = exc.position
        return CommandResult.failure(
            code="validation_error",
            message="expression is outside the controlled expression grammar.",
            data=data,
        )
    return index, parsed.canonical


def validate_sketch_constraint_expression_locator(
    document_name: object,
    sketch_name: object,
    constraint_index: object,
) -> int | CommandResult:
    """Validate one document/sketch/current-constraint locator."""
    reference_error = validate_object_reference(document_name, sketch_name)
    if reference_error is not None:
        return reference_error
    return _validate_strict_mutation_index(constraint_index, field="constraint_index")


__all__ = [
    "normalize_arc_angles_degrees",
    "validate_add_external_geometry_request",
    "validate_add_sketch_constraints_request",
    "validate_add_sketch_geometry_request",
    "validate_add_sketch_reference_constraints_request",
    "validate_analyze_sketch_request",
    "validate_chamfer_sketch_geometry_request",
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
    "validate_extend_sketch_geometry_request",
    "validate_external_geometry_reference_request",
    "validate_fillet_sketch_geometry_request",
    "validate_mirror_sketch_geometry_request",
    "validate_object_reference",
    "validate_polar_array_sketch_geometry_request",
    "validate_rectangular_array_sketch_geometry_request",
    "validate_replace_sketch_constraint_request",
    "validate_rotate_sketch_geometry_request",
    "validate_scale_sketch_geometry_request",
    "validate_set_sketch_constraint_active_request",
    "validate_set_sketch_constraint_driving_request",
    "validate_set_sketch_constraint_expression_request",
    "validate_set_sketch_constraint_name_request",
    "validate_set_sketch_constraint_virtual_space_request",
    "validate_set_sketch_geometry_construction_request",
    "validate_sketch_constraint_expression_locator",
    "validate_sketch_mutation_selection_request",
    "validate_sketch_profile_analysis_request",
    "validate_sketch_topology_point_request",
    "validate_translate_sketch_geometry_request",
    "validate_update_sketch_constraint_value_request",
    "validate_update_sketch_geometry_request",
]
