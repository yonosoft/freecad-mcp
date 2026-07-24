"""FastMCP registration for Milestone 28 whole-sketch transform tools 55--58."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import ConfigDict

from freecad_mcp.commands import DocumentHandlers
from freecad_mcp.models import (
    SketchPoint2DInput,
    SketchTransformAngleDegrees,
    SketchTransformScaleFactor,
    SketchWholeMirrorReferenceInput,
)
from freecad_mcp.tool_registry import (
    MIRROR_SKETCH_TOOL,
    ROTATE_SKETCH_TOOL,
    SCALE_SKETCH_TOOL,
    TRANSLATE_SKETCH_TOOL,
)

_COPY_POLICY = (
    "The operation is copy-only: original geometry remains unchanged, sketch placement is "
    "not modified, and constraints, names, expressions, and consumers are not copied. "
    "Every internal geometry item is transformed together; unsupported or mixed internal "
    "geometry types (including ellipse, arc-of-ellipse, arc-of-parabola, arc-of-hyperbola, "
    "B-spline, and unknown future variants) refuse the entire operation before mutation. "
    "Success returns complete geometry and constraint mappings, creates one named undo step, "
    "and never saves."
)

TRANSLATE_SKETCH_DESCRIPTION = (
    "Append transformed independent copies of every internal geometry item by a finite "
    "non-zero sketch-local x/y displacement vector. " + _COPY_POLICY
)
ROTATE_SKETCH_DESCRIPTION = (
    "Append transformed independent copies of every internal geometry item by a signed "
    "rotation angle in degrees about one finite sketch-local centre. Zero, full-turn, and "
    "geometry-invariant overlapping copies are refused. " + _COPY_POLICY
)
SCALE_SKETCH_DESCRIPTION = (
    "Append transformed independent copies of every internal geometry item by a uniform "
    "scale factor about one finite centre. The factor must be at least 1e-6; factor 1 and "
    "invariant overlapping copies are refused. " + _COPY_POLICY
)
MIRROR_SKETCH_DESCRIPTION = (
    "Append transformed independent copies of every internal geometry item reflected about "
    "one built-in sketch reference: horizontal_axis, vertical_axis, or origin. "
    "Construction-line and internal-point references are refused. "
    "Geometry invariant under the reference is refused. " + _COPY_POLICY
)


def register_sketch_whole_transform_tools(
    server: FastMCP[Any],
    handlers: DocumentHandlers,
) -> None:
    """Append the authoritative Milestone 28 whole-sketch tools in 55--58 order."""

    @server.tool(
        name=TRANSLATE_SKETCH_TOOL,
        description=TRANSLATE_SKETCH_DESCRIPTION,
        structured_output=True,
    )
    def translate_sketch(
        document_name: str,
        sketch_name: str,
        displacement: SketchPoint2DInput,
    ) -> dict[str, object]:
        return handlers.translate_sketch.execute(document_name, sketch_name, displacement).to_dict()

    @server.tool(
        name=ROTATE_SKETCH_TOOL,
        description=ROTATE_SKETCH_DESCRIPTION,
        structured_output=True,
    )
    def rotate_sketch(
        document_name: str,
        sketch_name: str,
        center: SketchPoint2DInput,
        angle_degrees: SketchTransformAngleDegrees,
    ) -> dict[str, object]:
        return handlers.rotate_sketch.execute(
            document_name, sketch_name, center, angle_degrees
        ).to_dict()

    @server.tool(
        name=SCALE_SKETCH_TOOL,
        description=SCALE_SKETCH_DESCRIPTION,
        structured_output=True,
    )
    def scale_sketch(
        document_name: str,
        sketch_name: str,
        center: SketchPoint2DInput,
        factor: SketchTransformScaleFactor,
    ) -> dict[str, object]:
        return handlers.scale_sketch.execute(document_name, sketch_name, center, factor).to_dict()

    @server.tool(
        name=MIRROR_SKETCH_TOOL,
        description=MIRROR_SKETCH_DESCRIPTION,
        structured_output=True,
    )
    def mirror_sketch(
        document_name: str,
        sketch_name: str,
        reference: SketchWholeMirrorReferenceInput,
    ) -> dict[str, object]:
        return handlers.mirror_sketch.execute(document_name, sketch_name, reference).to_dict()

    for name in (
        TRANSLATE_SKETCH_TOOL,
        ROTATE_SKETCH_TOOL,
        SCALE_SKETCH_TOOL,
        MIRROR_SKETCH_TOOL,
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
    "MIRROR_SKETCH_DESCRIPTION",
    "ROTATE_SKETCH_DESCRIPTION",
    "SCALE_SKETCH_DESCRIPTION",
    "TRANSLATE_SKETCH_DESCRIPTION",
    "register_sketch_whole_transform_tools",
]
