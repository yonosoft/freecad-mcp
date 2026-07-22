"""FastMCP registration for Milestone 24 transform tools 43--48."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import ConfigDict

from freecad_mcp.commands import DocumentHandlers
from freecad_mcp.models import (
    SketchMirrorReferenceInput,
    SketchPoint2DInput,
    SketchPolarArrayInstanceCount,
    SketchRectangularArrayAxisCount,
    SketchTransformAngleDegrees,
    SketchTransformScaleFactor,
    SketchTransformSelection,
)
from freecad_mcp.tool_registry import (
    MIRROR_SKETCH_GEOMETRY_TOOL,
    POLAR_ARRAY_SKETCH_GEOMETRY_TOOL,
    RECTANGULAR_ARRAY_SKETCH_GEOMETRY_TOOL,
    ROTATE_SKETCH_GEOMETRY_TOOL,
    SCALE_SKETCH_GEOMETRY_TOOL,
    TRANSLATE_SKETCH_GEOMETRY_TOOL,
)

_COPY_POLICY = (
    "The operation is copy-only: originals, existing constraints, names, expressions, and "
    "consumers remain unchanged. Selected geometry with any constraint or unproven dependency "
    "is refused. Supported internal families are line segments, points, circles, and bounded "
    "circular arcs; construction state is preserved. Success returns complete geometry and "
    "constraint mappings, creates one named undo step, and never saves."
)

MIRROR_SKETCH_GEOMETRY_DESCRIPTION = (
    "Create independent mirror copies of a unique internal geometry selection about the "
    "horizontal axis, vertical axis, origin, an unselected internal construction line, or an "
    "unselected internal point. Geometry invariant under the reference and external references "
    "are refused. " + _COPY_POLICY
)
TRANSLATE_SKETCH_GEOMETRY_DESCRIPTION = (
    "Create independent copies displaced by one finite non-zero sketch-local x/y vector. "
    + _COPY_POLICY
)
ROTATE_SKETCH_GEOMETRY_DESCRIPTION = (
    "Create independent copies rotated about one finite sketch-local centre by a signed angle "
    "in degrees. Zero, full-turn, and geometry-invariant overlapping copies are refused. "
    + _COPY_POLICY
)
SCALE_SKETCH_GEOMETRY_DESCRIPTION = (
    "Create independent copies uniformly scaled about one finite centre. The factor must be at "
    "least 1e-6; factor 1 and invariant overlapping copies are refused. " + _COPY_POLICY
)
RECTANGULAR_ARRAY_SKETCH_GEOMETRY_DESCRIPTION = (
    "Create a bounded source-inclusive rectangular array with explicit row and column vectors. "
    "Copies are appended in row-major order and then canonical selection order. Counts are 1--20 "
    "per axis, at most 100 instances and 500 generated geometry items; duplicate offsets are "
    "refused. A 1x1 request is a transaction-free no-op. " + _COPY_POLICY
)
POLAR_ARRAY_SKETCH_GEOMETRY_DESCRIPTION = (
    "Create a bounded source-inclusive polar array about one finite centre using a signed step "
    "angle in degrees. Copies are appended by ascending instance then canonical selection order. "
    "Counts are 2--100 with at most 500 generated geometry items; any full-turn duplicate is "
    "refused, as is a geometry-invariant instance. " + _COPY_POLICY
)


def register_sketch_geometry_transform_tools(
    server: FastMCP[Any],
    handlers: DocumentHandlers,
) -> None:
    """Append the authoritative Milestone 24 tools in 43--48 order."""

    @server.tool(
        name=MIRROR_SKETCH_GEOMETRY_TOOL,
        description=MIRROR_SKETCH_GEOMETRY_DESCRIPTION,
        structured_output=True,
    )
    def mirror_sketch_geometry(
        document_name: str,
        sketch_name: str,
        geometry_indices: SketchTransformSelection,
        reference: SketchMirrorReferenceInput,
    ) -> dict[str, object]:
        return handlers.mirror_sketch_geometry.execute(
            document_name, sketch_name, geometry_indices, reference
        ).to_dict()

    @server.tool(
        name=TRANSLATE_SKETCH_GEOMETRY_TOOL,
        description=TRANSLATE_SKETCH_GEOMETRY_DESCRIPTION,
        structured_output=True,
    )
    def translate_sketch_geometry(
        document_name: str,
        sketch_name: str,
        geometry_indices: SketchTransformSelection,
        displacement: SketchPoint2DInput,
    ) -> dict[str, object]:
        return handlers.translate_sketch_geometry.execute(
            document_name, sketch_name, geometry_indices, displacement
        ).to_dict()

    @server.tool(
        name=ROTATE_SKETCH_GEOMETRY_TOOL,
        description=ROTATE_SKETCH_GEOMETRY_DESCRIPTION,
        structured_output=True,
    )
    def rotate_sketch_geometry(
        document_name: str,
        sketch_name: str,
        geometry_indices: SketchTransformSelection,
        center: SketchPoint2DInput,
        angle_degrees: SketchTransformAngleDegrees,
    ) -> dict[str, object]:
        return handlers.rotate_sketch_geometry.execute(
            document_name, sketch_name, geometry_indices, center, angle_degrees
        ).to_dict()

    @server.tool(
        name=SCALE_SKETCH_GEOMETRY_TOOL,
        description=SCALE_SKETCH_GEOMETRY_DESCRIPTION,
        structured_output=True,
    )
    def scale_sketch_geometry(
        document_name: str,
        sketch_name: str,
        geometry_indices: SketchTransformSelection,
        center: SketchPoint2DInput,
        factor: SketchTransformScaleFactor,
    ) -> dict[str, object]:
        return handlers.scale_sketch_geometry.execute(
            document_name, sketch_name, geometry_indices, center, factor
        ).to_dict()

    @server.tool(
        name=RECTANGULAR_ARRAY_SKETCH_GEOMETRY_TOOL,
        description=RECTANGULAR_ARRAY_SKETCH_GEOMETRY_DESCRIPTION,
        structured_output=True,
    )
    def rectangular_array_sketch_geometry(
        document_name: str,
        sketch_name: str,
        geometry_indices: SketchTransformSelection,
        rows: SketchRectangularArrayAxisCount,
        columns: SketchRectangularArrayAxisCount,
        row_displacement: SketchPoint2DInput,
        column_displacement: SketchPoint2DInput,
    ) -> dict[str, object]:
        return handlers.rectangular_array_sketch_geometry.execute(
            document_name,
            sketch_name,
            geometry_indices,
            rows,
            columns,
            row_displacement,
            column_displacement,
        ).to_dict()

    @server.tool(
        name=POLAR_ARRAY_SKETCH_GEOMETRY_TOOL,
        description=POLAR_ARRAY_SKETCH_GEOMETRY_DESCRIPTION,
        structured_output=True,
    )
    def polar_array_sketch_geometry(
        document_name: str,
        sketch_name: str,
        geometry_indices: SketchTransformSelection,
        center: SketchPoint2DInput,
        instance_count: SketchPolarArrayInstanceCount,
        step_angle_degrees: SketchTransformAngleDegrees,
    ) -> dict[str, object]:
        return handlers.polar_array_sketch_geometry.execute(
            document_name,
            sketch_name,
            geometry_indices,
            center,
            instance_count,
            step_angle_degrees,
        ).to_dict()

    for name in (
        MIRROR_SKETCH_GEOMETRY_TOOL,
        TRANSLATE_SKETCH_GEOMETRY_TOOL,
        ROTATE_SKETCH_GEOMETRY_TOOL,
        SCALE_SKETCH_GEOMETRY_TOOL,
        RECTANGULAR_ARRAY_SKETCH_GEOMETRY_TOOL,
        POLAR_ARRAY_SKETCH_GEOMETRY_TOOL,
    ):
        _forbid_extra_arguments(server, name)


def _forbid_extra_arguments(server: FastMCP[Any], tool_name: str) -> None:
    tool = server._tool_manager.get_tool(tool_name)
    if tool is None:  # pragma: no cover
        raise RuntimeError(f"FastMCP transform tool {tool_name!r} was not registered.")
    argument_model = tool.fn_metadata.arg_model
    argument_model.model_config = ConfigDict(**argument_model.model_config, extra="forbid")
    argument_model.model_rebuild(force=True)
    tool.parameters = argument_model.model_json_schema(by_alias=True)


__all__ = [
    "MIRROR_SKETCH_GEOMETRY_DESCRIPTION",
    "POLAR_ARRAY_SKETCH_GEOMETRY_DESCRIPTION",
    "RECTANGULAR_ARRAY_SKETCH_GEOMETRY_DESCRIPTION",
    "ROTATE_SKETCH_GEOMETRY_DESCRIPTION",
    "SCALE_SKETCH_GEOMETRY_DESCRIPTION",
    "TRANSLATE_SKETCH_GEOMETRY_DESCRIPTION",
    "register_sketch_geometry_transform_tools",
]
