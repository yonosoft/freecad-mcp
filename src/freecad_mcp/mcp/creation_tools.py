"""Explicit FastMCP registration for controlled body and sketch creation."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from freecad_mcp.commands import DocumentHandlers
from freecad_mcp.tool_registry import CREATE_BODY_TOOL, CREATE_SKETCH_TOOL


def register_creation_tools(server: FastMCP[Any], handlers: DocumentHandlers) -> None:
    """Register Part Design Body and sketch creation tools."""

    @server.tool(
        name=CREATE_BODY_TOOL,
        description=(
            "Create one empty Part Design Body in an open FreeCAD document. "
            "Use exact internal document and object names, not labels. "
            "The tool recomputes the document but does not save it or create "
            "sketches or features. Use list_documents and list_objects first "
            "when the required internal names are unknown."
        ),
        structured_output=True,
    )
    def create_body(
        document_name: str,
        name: str,
        label: str | None = None,
    ) -> dict[str, object]:
        return handlers.create_body.execute(
            document_name=document_name,
            name=name,
            label=label,
        ).to_dict()

    @server.tool(
        name=CREATE_SKETCH_TOOL,
        description=(
            "Create one empty sketch inside an existing Part Design Body. "
            "Optionally attach it to that body's XY, XZ or YZ origin plane "
            "using the support_plane selector. Use exact internal document, "
            "body and sketch names, not labels. The tool recomputes the "
            "document but does not save it, add geometry or constraints, "
            "use arbitrary faces, apply attachment offsets or open sketch "
            "edit mode. Use list_documents, list_objects and get_object "
            "first when internal names are unknown."
        ),
        structured_output=True,
    )
    def create_sketch(
        document_name: str,
        body_name: str,
        name: str,
        label: str | None = None,
        support_plane: str | None = None,
    ) -> dict[str, object]:
        return handlers.create_sketch.execute(
            document_name=document_name,
            body_name=body_name,
            name=name,
            label=label,
            support_plane=support_plane,
        ).to_dict()
