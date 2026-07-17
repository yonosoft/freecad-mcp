"""Explicit FastMCP registration for controlled object inspection."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from freecad_mcp.commands import DocumentHandlers
from freecad_mcp.tool_registry import GET_OBJECT_TOOL, GET_SKETCH_TOOL, LIST_OBJECTS_TOOL


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


def register_get_sketch_tool(server: FastMCP[Any], handlers: DocumentHandlers) -> None:
    """Register read-only sketch inspection after all existing tools."""

    @server.tool(
        name=GET_SKETCH_TOOL,
        description=(
            "Retrieve a read-only, controlled snapshot of one sketch by exact internal "
            "document and sketch name. Supports line segments, circles, circular arcs, "
            "points, and a focused constraint subset; other valid items are reported "
            "as unsupported records. Does not solve, recompute, save, or modify the document."
        ),
        structured_output=True,
    )
    def get_sketch(document_name: str, sketch_name: str) -> dict[str, object]:
        return handlers.get_sketch.execute(
            document_name=document_name,
            sketch_name=sketch_name,
        ).to_dict()
