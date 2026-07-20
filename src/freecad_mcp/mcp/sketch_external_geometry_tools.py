"""FastMCP registration for external geometry and dependency tools 25--28."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import ConfigDict

from freecad_mcp.commands import DocumentHandlers
from freecad_mcp.models import ExternalGeometrySourceInput, ExternalReferenceNumber
from freecad_mcp.tool_registry import (
    ADD_EXTERNAL_GEOMETRY_TOOL,
    GET_SKETCH_DEPENDENCIES_TOOL,
    LIST_EXTERNAL_GEOMETRY_TOOL,
    REMOVE_EXTERNAL_GEOMETRY_TOOL,
)

ADD_EXTERNAL_GEOMETRY_DESCRIPTION = (
    "Atomically add one normal same-document external reference to a sketch. Source is a strict "
    "discriminated union: object_subelement accepts one canonical EdgeN or VertexN on a non-sketch "
    "object; sketch_geometry accepts one zero-based line, circle, or circular-arc geometry index "
    "from another sketch. Exact duplicates are rejected before mutation. The result uses a "
    "non-negative sketch-local external_reference_number; native negative geometry IDs are never "
    "exposed. The operation recomputes and verifies one 'Add sketch external geometry' transaction "
    "but never saves, invokes GUI commands, enters edit mode, or changes selection."
)

LIST_EXTERNAL_GEOMETRY_DESCRIPTION = (
    "Read one sketch's external references in deterministic sketch-local order. Returns controlled "
    "source identity, source labels, category, resolved or broken state, geometry readback, and "
    "constraint indices using each non-negative external_reference_number. Broken native mappings "
    "are reported conservatively without guessing lost source identity. This tool is strictly "
    "read-only: no recompute, solve, transaction, save, activation, edit mode, or selection change."
)

REMOVE_EXTERNAL_GEOMETRY_DESCRIPTION = (
    "Atomically remove one controlled external_reference_number after reporting impact. Removal is "
    "refused when the reference is unresolved, non-normal, cross-document, unsupported, or used by "
    "any constraint; dependent constraints are never deleted automatically. A successful call "
    "verifies one 'Remove sketch external geometry' transaction and remaining mappings without "
    "saving or invoking GUI commands."
)

GET_SKETCH_DEPENDENCIES_DESCRIPTION = (
    "Inspect controlled dependencies for one sketch: external geometry sources, attachment "
    "sources, "
    "expression sources, constraints using external references, downstream consumers, broken "
    "references, and observed cross-document references. Returns no native objects, raw link "
    "arrays, "
    "memory addresses, or negative geometry IDs. This tool is strictly read-only and performs no "
    "recompute, solve, transaction, save, activation, edit-mode, or selection changes."
)


def register_sketch_external_geometry_tools(
    server: FastMCP[Any],
    handlers: DocumentHandlers,
) -> None:
    """Append Milestone 18 tools in their authoritative 25--28 order."""

    @server.tool(
        name=ADD_EXTERNAL_GEOMETRY_TOOL,
        description=ADD_EXTERNAL_GEOMETRY_DESCRIPTION,
        structured_output=True,
    )
    def add_external_geometry(
        document_name: str,
        sketch_name: str,
        source: ExternalGeometrySourceInput,
    ) -> dict[str, object]:
        return handlers.add_external_geometry.execute(
            document_name=document_name,
            sketch_name=sketch_name,
            source=source,
        ).to_dict()

    @server.tool(
        name=LIST_EXTERNAL_GEOMETRY_TOOL,
        description=LIST_EXTERNAL_GEOMETRY_DESCRIPTION,
        structured_output=True,
    )
    def list_external_geometry(
        document_name: str,
        sketch_name: str,
    ) -> dict[str, object]:
        return handlers.list_external_geometry.execute(
            document_name=document_name,
            sketch_name=sketch_name,
        ).to_dict()

    @server.tool(
        name=REMOVE_EXTERNAL_GEOMETRY_TOOL,
        description=REMOVE_EXTERNAL_GEOMETRY_DESCRIPTION,
        structured_output=True,
    )
    def remove_external_geometry(
        document_name: str,
        sketch_name: str,
        external_reference_number: ExternalReferenceNumber,
    ) -> dict[str, object]:
        return handlers.remove_external_geometry.execute(
            document_name=document_name,
            sketch_name=sketch_name,
            external_reference_number=external_reference_number,
        ).to_dict()

    @server.tool(
        name=GET_SKETCH_DEPENDENCIES_TOOL,
        description=GET_SKETCH_DEPENDENCIES_DESCRIPTION,
        structured_output=True,
    )
    def get_sketch_dependencies(
        document_name: str,
        sketch_name: str,
    ) -> dict[str, object]:
        return handlers.get_sketch_dependencies.execute(
            document_name=document_name,
            sketch_name=sketch_name,
        ).to_dict()

    _forbid_extra_arguments(server, ADD_EXTERNAL_GEOMETRY_TOOL)
    _forbid_extra_arguments(server, LIST_EXTERNAL_GEOMETRY_TOOL)
    _forbid_extra_arguments(server, REMOVE_EXTERNAL_GEOMETRY_TOOL)
    _forbid_extra_arguments(server, GET_SKETCH_DEPENDENCIES_TOOL)


def _forbid_extra_arguments(server: FastMCP[Any], tool_name: str) -> None:
    tool = server._tool_manager.get_tool(tool_name)
    if tool is None:  # pragma: no cover
        raise RuntimeError(f"FastMCP external-geometry tool {tool_name!r} was not registered.")
    argument_model = tool.fn_metadata.arg_model
    argument_model.model_config = ConfigDict(**argument_model.model_config, extra="forbid")
    argument_model.model_rebuild(force=True)
    tool.parameters = argument_model.model_json_schema(by_alias=True)


__all__ = [
    "ADD_EXTERNAL_GEOMETRY_DESCRIPTION",
    "GET_SKETCH_DEPENDENCIES_DESCRIPTION",
    "LIST_EXTERNAL_GEOMETRY_DESCRIPTION",
    "REMOVE_EXTERNAL_GEOMETRY_DESCRIPTION",
    "register_sketch_external_geometry_tools",
]
