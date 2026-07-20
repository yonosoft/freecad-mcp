"""FastMCP registration for controlled sketch editing tools 32--34."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import ConfigDict

from freecad_mcp.commands import DocumentHandlers
from freecad_mcp.models import (
    SketchConstraintInput,
    SketchConstraintValueInput,
    SketchGeometryUpdateInput,
    SketchMutationIndex,
)
from freecad_mcp.tool_registry import (
    REPLACE_SKETCH_CONSTRAINT_TOOL,
    UPDATE_SKETCH_CONSTRAINT_VALUE_TOOL,
    UPDATE_SKETCH_GEOMETRY_TOOL,
)

UPDATE_SKETCH_GEOMETRY_DESCRIPTION = (
    "Set one existing supported internal geometry element to a complete same-type final state. "
    "Supports line segments, points, circles, and bounded circular arcs. Construction state is "
    "preserved and external geometry is never addressed. A geometry with dependent constraints "
    "is refused unless the request is already a semantic no-op; dimensional changes belong in "
    "update_sketch_constraint_value. A change preserves current indices, verifies solver/profile "
    "impact, creates one 'Update sketch geometry' history step, and never saves."
)

REPLACE_SKETCH_CONSTRAINT_DESCRIPTION = (
    "Atomically replace one current constraint using the unchanged controlled 17-variant "
    "constraint union. Named, expression-sensitive, inactive, virtual, and reference constraints "
    "are refused. Exact no-ops create no transaction, and duplicates are refused before mutation. "
    "FreeCAD appends the replacement after deleting the selected constraint, so the result returns "
    "the replacement index and complete ordered survivor remapping. A change creates one 'Replace "
    "sketch constraint' history step and never saves."
)

UPDATE_SKETCH_CONSTRAINT_VALUE_DESCRIPTION = (
    "Set the absolute numeric value of one active driving distance, distance_x, distance_y, "
    "radius, "
    "diameter, or angle constraint. Lengths use millimetres and angles use degrees. Geometric, "
    "reference, virtual, inactive, and expression-sensitive constraints are refused. Exact no-ops "
    "create no transaction; a change preserves constraint identity, verifies solver/profile "
    "impact, "
    "creates one 'Update sketch constraint value' history step, and never saves."
)


def register_sketch_editing_tools(
    server: FastMCP[Any],
    handlers: DocumentHandlers,
) -> None:
    """Append Milestone 20 tools in authoritative 32--34 order."""

    @server.tool(
        name=UPDATE_SKETCH_GEOMETRY_TOOL,
        description=UPDATE_SKETCH_GEOMETRY_DESCRIPTION,
        structured_output=True,
    )
    def update_sketch_geometry(
        document_name: str,
        sketch_name: str,
        geometry_index: SketchMutationIndex,
        geometry: SketchGeometryUpdateInput,
    ) -> dict[str, object]:
        return handlers.update_sketch_geometry.execute(
            document_name=document_name,
            sketch_name=sketch_name,
            geometry_index=geometry_index,
            geometry=geometry,
        ).to_dict()

    @server.tool(
        name=REPLACE_SKETCH_CONSTRAINT_TOOL,
        description=REPLACE_SKETCH_CONSTRAINT_DESCRIPTION,
        structured_output=True,
    )
    def replace_sketch_constraint(
        document_name: str,
        sketch_name: str,
        constraint_index: SketchMutationIndex,
        replacement: SketchConstraintInput,
    ) -> dict[str, object]:
        return handlers.replace_sketch_constraint.execute(
            document_name=document_name,
            sketch_name=sketch_name,
            constraint_index=constraint_index,
            replacement=replacement,
        ).to_dict()

    @server.tool(
        name=UPDATE_SKETCH_CONSTRAINT_VALUE_TOOL,
        description=UPDATE_SKETCH_CONSTRAINT_VALUE_DESCRIPTION,
        structured_output=True,
    )
    def update_sketch_constraint_value(
        document_name: str,
        sketch_name: str,
        constraint_index: SketchMutationIndex,
        value: SketchConstraintValueInput,
    ) -> dict[str, object]:
        return handlers.update_sketch_constraint_value.execute(
            document_name=document_name,
            sketch_name=sketch_name,
            constraint_index=constraint_index,
            value=value,
        ).to_dict()

    _forbid_extra_arguments(server, UPDATE_SKETCH_GEOMETRY_TOOL)
    _forbid_extra_arguments(server, REPLACE_SKETCH_CONSTRAINT_TOOL)
    _forbid_extra_arguments(server, UPDATE_SKETCH_CONSTRAINT_VALUE_TOOL)


def _forbid_extra_arguments(server: FastMCP[Any], tool_name: str) -> None:
    tool = server._tool_manager.get_tool(tool_name)
    if tool is None:  # pragma: no cover
        raise RuntimeError(f"FastMCP sketch-editing tool {tool_name!r} was not registered.")
    argument_model = tool.fn_metadata.arg_model
    argument_model.model_config = ConfigDict(**argument_model.model_config, extra="forbid")
    argument_model.model_rebuild(force=True)
    tool.parameters = argument_model.model_json_schema(by_alias=True)


__all__ = [
    "REPLACE_SKETCH_CONSTRAINT_DESCRIPTION",
    "UPDATE_SKETCH_CONSTRAINT_VALUE_DESCRIPTION",
    "UPDATE_SKETCH_GEOMETRY_DESCRIPTION",
    "register_sketch_editing_tools",
]
