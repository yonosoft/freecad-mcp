"""FastMCP registration for controlled sketch constraint state tools 49--51."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from freecad_mcp.commands import DocumentHandlers
from freecad_mcp.tool_registry import (
    SET_SKETCH_CONSTRAINT_ACTIVE_TOOL,
    SET_SKETCH_CONSTRAINT_DRIVING_TOOL,
    SET_SKETCH_CONSTRAINT_VIRTUAL_SPACE_TOOL,
)

SET_SKETCH_CONSTRAINT_DRIVING_DESCRIPTION = (
    "Set one supported dimensional sketch constraint to driving or reference state. "
    "Only dimensional constraints (distance, radius, diameter, angle) support "
    "driving/reference conversion. Expression-bound constraints are refused. Name, "
    "expression, and all other constraint properties are preserved. When the "
    "constraint is already in the requested state the call succeeds with no "
    "transaction or history change."
)

SET_SKETCH_CONSTRAINT_ACTIVE_DESCRIPTION = (
    "Set one supported sketch constraint to active or inactive state. "
    "All constraint types are supported. Deactivating an expression dependency "
    "source is refused. Active state, name, expression, and all other constraint "
    "properties are preserved. When the constraint is already in the requested "
    "state the call succeeds with no transaction or history change."
)

SET_SKETCH_CONSTRAINT_VIRTUAL_SPACE_DESCRIPTION = (
    "Move one supported sketch constraint into or out of virtual space. "
    "All constraint types are supported. Moving an expression dependency source "
    "into virtual space is refused. Virtual space state, name, expression, and "
    "all other constraint properties are preserved. When the constraint is "
    "already in the requested state the call succeeds with no transaction or "
    "history change."
)


def register_sketch_constraint_state_tools(
    server: FastMCP[Any],
    handlers: DocumentHandlers,
) -> None:
    """Append Milestone 25 tools in authoritative 49--51 order."""

    @server.tool(
        name=SET_SKETCH_CONSTRAINT_DRIVING_TOOL,
        description=SET_SKETCH_CONSTRAINT_DRIVING_DESCRIPTION,
        structured_output=True,
    )
    def set_sketch_constraint_driving(
        document_name: str,
        sketch_name: str,
        constraint_index: int,
        driving: bool,
    ) -> dict[str, object]:
        return handlers.set_sketch_constraint_driving.execute(
            document_name=document_name,
            sketch_name=sketch_name,
            constraint_index=constraint_index,
            driving=driving,
        ).to_dict()

    @server.tool(
        name=SET_SKETCH_CONSTRAINT_ACTIVE_TOOL,
        description=SET_SKETCH_CONSTRAINT_ACTIVE_DESCRIPTION,
        structured_output=True,
    )
    def set_sketch_constraint_active(
        document_name: str,
        sketch_name: str,
        constraint_index: int,
        active: bool,
    ) -> dict[str, object]:
        return handlers.set_sketch_constraint_active.execute(
            document_name=document_name,
            sketch_name=sketch_name,
            constraint_index=constraint_index,
            active=active,
        ).to_dict()

    @server.tool(
        name=SET_SKETCH_CONSTRAINT_VIRTUAL_SPACE_TOOL,
        description=SET_SKETCH_CONSTRAINT_VIRTUAL_SPACE_DESCRIPTION,
        structured_output=True,
    )
    def set_sketch_constraint_virtual_space(
        document_name: str,
        sketch_name: str,
        constraint_index: int,
        virtual: bool,
    ) -> dict[str, object]:
        return handlers.set_sketch_constraint_virtual_space.execute(
            document_name=document_name,
            sketch_name=sketch_name,
            constraint_index=constraint_index,
            virtual=virtual,
        ).to_dict()

    _forbid_extra_arguments(server, SET_SKETCH_CONSTRAINT_DRIVING_TOOL)
    _forbid_extra_arguments(server, SET_SKETCH_CONSTRAINT_ACTIVE_TOOL)
    _forbid_extra_arguments(server, SET_SKETCH_CONSTRAINT_VIRTUAL_SPACE_TOOL)


def _forbid_extra_arguments(server: FastMCP[Any], tool_name: str) -> None:
    """Reject unexpected fields for one registered tool."""
    from pydantic import ConfigDict

    tool = server._tool_manager._tools.get(tool_name)
    if tool is not None and hasattr(tool, "fn"):
        fn = tool.fn
        if hasattr(fn, "__annotations__"):
            fn.__annotations__["_extra"] = ConfigDict(extra="forbid")
