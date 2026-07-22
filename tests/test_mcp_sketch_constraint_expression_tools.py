from __future__ import annotations

import asyncio
from typing import Any, cast

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from freecad_mcp.mcp.server import build_mcp_server
from freecad_mcp.server.config import ServerConfig
from freecad_mcp.tool_registry import (
    CLEAR_SKETCH_CONSTRAINT_EXPRESSION_TOOL,
    LIST_SKETCH_CONSTRAINT_EXPRESSIONS_TOOL,
    REGISTERED_TOOL_NAMES,
    SET_SKETCH_CONSTRAINT_EXPRESSION_TOOL,
    SET_SKETCH_CONSTRAINT_NAME_TOOL,
)
from mcp_server_stubs import make_handlers


def _server() -> Any:
    handlers, _adapter = make_handlers()
    return build_mcp_server(handlers, ServerConfig())


def test_constraint_expression_tools_are_exactly_tools_thirty_six_through_thirty_nine() -> None:
    names = [tool.name for tool in asyncio.run(_server().list_tools())]

    assert len(names) == 51
    assert tuple(names) == REGISTERED_TOOL_NAMES
    assert names[35:39] == [
        SET_SKETCH_CONSTRAINT_NAME_TOOL,
        SET_SKETCH_CONSTRAINT_EXPRESSION_TOOL,
        CLEAR_SKETCH_CONSTRAINT_EXPRESSION_TOOL,
        LIST_SKETCH_CONSTRAINT_EXPRESSIONS_TOOL,
    ]


@pytest.mark.parametrize(
    ("tool_name", "required"),
    [
        (
            SET_SKETCH_CONSTRAINT_NAME_TOOL,
            ["document_name", "sketch_name", "constraint_index", "name"],
        ),
        (
            SET_SKETCH_CONSTRAINT_EXPRESSION_TOOL,
            ["document_name", "sketch_name", "constraint_index", "expression"],
        ),
        (
            CLEAR_SKETCH_CONSTRAINT_EXPRESSION_TOOL,
            ["document_name", "sketch_name", "constraint_index"],
        ),
        (
            LIST_SKETCH_CONSTRAINT_EXPRESSIONS_TOOL,
            ["document_name", "sketch_name"],
        ),
    ],
)
def test_constraint_expression_tool_schemas_are_strict(
    tool_name: str,
    required: list[str],
) -> None:
    tool = _server()._tool_manager.get_tool(tool_name)
    assert tool is not None
    schema = cast(dict[str, Any], tool.parameters)

    assert schema["additionalProperties"] is False
    assert schema["required"] == required
    if "constraint_index" in schema["properties"]:
        assert schema["properties"]["constraint_index"]["minimum"] == 0


def test_constraint_expression_tools_delegate_once_with_canonical_expression() -> None:
    handlers, adapter = make_handlers()
    server = build_mcp_server(handlers, ServerConfig())

    name_result = cast(
        tuple[list[Any], dict[str, object]],
        asyncio.run(
            server.call_tool(
                SET_SKETCH_CONSTRAINT_NAME_TOOL,
                {
                    "document_name": "TestDocument",
                    "sketch_name": "Source",
                    "constraint_index": 0,
                    "name": "SideLength",
                },
            )
        ),
    )[1]
    expression_result = cast(
        tuple[list[Any], dict[str, object]],
        asyncio.run(
            server.call_tool(
                SET_SKETCH_CONSTRAINT_EXPRESSION_TOOL,
                {
                    "document_name": "TestDocument",
                    "sketch_name": "Target",
                    "constraint_index": 0,
                    "expression": "Source.Constraints.SideLength/(2*sqrt(3))",
                },
            )
        ),
    )[1]
    clear_result = cast(
        tuple[list[Any], dict[str, object]],
        asyncio.run(
            server.call_tool(
                CLEAR_SKETCH_CONSTRAINT_EXPRESSION_TOOL,
                {
                    "document_name": "TestDocument",
                    "sketch_name": "Target",
                    "constraint_index": 0,
                },
            )
        ),
    )[1]
    list_result = cast(
        tuple[list[Any], dict[str, object]],
        asyncio.run(
            server.call_tool(
                LIST_SKETCH_CONSTRAINT_EXPRESSIONS_TOOL,
                {"document_name": "TestDocument", "sketch_name": "Target"},
            )
        ),
    )[1]

    assert name_result["code"] == "sketch_constraint_name_set"
    assert expression_result["code"] == "sketch_constraint_expression_set"
    assert clear_result["code"] == "sketch_constraint_expression_cleared"
    assert list_result["code"] == "sketch_constraint_expressions_listed"
    assert adapter.set_sketch_constraint_name_calls == [("TestDocument", "Source", 0, "SideLength")]
    assert adapter.set_sketch_constraint_expression_calls == [
        (
            "TestDocument",
            "Target",
            0,
            "Source.Constraints.SideLength / (2 * sqrt(3))",
        )
    ]
    assert adapter.clear_sketch_constraint_expression_calls == [("TestDocument", "Target", 0)]
    assert adapter.list_sketch_constraint_expressions_calls == [("TestDocument", "Target")]


@pytest.mark.parametrize(
    ("tool_name", "payload"),
    [
        (
            SET_SKETCH_CONSTRAINT_NAME_TOOL,
            {
                "document_name": "TestDocument",
                "sketch_name": "Source",
                "constraint_index": 0,
                "name": "SideLength",
                "native_name": "unsafe",
            },
        ),
        (
            SET_SKETCH_CONSTRAINT_EXPRESSION_TOOL,
            {
                "document_name": "TestDocument",
                "sketch_name": "Target",
                "constraint_index": 0,
                "expression": "7 mm",
                "python": "unsafe",
            },
        ),
    ],
)
def test_constraint_expression_tools_reject_extra_arguments(
    tool_name: str,
    payload: dict[str, object],
) -> None:
    with pytest.raises(ToolError):
        asyncio.run(_server().call_tool(tool_name, payload))
