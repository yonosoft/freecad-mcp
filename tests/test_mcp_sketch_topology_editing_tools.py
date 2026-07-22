from __future__ import annotations

import asyncio
from typing import Any, cast

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from freecad_mcp.mcp.server import build_mcp_server
from freecad_mcp.mcp.sketch_topology_editing_tools import (
    EXTEND_SKETCH_GEOMETRY_DESCRIPTION,
    SPLIT_SKETCH_GEOMETRY_DESCRIPTION,
    TRIM_SKETCH_GEOMETRY_DESCRIPTION,
)
from freecad_mcp.models import SketchTopologyEndpoint
from freecad_mcp.server.config import ServerConfig
from freecad_mcp.tool_registry import (
    EXTEND_SKETCH_GEOMETRY_TOOL,
    REGISTERED_TOOL_NAMES,
    SPLIT_SKETCH_GEOMETRY_TOOL,
    TRIM_SKETCH_GEOMETRY_TOOL,
)
from mcp_server_stubs import make_handlers


def _server() -> Any:
    handlers, _ = make_handlers()
    return build_mcp_server(handlers, ServerConfig())


def test_milestone_23_appends_exact_tools_forty_through_forty_two() -> None:
    names = [item.name for item in asyncio.run(_server().list_tools())]

    assert len(names) == 42
    assert tuple(names) == REGISTERED_TOOL_NAMES
    assert names[39:] == [
        TRIM_SKETCH_GEOMETRY_TOOL,
        SPLIT_SKETCH_GEOMETRY_TOOL,
        EXTEND_SKETCH_GEOMETRY_TOOL,
    ]


@pytest.mark.parametrize(
    ("tool_name", "point_field", "description", "required"),
    [
        (
            TRIM_SKETCH_GEOMETRY_TOOL,
            "pick_point",
            TRIM_SKETCH_GEOMETRY_DESCRIPTION,
            ["document_name", "sketch_name", "geometry_index", "pick_point"],
        ),
        (
            SPLIT_SKETCH_GEOMETRY_TOOL,
            "point",
            SPLIT_SKETCH_GEOMETRY_DESCRIPTION,
            ["document_name", "sketch_name", "geometry_index", "point"],
        ),
        (
            EXTEND_SKETCH_GEOMETRY_TOOL,
            "target_point",
            EXTEND_SKETCH_GEOMETRY_DESCRIPTION,
            [
                "document_name",
                "sketch_name",
                "geometry_index",
                "endpoint",
                "target_point",
            ],
        ),
    ],
)
def test_topology_tool_schemas_are_closed_strict_and_explicit(
    tool_name: str,
    point_field: str,
    description: str,
    required: list[str],
) -> None:
    tool = _server()._tool_manager.get_tool(tool_name)
    assert tool is not None
    schema = cast(dict[str, Any], tool.parameters)

    assert tool.description == description
    assert schema["additionalProperties"] is False
    assert schema["required"] == required
    assert schema["properties"]["geometry_index"] == {
        "minimum": 0,
        "title": "Geometry Index",
        "type": "integer",
    }
    assert schema["properties"][point_field] == {"$ref": "#/$defs/SketchPoint2DInput"}
    point = schema["$defs"]["SketchPoint2DInput"]
    assert point["additionalProperties"] is False
    assert point["required"] == ["x", "y"]
    assert point["properties"]["x"]["type"] == "number"
    assert point["properties"]["y"]["type"] == "number"
    if tool_name == EXTEND_SKETCH_GEOMETRY_TOOL:
        assert schema["$defs"]["SketchTopologyEndpoint"]["enum"] == ["start", "end"]
        assert schema["properties"]["endpoint"] == {"$ref": "#/$defs/SketchTopologyEndpoint"}


def test_all_three_tools_delegate_exact_typed_requests() -> None:
    handlers, adapter = make_handlers()
    server = build_mcp_server(handlers, ServerConfig())
    names = {"document_name": "TestDocument", "sketch_name": "BaseSketch"}

    results = [
        cast(
            tuple[list[Any], dict[str, object]],
            asyncio.run(
                server.call_tool(
                    TRIM_SKETCH_GEOMETRY_TOOL,
                    {**names, "geometry_index": 2, "pick_point": {"x": 3.0, "y": 0.0}},
                )
            ),
        )[1],
        cast(
            tuple[list[Any], dict[str, object]],
            asyncio.run(
                server.call_tool(
                    SPLIT_SKETCH_GEOMETRY_TOOL,
                    {**names, "geometry_index": 3, "point": {"x": 4.0, "y": 1.0}},
                )
            ),
        )[1],
        cast(
            tuple[list[Any], dict[str, object]],
            asyncio.run(
                server.call_tool(
                    EXTEND_SKETCH_GEOMETRY_TOOL,
                    {
                        **names,
                        "geometry_index": 4,
                        "endpoint": "start",
                        "target_point": {"x": -5.0, "y": 2.0},
                    },
                )
            ),
        )[1],
    ]

    assert [result["code"] for result in results] == [
        "sketch_geometry_trimmed",
        "sketch_geometry_split",
        "sketch_geometry_extended",
    ]
    assert adapter.trim_sketch_geometry_calls[0][:3] == ("TestDocument", "BaseSketch", 2)
    assert adapter.trim_sketch_geometry_calls[0][3].model_dump() == {"x": 3.0, "y": 0.0}
    assert adapter.split_sketch_geometry_calls[0][:3] == ("TestDocument", "BaseSketch", 3)
    assert adapter.split_sketch_geometry_calls[0][3].model_dump() == {"x": 4.0, "y": 1.0}
    assert adapter.extend_sketch_geometry_calls[0][:4] == (
        "TestDocument",
        "BaseSketch",
        4,
        SketchTopologyEndpoint.START,
    )
    assert adapter.extend_sketch_geometry_calls[0][4].model_dump() == {"x": -5.0, "y": 2.0}


@pytest.mark.parametrize(
    ("tool_name", "arguments"),
    [
        (
            TRIM_SKETCH_GEOMETRY_TOOL,
            {"geometry_index": 0, "pick_point": {"x": 1.0, "y": 0.0}, "side": "left"},
        ),
        (
            SPLIT_SKETCH_GEOMETRY_TOOL,
            {"geometry_index": 0, "point": {"x": 1.0, "y": 0.0, "z": 0.0}},
        ),
        (
            EXTEND_SKETCH_GEOMETRY_TOOL,
            {
                "geometry_index": 0,
                "endpoint": "middle",
                "target_point": {"x": 2.0, "y": 0.0},
            },
        ),
        (
            EXTEND_SKETCH_GEOMETRY_TOOL,
            {
                "geometry_index": True,
                "endpoint": "end",
                "target_point": {"x": 2.0, "y": 0.0},
            },
        ),
    ],
)
def test_topology_tools_reject_contract_expansion(
    tool_name: str,
    arguments: dict[str, object],
) -> None:
    with pytest.raises(ToolError):
        asyncio.run(
            _server().call_tool(
                tool_name,
                {
                    "document_name": "TestDocument",
                    "sketch_name": "BaseSketch",
                    **arguments,
                },
            )
        )


def test_descriptions_lock_supported_domain_history_mapping_and_no_save_policy() -> None:
    assert "on-source pick point" in TRIM_SKETCH_GEOMETRY_DESCRIPTION
    assert "internal line-segment boundaries" in TRIM_SKETCH_GEOMETRY_DESCRIPTION
    assert "complete ordered geometry and constraint mappings" in (TRIM_SKETCH_GEOMETRY_DESCRIPTION)
    assert "1e-7" in SPLIT_SKETCH_GEOMETRY_DESCRIPTION
    assert "transaction-free no-ops" in SPLIT_SKETCH_GEOMETRY_DESCRIPTION
    assert "explicit finite collinear point" in EXTEND_SKETCH_GEOMETRY_DESCRIPTION
    assert "shortening" in EXTEND_SKETCH_GEOMETRY_DESCRIPTION
    assert all(
        "never saves" in description
        for description in (
            TRIM_SKETCH_GEOMETRY_DESCRIPTION,
            SPLIT_SKETCH_GEOMETRY_DESCRIPTION,
            EXTEND_SKETCH_GEOMETRY_DESCRIPTION,
        )
    )
