"""Explicit FastMCP registration for controlled document history."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import ConfigDict

from freecad_mcp.commands import DocumentHandlers
from freecad_mcp.tool_registry import (
    GET_DOCUMENT_HISTORY_TOOL,
    REDO_DOCUMENT_TOOL,
    UNDO_DOCUMENT_TOOL,
)


def register_document_history_tools(
    server: FastMCP[Any],
    handlers: DocumentHandlers,
) -> None:
    """Register history inspection, one-step undo, and one-step redo as tools 13-15."""

    @server.tool(
        name=GET_DOCUMENT_HISTORY_TOOL,
        description=(
            "Inspect controlled undo/redo availability for one exact open document. Returns "
            "counts and current top transaction safety labels without native transaction IDs "
            "or complete stacks. After a successful modelling operation, recompute and inspect "
            "the result; when it succeeded but produced the wrong design intent, inspect history "
            "before undoing the known last transaction in the same sketch or model."
        ),
        structured_output=True,
    )
    def get_document_history(document_name: str) -> dict[str, object]:
        return handlers.get_history.execute(document_name=document_name).to_dict()

    _forbid_extra_arguments(server, GET_DOCUMENT_HISTORY_TOOL)

    @server.tool(
        name=UNDO_DOCUMENT_TOOL,
        description=(
            "Undo exactly one transaction in one exact open document. Supply "
            "expected_transaction_name when the known top safety label is available; a mismatch "
            "performs no mutation. Use this for a successful but wrong modelling operation. Do "
            "not undo a failed atomic MCP operation because it should already have rolled back "
            "with zero mutation. Prefer correcting the current sketch or model through controlled "
            "undo and avoid creating replacement sketches or documents for recoverable mistakes. "
            "The tool does not recompute or save."
        ),
        structured_output=True,
    )
    def undo_document(
        document_name: str,
        expected_transaction_name: str | None = None,
    ) -> dict[str, object]:
        return handlers.undo.execute(
            document_name=document_name,
            expected_transaction_name=expected_transaction_name,
        ).to_dict()

    _forbid_extra_arguments(server, UNDO_DOCUMENT_TOOL)

    @server.tool(
        name=REDO_DOCUMENT_TOOL,
        description=(
            "Redo exactly one most-recently undone transaction in one exact open document. Supply "
            "expected_transaction_name when its top safety label is known. Redo only when "
            "intentionally restoring the preceding undo; an intervening mutation normally "
            "invalidates redo history. The tool does not navigate multiple steps, recompute, "
            "or save."
        ),
        structured_output=True,
    )
    def redo_document(
        document_name: str,
        expected_transaction_name: str | None = None,
    ) -> dict[str, object]:
        return handlers.redo.execute(
            document_name=document_name,
            expected_transaction_name=expected_transaction_name,
        ).to_dict()

    _forbid_extra_arguments(server, REDO_DOCUMENT_TOOL)


def _forbid_extra_arguments(server: FastMCP[Any], tool_name: str) -> None:
    """Tighten FastMCP's generated argument model for the new public contract.

    FastMCP 1.x generates function argument models with Pydantic's default
    ``extra='ignore'`` behaviour. Controlled history deliberately rejects
    unsupported fields such as ``steps``, ``count``, and native transaction IDs.
    """
    manager = server._tool_manager
    tool = manager.get_tool(tool_name)
    if tool is None:  # pragma: no cover - registration immediately precedes this call
        raise RuntimeError(f"FastMCP tool '{tool_name}' was not registered.")
    argument_model = tool.fn_metadata.arg_model
    argument_model.model_config = ConfigDict(**argument_model.model_config, extra="forbid")
    argument_model.model_rebuild(force=True)
    tool.parameters = argument_model.model_json_schema(by_alias=True)


__all__ = ["register_document_history_tools"]
