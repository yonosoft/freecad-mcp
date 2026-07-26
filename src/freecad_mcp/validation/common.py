"""Coherent common validation definitions."""

from __future__ import annotations

import re

from pydantic import TypeAdapter

from freecad_mcp.core.result import CommandResult
from freecad_mcp.models import (
    ExternalGeometrySourceInput,
    SketchCenteredRectangleRequestInput,
    SketchConstraintInput,
    SketchEquilateralTriangleRequestInput,
    SketchGeometryInput,
    SketchGeometryUpdateInput,
    SketchMirrorReferenceInput,
    SketchPoint2DInput,
    SketchPolylineRequestInput,
    SketchRectangleRequestInput,
    SketchReferenceConstraintInput,
    SketchRegularPolygonRequestInput,
    SketchRoundedRectangleRequestInput,
    SketchSlotRequestInput,
    SketchWholeMirrorReferenceInput,
    SketchWholeMirrorRequestInput,
    SketchWholeRotateRequestInput,
    SketchWholeScaleRequestInput,
    SketchWholeTranslateRequestInput,
)

_INTERNAL_NAME_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")


_EXTERNAL_SUBELEMENT_PATTERN = re.compile(r"(?:Edge|Vertex)[1-9][0-9]*\Z")


_INTERNAL_NAME_RULE = "ASCII letter or underscore, followed by letters, digits, or underscores"


_SUPPORTED_SKETCH_GEOMETRY_INPUT_TYPES = {
    "arc_of_circle",
    "arc_of_ellipse",
    "arc_of_hyperbola",
    "arc_of_parabola",
    "b_spline",
    "circle",
    "ellipse",
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


_SKETCH_POLYLINE_REQUEST_ADAPTER: TypeAdapter[SketchPolylineRequestInput] = TypeAdapter(
    SketchPolylineRequestInput
)


_EXTERNAL_GEOMETRY_SOURCE_ADAPTER: TypeAdapter[ExternalGeometrySourceInput] = TypeAdapter(
    ExternalGeometrySourceInput
)


_SKETCH_POINT_2D_INPUT_ADAPTER: TypeAdapter[SketchPoint2DInput] = TypeAdapter(SketchPoint2DInput)


_SKETCH_MIRROR_REFERENCE_ADAPTER: TypeAdapter[SketchMirrorReferenceInput] = TypeAdapter(
    SketchMirrorReferenceInput
)


_SKETCH_WHOLE_MIRROR_REFERENCE_ADAPTER: TypeAdapter[SketchWholeMirrorReferenceInput] = TypeAdapter(
    SketchWholeMirrorReferenceInput
)


_SKETCH_WHOLE_TRANSLATE_REQUEST_ADAPTER: TypeAdapter[SketchWholeTranslateRequestInput] = (
    TypeAdapter(SketchWholeTranslateRequestInput)
)


_SKETCH_WHOLE_ROTATE_REQUEST_ADAPTER: TypeAdapter[SketchWholeRotateRequestInput] = TypeAdapter(
    SketchWholeRotateRequestInput
)


_SKETCH_WHOLE_SCALE_REQUEST_ADAPTER: TypeAdapter[SketchWholeScaleRequestInput] = TypeAdapter(
    SketchWholeScaleRequestInput
)


_SKETCH_WHOLE_MIRROR_REQUEST_ADAPTER: TypeAdapter[SketchWholeMirrorRequestInput] = TypeAdapter(
    SketchWholeMirrorRequestInput
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
