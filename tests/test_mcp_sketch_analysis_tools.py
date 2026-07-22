from __future__ import annotations

import asyncio
from typing import Any, cast

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from freecad_mcp.mcp.server import build_mcp_server
from freecad_mcp.mcp.sketch_analysis_tools import (
    ANALYZE_SKETCH_DESCRIPTION,
    LIST_SKETCH_OPEN_VERTICES_DESCRIPTION,
    VALIDATE_SKETCH_PROFILE_DESCRIPTION,
)
from freecad_mcp.server.config import ServerConfig
from freecad_mcp.tool_registry import (
    ANALYZE_SKETCH_TOOL,
    LIST_SKETCH_OPEN_VERTICES_TOOL,
    VALIDATE_SKETCH_PROFILE_TOOL,
)
from mcp_server_stubs import make_handlers


def _server() -> Any:
    handlers, _ = make_handlers()
    return build_mcp_server(handlers, ServerConfig())


def test_analysis_tools_are_exactly_twenty_two_through_twenty_four() -> None:
    tools = asyncio.run(_server().list_tools())
    names = [item.name for item in tools]

    assert names[21:24] == [
        "analyze_sketch",
        "validate_sketch_profile",
        "list_sketch_open_vertices",
    ]


def test_analyze_sketch_has_strict_exact_schema_and_false_defaults() -> None:
    tool = _server()._tool_manager.get_tool(ANALYZE_SKETCH_TOOL)
    assert tool is not None
    schema = cast(dict[str, Any], tool.parameters)

    assert tool.description == ANALYZE_SKETCH_DESCRIPTION
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["document_name", "sketch_name"]
    assert set(schema["properties"]) == {
        "document_name",
        "sketch_name",
        "include_construction",
        "include_external",
    }
    assert schema["properties"]["include_construction"] == {
        "default": False,
        "title": "Include Construction",
        "type": "boolean",
    }
    assert schema["properties"]["include_external"]["default"] is False


@pytest.mark.parametrize(
    "tool_name",
    [VALIDATE_SKETCH_PROFILE_TOOL, LIST_SKETCH_OPEN_VERTICES_TOOL],
)
def test_selection_tools_share_strict_exact_schema(tool_name: str) -> None:
    tool = _server()._tool_manager.get_tool(tool_name)
    assert tool is not None
    schema = cast(dict[str, Any], tool.parameters)

    assert schema["additionalProperties"] is False
    assert schema["required"] == ["document_name", "sketch_name"]
    assert set(schema["properties"]) == {
        "document_name",
        "sketch_name",
        "geometry_indices",
        "include_construction",
        "include_external",
    }
    array_schema = schema["properties"]["geometry_indices"]["anyOf"][0]
    assert array_schema["minItems"] == 1
    assert array_schema["uniqueItems"] is True
    assert array_schema["items"] == {"minimum": 0, "type": "integer"}
    assert schema["properties"]["geometry_indices"]["default"] is None


def test_all_analysis_tools_delegate_once_with_defaults() -> None:
    handlers, adapter = make_handlers()
    server = build_mcp_server(handlers, ServerConfig())
    arguments = {"document_name": "TestDocument", "sketch_name": "BaseSketch"}

    analyzed = cast(
        tuple[list[Any], dict[str, object]],
        asyncio.run(server.call_tool(ANALYZE_SKETCH_TOOL, arguments)),
    )[1]
    validated = cast(
        tuple[list[Any], dict[str, object]],
        asyncio.run(server.call_tool(VALIDATE_SKETCH_PROFILE_TOOL, arguments)),
    )[1]
    opened = cast(
        tuple[list[Any], dict[str, object]],
        asyncio.run(server.call_tool(LIST_SKETCH_OPEN_VERTICES_TOOL, arguments)),
    )[1]

    assert analyzed["code"] == "sketch_analyzed"
    assert validated["code"] == "sketch_profile_validated"
    assert opened["code"] == "sketch_open_vertices_listed"
    assert len(adapter.analyze_sketch_calls) == 1
    assert len(adapter.validate_sketch_profile_calls) == 1
    assert len(adapter.list_sketch_open_vertices_calls) == 1
    assert adapter.analyze_sketch_calls[0].include_construction is False
    assert adapter.analyze_sketch_calls[0].include_external is False
    assert adapter.validate_sketch_profile_calls[0].geometry_indices is None


def test_selection_tools_delegate_ordered_unique_internal_indices() -> None:
    handlers, adapter = make_handlers()
    server = build_mcp_server(handlers, ServerConfig())

    output = cast(
        tuple[list[Any], dict[str, object]],
        asyncio.run(
            server.call_tool(
                VALIDATE_SKETCH_PROFILE_TOOL,
                {
                    "document_name": "TestDocument",
                    "sketch_name": "BaseSketch",
                    "geometry_indices": [3, 1],
                    "include_construction": True,
                    "include_external": True,
                },
            )
        ),
    )[1]

    request = adapter.validate_sketch_profile_calls[0]
    assert request.geometry_indices == (3, 1)
    assert request.include_construction is True
    assert request.include_external is True
    # The stub sketch is empty, so the controlled adapter rejects existence.
    assert output["ok"] is False
    assert output["error"]["code"] == "invalid_geometry_selection"  # type: ignore[index]


@pytest.mark.parametrize("flag", [0, 1, "false", None, [], {}])
def test_analysis_flags_are_strict_booleans(flag: object) -> None:
    with pytest.raises(ToolError):
        asyncio.run(
            _server().call_tool(
                ANALYZE_SKETCH_TOOL,
                {
                    "document_name": "TestDocument",
                    "sketch_name": "BaseSketch",
                    "include_construction": flag,
                },
            )
        )


@pytest.mark.parametrize("indices", [[], [-1], [True], [1.0], ["1"]])
def test_geometry_selection_rejects_empty_negative_and_non_strict_indices(
    indices: list[object],
) -> None:
    with pytest.raises(ToolError):
        asyncio.run(
            _server().call_tool(
                VALIDATE_SKETCH_PROFILE_TOOL,
                {
                    "document_name": "TestDocument",
                    "sketch_name": "BaseSketch",
                    "geometry_indices": indices,
                },
            )
        )


def test_duplicate_geometry_selection_returns_controlled_validation_error() -> None:
    result = cast(
        tuple[list[Any], dict[str, object]],
        asyncio.run(
            _server().call_tool(
                VALIDATE_SKETCH_PROFILE_TOOL,
                {
                    "document_name": "TestDocument",
                    "sketch_name": "BaseSketch",
                    "geometry_indices": [1, 1],
                },
            )
        ),
    )[1]
    assert result["ok"] is False
    error = cast(dict[str, object], result["error"])
    assert error["code"] == "validation_error"
    assert cast(dict[str, object], error["details"])["reason"] == "duplicate_geometry_index"


@pytest.mark.parametrize(
    ("tool_name", "extra"),
    [
        (ANALYZE_SKETCH_TOOL, {"tolerance": 0.01}),
        (ANALYZE_SKETCH_TOOL, {"repair": True}),
        (VALIDATE_SKETCH_PROFILE_TOOL, {"selection": [0]}),
        (LIST_SKETCH_OPEN_VERTICES_TOOL, {"recompute": True}),
    ],
)
def test_analysis_tools_forbid_extra_fields(tool_name: str, extra: dict[str, object]) -> None:
    with pytest.raises(ToolError):
        asyncio.run(
            _server().call_tool(
                tool_name,
                {
                    "document_name": "TestDocument",
                    "sketch_name": "BaseSketch",
                    **extra,
                },
            )
        )


def test_descriptions_protect_primary_tool_selection_and_read_only_scope() -> None:
    for phrase in ("broad read-only summary", "higher-level than get_sketch", "never modifies"):
        assert phrase in ANALYZE_SKETCH_DESCRIPTION
    for phrase in ("main question", "usable closed profiles", "selected internal"):
        assert phrase in VALIDATE_SKETCH_PROFILE_DESCRIPTION
    for phrase in ("where an open chain", "only degree-one endpoints", "does not close"):
        assert phrase in LIST_SKETCH_OPEN_VERTICES_DESCRIPTION


def test_constraint_union_remains_stable() -> None:
    server = _server()
    constraints = server._tool_manager.get_tool("add_sketch_constraints")
    assert constraints is not None
    assert len(constraints.parameters["properties"]["constraints"]["items"]["oneOf"]) == 17
