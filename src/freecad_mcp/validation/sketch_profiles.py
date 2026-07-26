"""Coherent sketch profiles validation definitions."""

from __future__ import annotations

import math

from pydantic import ValidationError

from freecad_mcp.core.result import CommandResult
from freecad_mcp.models import (
    SketchCenteredRectangleRequestInput,
    SketchEquilateralTriangleRequestInput,
    SketchPolylineRequestInput,
    SketchRectangleRequestInput,
    SketchRegularPolygonRequestInput,
    SketchRoundedRectangleRequestInput,
    SketchSlotRequestInput,
)
from freecad_mcp.validation.common import (
    _SKETCH_CENTERED_RECTANGLE_REQUEST_ADAPTER,
    _SKETCH_EQUILATERAL_TRIANGLE_REQUEST_ADAPTER,
    _SKETCH_POLYLINE_REQUEST_ADAPTER,
    _SKETCH_RECTANGLE_REQUEST_ADAPTER,
    _SKETCH_REGULAR_POLYGON_REQUEST_ADAPTER,
    _SKETCH_ROUNDED_RECTANGLE_REQUEST_ADAPTER,
    _SKETCH_SLOT_REQUEST_ADAPTER,
    _validate_object_name,
)
from freecad_mcp.validation.document import (
    validate_document_reference,
)


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


def validate_create_sketch_polyline_request(
    document_name: object,
    sketch_name: object,
    points: object,
    closed: object = False,
) -> CommandResult | SketchPolylineRequestInput:
    """Validate and parse one complete semantic polyline request."""
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
        parsed = _SKETCH_POLYLINE_REQUEST_ADAPTER.validate_python(
            {
                "document_name": document_name,
                "sketch_name": sketch_name,
                "points": points,
                "closed": closed,
            }
        )
    except ValidationError as exc:
        first_error = exc.errors(include_url=False)[0]
        location = ".".join(str(item) for item in first_error.get("loc", ()))
        return CommandResult.failure(
            code="invalid_polyline_parameters",
            message=(
                "Polyline parameters must be strict, finite, and contain only the "
                "documented fields."
            ),
            data={
                "field": location or "request",
                "reason": str(first_error.get("type", "invalid_parameters")),
            },
        )

    point_count = len(parsed.points)
    if parsed.closed:
        if point_count < 3:
            return CommandResult.failure(
                code="invalid_polyline_parameters",
                message="Closed polyline must have at least 3 points.",
                data={
                    "field": "points",
                    "point_count": point_count,
                    "reason": "closed_polyline_too_few_points",
                },
            )
    else:
        if point_count < 2:
            return CommandResult.failure(
                code="invalid_polyline_parameters",
                message="Open polyline must have at least 2 points.",
                data={
                    "field": "points",
                    "point_count": point_count,
                    "reason": "open_polyline_too_few_points",
                },
            )
    if point_count > 50:
        return CommandResult.failure(
            code="invalid_polyline_parameters",
            message="Polyline must have at most 50 points.",
            data={
                "field": "points",
                "point_count": point_count,
                "reason": "polyline_too_many_points",
            },
        )

    for index in range(point_count - 1):
        p0 = parsed.points[index]
        p1 = parsed.points[index + 1]
        distance = math.hypot(p0.x - p1.x, p0.y - p1.y)
        if distance < 1e-9:
            return CommandResult.failure(
                code="invalid_polyline_parameters",
                message="Consecutive polyline points must be distinct.",
                data={
                    "field": f"points[{index}]",
                    "reason": "consecutive_duplicate_points",
                },
            )

    if parsed.closed:
        p0 = parsed.points[0]
        p1 = parsed.points[-1]
        distance = math.hypot(p0.x - p1.x, p0.y - p1.y)
        if distance <= 1e-9:
            return CommandResult.failure(
                code="invalid_polyline_parameters",
                message="Closed polyline first and last points must be distinct.",
                data={
                    "field": "points",
                    "reason": "closed_polyline_first_last_coincident",
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
