"""FastMCP registration for controlled sketch mutation tools 29--31."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import ConfigDict

from freecad_mcp.commands import DocumentHandlers
from freecad_mcp.models import SketchConstructionState, SketchMutationIndexSelection
from freecad_mcp.tool_registry import (
    REMOVE_SKETCH_CONSTRAINTS_TOOL,
    REMOVE_SKETCH_GEOMETRY_TOOL,
    SET_SKETCH_GEOMETRY_CONSTRUCTION_TOOL,
)

REMOVE_SKETCH_CONSTRAINTS_DESCRIPTION = (
    "Atomically remove a non-empty unique selection of current constraint indices. Indices refer "
    "to the pre-call sketch and are deleted in a safe deterministic order. Constraints with an "
    "attached or downstream expression dependency, or unsupported readback, are refused before "
    "mutation. Returns controlled removed summaries, survivor remapping, solver state, and one "
    "'Remove sketch constraints' history step without deleting geometry or saving."
)

REMOVE_SKETCH_GEOMETRY_DESCRIPTION = (
    "Atomically remove selected current internal sketch geometry only when no selected element is "
    "used by a constraint. External-reference numbers and native negative IDs are not accepted; "
    "use remove_external_geometry for external references. Dependent constraints are reported "
    "exactly and never cascade-deleted. Returns controlled removed summaries, geometry and "
    "constraint survivor remapping, profile impact, and one 'Remove sketch geometry' history step."
)

SET_SKETCH_GEOMETRY_CONSTRUCTION_DESCRIPTION = (
    "Set a non-empty unique selection of current internal geometry to the requested strict Boolean "
    "construction state. The Boolean is a desired final state, not a blind toggle. Mixed "
    "selections change only mismatched geometry and report already-correct members. An "
    "all-already-correct request returns a controlled no-change result with no transaction. "
    "External geometry is never eligible and successful changes form one 'Set sketch geometry "
    "construction' history step."
)


def register_sketch_removal_tools(
    server: FastMCP[Any],
    handlers: DocumentHandlers,
) -> None:
    """Append Milestone 19 tools in authoritative 29--31 order."""

    @server.tool(
        name=REMOVE_SKETCH_CONSTRAINTS_TOOL,
        description=REMOVE_SKETCH_CONSTRAINTS_DESCRIPTION,
        structured_output=True,
    )
    def remove_sketch_constraints(
        document_name: str,
        sketch_name: str,
        constraint_indices: SketchMutationIndexSelection,
    ) -> dict[str, object]:
        return handlers.remove_sketch_constraints.execute(
            document_name=document_name,
            sketch_name=sketch_name,
            constraint_indices=constraint_indices,
        ).to_dict()

    @server.tool(
        name=REMOVE_SKETCH_GEOMETRY_TOOL,
        description=REMOVE_SKETCH_GEOMETRY_DESCRIPTION,
        structured_output=True,
    )
    def remove_sketch_geometry(
        document_name: str,
        sketch_name: str,
        geometry_indices: SketchMutationIndexSelection,
    ) -> dict[str, object]:
        return handlers.remove_sketch_geometry.execute(
            document_name=document_name,
            sketch_name=sketch_name,
            geometry_indices=geometry_indices,
        ).to_dict()

    @server.tool(
        name=SET_SKETCH_GEOMETRY_CONSTRUCTION_TOOL,
        description=SET_SKETCH_GEOMETRY_CONSTRUCTION_DESCRIPTION,
        structured_output=True,
    )
    def set_sketch_geometry_construction(
        document_name: str,
        sketch_name: str,
        geometry_indices: SketchMutationIndexSelection,
        construction: SketchConstructionState,
    ) -> dict[str, object]:
        return handlers.set_sketch_geometry_construction.execute(
            document_name=document_name,
            sketch_name=sketch_name,
            geometry_indices=geometry_indices,
            construction=construction,
        ).to_dict()

    _forbid_extra_arguments(server, REMOVE_SKETCH_CONSTRAINTS_TOOL)
    _forbid_extra_arguments(server, REMOVE_SKETCH_GEOMETRY_TOOL)
    _forbid_extra_arguments(server, SET_SKETCH_GEOMETRY_CONSTRUCTION_TOOL)


def _forbid_extra_arguments(server: FastMCP[Any], tool_name: str) -> None:
    tool = server._tool_manager.get_tool(tool_name)
    if tool is None:  # pragma: no cover
        raise RuntimeError(f"FastMCP sketch-removal tool {tool_name!r} was not registered.")
    argument_model = tool.fn_metadata.arg_model
    argument_model.model_config = ConfigDict(**argument_model.model_config, extra="forbid")
    argument_model.model_rebuild(force=True)
    tool.parameters = argument_model.model_json_schema(by_alias=True)


__all__ = [
    "REMOVE_SKETCH_CONSTRAINTS_DESCRIPTION",
    "REMOVE_SKETCH_GEOMETRY_DESCRIPTION",
    "SET_SKETCH_GEOMETRY_CONSTRUCTION_DESCRIPTION",
    "register_sketch_removal_tools",
]
