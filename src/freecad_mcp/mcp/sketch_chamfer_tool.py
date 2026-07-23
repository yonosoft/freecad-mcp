"""FastMCP registration for chamfer tool."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import ConfigDict

from freecad_mcp.commands import DocumentHandlers
from freecad_mcp.tool_registry import CHAMFER_SKETCH_GEOMETRY_TOOL

CHAMFER_SKETCH_GEOMETRY_DESCRIPTION = (
    "Chamfer the shared coincident corner of two normal internal line segments by trimming both "
    "lines and inserting an equal-distance chamfer line. Only one geometry index is required; "
    "the partner is discovered automatically through the sketch's sole coincident constraint "
    "at the shared endpoint. Both source lines must be normal (non-construction) and must share "
    "exactly one coincident constraint with no additional constraints on either geometry. "
    "Construction, named, expression-bound, external, and constrained geometry is refused. "
    "Success returns complete ordered geometry and constraint mappings including source indices, "
    "the created construction-arc index, created chamfer line index, removed coincident "
    "constraint, created tangent constraints, trimmed endpoint and tangency information, solver "
    "state, and dependency summary. Creates one 'Chamfer sketch geometry' history step and "
    "never saves."
)


def register_sketch_chamfer_tool(
    server: FastMCP[Any],
    handlers: DocumentHandlers,
) -> None:
    """Register the chamfer sketch geometry tool."""

    @server.tool(
        name=CHAMFER_SKETCH_GEOMETRY_TOOL,
        description=CHAMFER_SKETCH_GEOMETRY_DESCRIPTION,
        structured_output=True,
    )
    def chamfer_sketch_geometry(
        document_name: str,
        sketch_name: str,
        first_geometry_index: int,
        distance: float,
    ) -> dict[str, object]:
        return handlers.chamfer_sketch_geometry.execute(
            document_name=document_name,
            sketch_name=sketch_name,
            first_geometry_index=first_geometry_index,
            distance=distance,
        ).to_dict()

    _forbid_extra_arguments(server, CHAMFER_SKETCH_GEOMETRY_TOOL)


def _forbid_extra_arguments(server: FastMCP[Any], tool_name: str) -> None:
    tool = server._tool_manager.get_tool(tool_name)
    if tool is None:  # pragma: no cover
        raise RuntimeError(f"FastMCP chamfer tool {tool_name!r} was not registered.")
    argument_model = tool.fn_metadata.arg_model
    argument_model.model_config = ConfigDict(**argument_model.model_config, extra="forbid")
    argument_model.model_rebuild(force=True)
    tool.parameters = argument_model.model_json_schema(by_alias=True)
