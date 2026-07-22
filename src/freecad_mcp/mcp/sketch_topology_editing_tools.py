"""FastMCP registration for Milestone 23 topology-editing tools 40--42."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import ConfigDict

from freecad_mcp.commands import DocumentHandlers
from freecad_mcp.models import (
    SketchMutationIndex,
    SketchPoint2DInput,
    SketchTopologyEndpoint,
)
from freecad_mcp.tool_registry import (
    EXTEND_SKETCH_GEOMETRY_TOOL,
    SPLIT_SKETCH_GEOMETRY_TOOL,
    TRIM_SKETCH_GEOMETRY_TOOL,
)

TRIM_SKETCH_GEOMETRY_DESCRIPTION = (
    "Trim the portion selected by one finite on-source pick point from an unconstrained internal "
    "line segment. Initial support requires deterministic interior intersections with internal "
    "line-segment boundaries; construction source and boundary lines are supported. External "
    "boundaries, endpoint/coincident/overlapping intersections, unsupported geometry, operated "
    "constraints, dependencies, and degenerate results are refused before mutation. Success "
    "returns complete ordered geometry and constraint mappings, creates one 'Trim sketch "
    "geometry' history step, and never saves."
)

SPLIT_SKETCH_GEOMETRY_DESCRIPTION = (
    "Split one unconstrained internal line segment at a finite point lying on it within the fixed "
    "1e-7 sketch-unit tolerance. Results are ordered by source parameter: the original index keeps "
    "the first segment and one appended index receives the second; FreeCAD's verified joining "
    "coincidence is reported explicitly. Construction lines are supported. Endpoint requests are "
    "transaction-free no-ops; unsupported geometry, operated constraints, dependencies, and "
    "off-source points are refused. Success creates one 'Split sketch geometry' history step and "
    "never saves."
)

EXTEND_SKETCH_GEOMETRY_DESCRIPTION = (
    "Extend the selected start or end of one unconstrained internal line segment to an explicit "
    "finite collinear point. The target must lie strictly beyond the selected endpoint; shortening "
    "and non-collinear targets are refused. Construction lines are supported. A target equal to "
    "the current endpoint is a transaction-free no-op. Success preserves the source index and all "
    "unrelated entities, returns complete ordered mappings, creates one 'Extend sketch geometry' "
    "history step, and never saves."
)


def register_sketch_topology_editing_tools(
    server: FastMCP[Any],
    handlers: DocumentHandlers,
) -> None:
    """Append trim, split, and extend in authoritative 40--42 order."""

    @server.tool(
        name=TRIM_SKETCH_GEOMETRY_TOOL,
        description=TRIM_SKETCH_GEOMETRY_DESCRIPTION,
        structured_output=True,
    )
    def trim_sketch_geometry(
        document_name: str,
        sketch_name: str,
        geometry_index: SketchMutationIndex,
        pick_point: SketchPoint2DInput,
    ) -> dict[str, object]:
        return handlers.trim_sketch_geometry.execute(
            document_name=document_name,
            sketch_name=sketch_name,
            geometry_index=geometry_index,
            pick_point=pick_point,
        ).to_dict()

    @server.tool(
        name=SPLIT_SKETCH_GEOMETRY_TOOL,
        description=SPLIT_SKETCH_GEOMETRY_DESCRIPTION,
        structured_output=True,
    )
    def split_sketch_geometry(
        document_name: str,
        sketch_name: str,
        geometry_index: SketchMutationIndex,
        point: SketchPoint2DInput,
    ) -> dict[str, object]:
        return handlers.split_sketch_geometry.execute(
            document_name=document_name,
            sketch_name=sketch_name,
            geometry_index=geometry_index,
            point=point,
        ).to_dict()

    @server.tool(
        name=EXTEND_SKETCH_GEOMETRY_TOOL,
        description=EXTEND_SKETCH_GEOMETRY_DESCRIPTION,
        structured_output=True,
    )
    def extend_sketch_geometry(
        document_name: str,
        sketch_name: str,
        geometry_index: SketchMutationIndex,
        endpoint: SketchTopologyEndpoint,
        target_point: SketchPoint2DInput,
    ) -> dict[str, object]:
        return handlers.extend_sketch_geometry.execute(
            document_name=document_name,
            sketch_name=sketch_name,
            geometry_index=geometry_index,
            endpoint=endpoint,
            target_point=target_point,
        ).to_dict()

    for tool_name in (
        TRIM_SKETCH_GEOMETRY_TOOL,
        SPLIT_SKETCH_GEOMETRY_TOOL,
        EXTEND_SKETCH_GEOMETRY_TOOL,
    ):
        _forbid_extra_arguments(server, tool_name)


def _forbid_extra_arguments(server: FastMCP[Any], tool_name: str) -> None:
    tool = server._tool_manager.get_tool(tool_name)
    if tool is None:  # pragma: no cover
        raise RuntimeError(f"FastMCP topology-editing tool {tool_name!r} was not registered.")
    argument_model = tool.fn_metadata.arg_model
    argument_model.model_config = ConfigDict(**argument_model.model_config, extra="forbid")
    argument_model.model_rebuild(force=True)
    tool.parameters = argument_model.model_json_schema(by_alias=True)


__all__ = [
    "EXTEND_SKETCH_GEOMETRY_DESCRIPTION",
    "SPLIT_SKETCH_GEOMETRY_DESCRIPTION",
    "TRIM_SKETCH_GEOMETRY_DESCRIPTION",
    "register_sketch_topology_editing_tools",
]
