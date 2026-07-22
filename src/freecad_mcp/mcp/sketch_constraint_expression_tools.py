"""FastMCP registration for Milestone 22 constraint-expression tools 36--39."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import ConfigDict

from freecad_mcp.commands import DocumentHandlers
from freecad_mcp.models import SketchMutationIndex
from freecad_mcp.tool_registry import (
    CLEAR_SKETCH_CONSTRAINT_EXPRESSION_TOOL,
    LIST_SKETCH_CONSTRAINT_EXPRESSIONS_TOOL,
    SET_SKETCH_CONSTRAINT_EXPRESSION_TOOL,
    SET_SKETCH_CONSTRAINT_NAME_TOOL,
)

SET_SKETCH_CONSTRAINT_NAME_DESCRIPTION = (
    "Assign, rename, or clear (name=null) one active driving scalar sketch constraint. Names use "
    "a case-sensitive ASCII identifier of at most 64 characters and must be unique within the "
    "sketch. Renaming or clearing a referenced source, or changing the name of an expression-bound "
    "target, is refused. Exact no-ops create no history; a change creates one 'Set sketch "
    "constraint name' history step and never saves."
)

SET_SKETCH_CONSTRAINT_EXPRESSION_DESCRIPTION = (
    "Bind or replace an expression on one active driving distance, distance_x, distance_y, radius, "
    "diameter, or angle constraint. The finite grammar supports numeric constants with explicit mm "
    "or deg units, parentheses, unary signs, + - * /, sqrt of dimensionless values, same-sketch "
    "Constraints.Name references, and same-document SketchName.Constraints.Name references. "
    "References resolve by internal sketch Name; cycles, opaque native expressions, dimension "
    "mismatches, arbitrary properties/functions, and cross-document syntax are refused. A change "
    "creates one 'Set sketch constraint expression' history step and never saves."
)

CLEAR_SKETCH_CONSTRAINT_EXPRESSION_DESCRIPTION = (
    "Clear one supported scalar constraint expression while preserving its current evaluated value "
    "and restoring direct value control. Opaque native expressions and referenced targets are "
    "refused. An unbound target is a history-free no-op; a change creates one 'Clear sketch "
    "constraint expression' history step and never saves."
)

LIST_SKETCH_CONSTRAINT_EXPRESSIONS_DESCRIPTION = (
    "Read the current sketch's constraint-expression bindings in constraint order without "
    "recompute, transactions, history movement, or saving. Supported records include canonical "
    "public expressions and exact named scalar dependencies. Unsupported native expressions are "
    "reported as opaque without exposing their raw native text or property paths."
)


def register_sketch_constraint_expression_tools(
    server: FastMCP[Any],
    handlers: DocumentHandlers,
) -> None:
    """Append Milestone 22 tools in authoritative 36--39 order."""

    @server.tool(
        name=SET_SKETCH_CONSTRAINT_NAME_TOOL,
        description=SET_SKETCH_CONSTRAINT_NAME_DESCRIPTION,
        structured_output=True,
    )
    def set_sketch_constraint_name(
        document_name: str,
        sketch_name: str,
        constraint_index: SketchMutationIndex,
        name: str | None,
    ) -> dict[str, object]:
        return handlers.set_sketch_constraint_name.execute(
            document_name=document_name,
            sketch_name=sketch_name,
            constraint_index=constraint_index,
            name=name,
        ).to_dict()

    @server.tool(
        name=SET_SKETCH_CONSTRAINT_EXPRESSION_TOOL,
        description=SET_SKETCH_CONSTRAINT_EXPRESSION_DESCRIPTION,
        structured_output=True,
    )
    def set_sketch_constraint_expression(
        document_name: str,
        sketch_name: str,
        constraint_index: SketchMutationIndex,
        expression: str,
    ) -> dict[str, object]:
        return handlers.set_sketch_constraint_expression.execute(
            document_name=document_name,
            sketch_name=sketch_name,
            constraint_index=constraint_index,
            expression=expression,
        ).to_dict()

    @server.tool(
        name=CLEAR_SKETCH_CONSTRAINT_EXPRESSION_TOOL,
        description=CLEAR_SKETCH_CONSTRAINT_EXPRESSION_DESCRIPTION,
        structured_output=True,
    )
    def clear_sketch_constraint_expression(
        document_name: str,
        sketch_name: str,
        constraint_index: SketchMutationIndex,
    ) -> dict[str, object]:
        return handlers.clear_sketch_constraint_expression.execute(
            document_name=document_name,
            sketch_name=sketch_name,
            constraint_index=constraint_index,
        ).to_dict()

    @server.tool(
        name=LIST_SKETCH_CONSTRAINT_EXPRESSIONS_TOOL,
        description=LIST_SKETCH_CONSTRAINT_EXPRESSIONS_DESCRIPTION,
        structured_output=True,
    )
    def list_sketch_constraint_expressions(
        document_name: str,
        sketch_name: str,
    ) -> dict[str, object]:
        return handlers.list_sketch_constraint_expressions.execute(
            document_name=document_name,
            sketch_name=sketch_name,
        ).to_dict()

    for tool_name in (
        SET_SKETCH_CONSTRAINT_NAME_TOOL,
        SET_SKETCH_CONSTRAINT_EXPRESSION_TOOL,
        CLEAR_SKETCH_CONSTRAINT_EXPRESSION_TOOL,
        LIST_SKETCH_CONSTRAINT_EXPRESSIONS_TOOL,
    ):
        _forbid_extra_arguments(server, tool_name)


def _forbid_extra_arguments(server: FastMCP[Any], tool_name: str) -> None:
    tool = server._tool_manager.get_tool(tool_name)
    if tool is None:  # pragma: no cover
        raise RuntimeError(f"FastMCP constraint-expression tool {tool_name!r} was not registered.")
    argument_model = tool.fn_metadata.arg_model
    argument_model.model_config = ConfigDict(**argument_model.model_config, extra="forbid")
    argument_model.model_rebuild(force=True)
    tool.parameters = argument_model.model_json_schema(by_alias=True)


__all__ = [
    "CLEAR_SKETCH_CONSTRAINT_EXPRESSION_DESCRIPTION",
    "LIST_SKETCH_CONSTRAINT_EXPRESSIONS_DESCRIPTION",
    "SET_SKETCH_CONSTRAINT_EXPRESSION_DESCRIPTION",
    "SET_SKETCH_CONSTRAINT_NAME_DESCRIPTION",
    "register_sketch_constraint_expression_tools",
]
