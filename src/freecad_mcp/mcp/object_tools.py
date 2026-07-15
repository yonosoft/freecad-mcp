"""Explicit FastMCP registration for controlled object inspection."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from freecad_mcp.commands import DocumentHandlers
from freecad_mcp.tool_registry import GET_OBJECT_TOOL, LIST_OBJECTS_TOOL


def register_object_tools(server: FastMCP[Any], handlers: DocumentHandlers) -> None:
    """Register object listing and exact-name lookup tools."""

    @server.tool(
        name=LIST_OBJECTS_TOOL,
        description="List controlled summaries of all objects in an open FreeCAD document.",
        structured_output=True,
    )
    def list_objects(document_name: str) -> dict[str, object]:
        return handlers.object_query.execute(document_name=document_name).to_dict()

    @server.tool(
        name=GET_OBJECT_TOOL,
        description=(
            "Retrieve one FreeCAD object by exact internal document and object name "
            "with controlled placement."
        ),
        structured_output=True,
    )
    def get_object(document_name: str, object_name: str) -> dict[str, object]:
        return handlers.get_object.execute(
            document_name=document_name,
            object_name=object_name,
        ).to_dict()
