"""Explicit FastMCP registration for document operations."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from freecad_mcp.commands import DocumentHandlers
from freecad_mcp.tool_registry import (
    CREATE_DOCUMENT_TOOL,
    GET_DOCUMENT_TOOL,
    LIST_DOCUMENTS_TOOL,
    RECOMPUTE_DOCUMENT_TOOL,
    SAVE_DOCUMENT_TOOL,
)


def register_document_tools(server: FastMCP[Any], handlers: DocumentHandlers) -> None:
    """Register document creation, lookup, listing, and persistence tools."""

    @server.tool(
        name=CREATE_DOCUMENT_TOOL,
        description="Create a new unsaved document in the running FreeCAD application.",
        structured_output=True,
    )
    def create_document(name: str, label: str | None = None) -> dict[str, object]:
        return handlers.create.execute(name=name, label=label).to_dict()

    @server.tool(
        name=LIST_DOCUMENTS_TOOL,
        description="List open FreeCAD documents and identify the active document.",
        structured_output=True,
    )
    def list_documents() -> dict[str, object]:
        return handlers.list.execute().to_dict()

    @server.tool(
        name=GET_DOCUMENT_TOOL,
        description="Inspect an open FreeCAD document by its internal name.",
        structured_output=True,
    )
    def get_document(name: str) -> dict[str, object]:
        return handlers.get.execute(name=name).to_dict()

    @server.tool(
        name=SAVE_DOCUMENT_TOOL,
        description="Save or save as an open FreeCAD document with overwrite protection.",
        structured_output=True,
    )
    def save_document(
        name: str,
        file_path: str | None = None,
        overwrite: bool = False,
    ) -> dict[str, object]:
        return handlers.save.execute(
            name=name,
            file_path=file_path,
            overwrite=overwrite,
        ).to_dict()


def register_recompute_document_tool(server: FastMCP[Any], handlers: DocumentHandlers) -> None:
    """Register document recomputation at its authoritative inventory position."""

    @server.tool(
        name=RECOMPUTE_DOCUMENT_TOOL,
        description="Recompute an open FreeCAD document and return its updated controlled summary.",
        structured_output=True,
    )
    def recompute_document(document_name: str) -> dict[str, object]:
        return handlers.recompute.execute(document_name=document_name).to_dict()
