"""FastMCP registration for read-only sketch analysis tools 22--24."""

from __future__ import annotations

from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from pydantic import ConfigDict, Field

from freecad_mcp.commands import DocumentHandlers
from freecad_mcp.tool_registry import (
    ANALYZE_SKETCH_TOOL,
    LIST_SKETCH_OPEN_VERTICES_TOOL,
    VALIDATE_SKETCH_PROFILE_TOOL,
)

StrictAnalysisFlag = Annotated[bool, Field(strict=True)]
StrictGeometryIndex = Annotated[int, Field(strict=True, ge=0)]
GeometrySelection = Annotated[
    list[StrictGeometryIndex],
    Field(min_length=1, json_schema_extra={"uniqueItems": True}),
]

ANALYZE_SKETCH_DESCRIPTION = (
    "Use for a broad read-only summary of sketch topology, cached solver state, connected "
    "components, open chains, and likely profile problems. This is higher-level than "
    "get_sketch and does not return complete raw geometry or constraints. It never modifies, "
    "repairs, solves, recomputes, or saves. Construction and external geometry are excluded "
    "unless explicitly included; zero solver conflicts alone does not prove a valid profile."
)
VALIDATE_SKETCH_PROFILE_DESCRIPTION = (
    "Use when the main question is whether all or selected internal sketch geometry forms one "
    "or more usable closed profiles, including disjoint or nested profiles. This read-only tool "
    "reports topology, orientation, exact supported line/arc area, containment, openings, "
    "branches, and intersections; it does not repair geometry. Construction and external "
    "geometry are excluded unless explicitly included. Use get_sketch for detailed geometry "
    "and constraint inspection."
)
LIST_SKETCH_OPEN_VERTICES_DESCRIPTION = (
    "Use when the main question is where an open chain or profile gap is located. Returns only "
    "degree-one endpoints for all or selected internal geometry with controlled coordinates and "
    "member references; branches are findings, not open vertices. This read-only tool does not "
    "close, move, constrain, delete, recompute, or save geometry."
)


def register_sketch_analysis_tools(server: FastMCP[Any], handlers: DocumentHandlers) -> None:
    """Append the three analysis tools in their authoritative order."""

    @server.tool(
        name=ANALYZE_SKETCH_TOOL,
        description=ANALYZE_SKETCH_DESCRIPTION,
        structured_output=True,
    )
    def analyze_sketch(
        document_name: str,
        sketch_name: str,
        include_construction: StrictAnalysisFlag = False,
        include_external: StrictAnalysisFlag = False,
    ) -> dict[str, object]:
        return handlers.analyze_sketch.execute(
            document_name=document_name,
            sketch_name=sketch_name,
            include_construction=include_construction,
            include_external=include_external,
        ).to_dict()

    @server.tool(
        name=VALIDATE_SKETCH_PROFILE_TOOL,
        description=VALIDATE_SKETCH_PROFILE_DESCRIPTION,
        structured_output=True,
    )
    def validate_sketch_profile(
        document_name: str,
        sketch_name: str,
        geometry_indices: GeometrySelection | None = None,
        include_construction: StrictAnalysisFlag = False,
        include_external: StrictAnalysisFlag = False,
    ) -> dict[str, object]:
        return handlers.validate_sketch_profile.execute(
            document_name=document_name,
            sketch_name=sketch_name,
            geometry_indices=geometry_indices,
            include_construction=include_construction,
            include_external=include_external,
        ).to_dict()

    @server.tool(
        name=LIST_SKETCH_OPEN_VERTICES_TOOL,
        description=LIST_SKETCH_OPEN_VERTICES_DESCRIPTION,
        structured_output=True,
    )
    def list_sketch_open_vertices(
        document_name: str,
        sketch_name: str,
        geometry_indices: GeometrySelection | None = None,
        include_construction: StrictAnalysisFlag = False,
        include_external: StrictAnalysisFlag = False,
    ) -> dict[str, object]:
        return handlers.list_sketch_open_vertices.execute(
            document_name=document_name,
            sketch_name=sketch_name,
            geometry_indices=geometry_indices,
            include_construction=include_construction,
            include_external=include_external,
        ).to_dict()

    _forbid_extra_arguments(server, ANALYZE_SKETCH_TOOL)
    _forbid_extra_arguments(server, VALIDATE_SKETCH_PROFILE_TOOL)
    _forbid_extra_arguments(server, LIST_SKETCH_OPEN_VERTICES_TOOL)


def _forbid_extra_arguments(server: FastMCP[Any], tool_name: str) -> None:
    tool = server._tool_manager.get_tool(tool_name)
    if tool is None:
        raise RuntimeError(f"FastMCP sketch-analysis tool {tool_name!r} was not registered.")
    argument_model = tool.fn_metadata.arg_model
    argument_model.model_config = ConfigDict(**argument_model.model_config, extra="forbid")
    argument_model.model_rebuild(force=True)
    tool.parameters = argument_model.model_json_schema(by_alias=True)


__all__ = [
    "ANALYZE_SKETCH_DESCRIPTION",
    "LIST_SKETCH_OPEN_VERTICES_DESCRIPTION",
    "VALIDATE_SKETCH_PROFILE_DESCRIPTION",
    "GeometrySelection",
    "StrictAnalysisFlag",
    "StrictGeometryIndex",
    "register_sketch_analysis_tools",
]
