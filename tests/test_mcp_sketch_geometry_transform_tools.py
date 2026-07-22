from __future__ import annotations

import asyncio
from typing import Any, cast

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from freecad_mcp.mcp.server import build_mcp_server
from freecad_mcp.mcp.sketch_geometry_transform_tools import (
    MIRROR_SKETCH_GEOMETRY_DESCRIPTION,
    POLAR_ARRAY_SKETCH_GEOMETRY_DESCRIPTION,
    RECTANGULAR_ARRAY_SKETCH_GEOMETRY_DESCRIPTION,
    ROTATE_SKETCH_GEOMETRY_DESCRIPTION,
    SCALE_SKETCH_GEOMETRY_DESCRIPTION,
    TRANSLATE_SKETCH_GEOMETRY_DESCRIPTION,
)
from freecad_mcp.server.config import ServerConfig
from freecad_mcp.tool_registry import (
    MIRROR_SKETCH_GEOMETRY_TOOL,
    POLAR_ARRAY_SKETCH_GEOMETRY_TOOL,
    RECTANGULAR_ARRAY_SKETCH_GEOMETRY_TOOL,
    ROTATE_SKETCH_GEOMETRY_TOOL,
    SCALE_SKETCH_GEOMETRY_TOOL,
    TRANSLATE_SKETCH_GEOMETRY_TOOL,
)
from mcp_server_stubs import make_handlers


def _server() -> Any:
    handlers, _adapter = make_handlers()
    return build_mcp_server(handlers, ServerConfig())


def test_milestone_24_appends_exact_tools_forty_three_through_forty_eight() -> None:
    names = [item.name for item in asyncio.run(_server().list_tools())]

    assert names[42:48] == [
        MIRROR_SKETCH_GEOMETRY_TOOL,
        TRANSLATE_SKETCH_GEOMETRY_TOOL,
        ROTATE_SKETCH_GEOMETRY_TOOL,
        SCALE_SKETCH_GEOMETRY_TOOL,
        RECTANGULAR_ARRAY_SKETCH_GEOMETRY_TOOL,
        POLAR_ARRAY_SKETCH_GEOMETRY_TOOL,
    ]


@pytest.mark.parametrize(
    ("tool_name", "description"),
    [
        (MIRROR_SKETCH_GEOMETRY_TOOL, MIRROR_SKETCH_GEOMETRY_DESCRIPTION),
        (TRANSLATE_SKETCH_GEOMETRY_TOOL, TRANSLATE_SKETCH_GEOMETRY_DESCRIPTION),
        (ROTATE_SKETCH_GEOMETRY_TOOL, ROTATE_SKETCH_GEOMETRY_DESCRIPTION),
        (SCALE_SKETCH_GEOMETRY_TOOL, SCALE_SKETCH_GEOMETRY_DESCRIPTION),
        (
            RECTANGULAR_ARRAY_SKETCH_GEOMETRY_TOOL,
            RECTANGULAR_ARRAY_SKETCH_GEOMETRY_DESCRIPTION,
        ),
        (POLAR_ARRAY_SKETCH_GEOMETRY_TOOL, POLAR_ARRAY_SKETCH_GEOMETRY_DESCRIPTION),
    ],
)
def test_transform_tool_schemas_are_closed_bounded_and_described(
    tool_name: str,
    description: str,
) -> None:
    tool = _server()._tool_manager.get_tool(tool_name)
    assert tool is not None
    schema = cast(dict[str, Any], tool.parameters)

    assert tool.description == description
    assert schema["additionalProperties"] is False
    selection = schema["properties"]["geometry_indices"]
    assert selection["minItems"] == 1
    assert selection["maxItems"] == 50
    assert selection["uniqueItems"] is True
    assert selection["items"]["minimum"] == 0
    assert "mode" not in schema["properties"]
    assert "never saves" in description
    assert "copy-only" in description


def test_mirror_reference_schema_is_discriminated_and_nested_models_are_closed() -> None:
    tool = _server()._tool_manager.get_tool(MIRROR_SKETCH_GEOMETRY_TOOL)
    assert tool is not None
    schema = cast(dict[str, Any], tool.parameters)
    reference = schema["properties"]["reference"]

    assert reference["discriminator"]["propertyName"] == "kind"
    assert len(reference["oneOf"]) == 3
    assert all(
        item["additionalProperties"] is False
        for name, item in schema["$defs"].items()
        if name.startswith("SketchMirror")
    )


def test_all_six_tools_delegate_exact_typed_requests() -> None:
    handlers, adapter = make_handlers()
    server = build_mcp_server(handlers, ServerConfig())
    common = {
        "document_name": "TestDocument",
        "sketch_name": "BaseSketch",
        "geometry_indices": [3, 1],
    }
    calls = (
        (MIRROR_SKETCH_GEOMETRY_TOOL, {**common, "reference": {"kind": "origin"}}),
        (
            TRANSLATE_SKETCH_GEOMETRY_TOOL,
            {**common, "displacement": {"x": 4.0, "y": -2.0}},
        ),
        (
            ROTATE_SKETCH_GEOMETRY_TOOL,
            {**common, "center": {"x": 0.0, "y": 0.0}, "angle_degrees": 45.0},
        ),
        (
            SCALE_SKETCH_GEOMETRY_TOOL,
            {**common, "center": {"x": 1.0, "y": 2.0}, "factor": 0.5},
        ),
        (
            RECTANGULAR_ARRAY_SKETCH_GEOMETRY_TOOL,
            {
                **common,
                "rows": 2,
                "columns": 3,
                "row_displacement": {"x": 0.0, "y": 5.0},
                "column_displacement": {"x": 8.0, "y": 0.0},
            },
        ),
        (
            POLAR_ARRAY_SKETCH_GEOMETRY_TOOL,
            {
                **common,
                "center": {"x": 0.0, "y": 0.0},
                "instance_count": 4,
                "step_angle_degrees": 90.0,
            },
        ),
    )

    results = [
        cast(tuple[list[Any], dict[str, object]], asyncio.run(server.call_tool(name, arguments)))[1]
        for name, arguments in calls
    ]

    assert all(result["ok"] is True for result in results)
    assert [item[0] for item in adapter.sketch_geometry_transform_calls] == [
        "mirror",
        "translate",
        "rotate",
        "scale",
        "rectangular_array",
        "polar_array",
    ]
    assert all(item[1][2] == (1, 3) for item in adapter.sketch_geometry_transform_calls)


@pytest.mark.parametrize(
    ("tool_name", "arguments"),
    [
        (
            MIRROR_SKETCH_GEOMETRY_TOOL,
            {"reference": {"kind": "horizontal_axis", "geometry_index": 0}},
        ),
        (
            TRANSLATE_SKETCH_GEOMETRY_TOOL,
            {"displacement": {"x": 1.0, "y": 0.0, "z": 0.0}},
        ),
        (
            ROTATE_SKETCH_GEOMETRY_TOOL,
            {"center": {"x": 0.0, "y": 0.0}, "angle_degrees": float("inf")},
        ),
        (
            SCALE_SKETCH_GEOMETRY_TOOL,
            {"center": {"x": 0.0, "y": 0.0}, "factor": 0.0},
        ),
        (
            RECTANGULAR_ARRAY_SKETCH_GEOMETRY_TOOL,
            {
                "rows": True,
                "columns": 2,
                "row_displacement": {"x": 0.0, "y": 5.0},
                "column_displacement": {"x": 8.0, "y": 0.0},
            },
        ),
        (
            POLAR_ARRAY_SKETCH_GEOMETRY_TOOL,
            {
                "center": {"x": 0.0, "y": 0.0},
                "instance_count": 1,
                "step_angle_degrees": 90.0,
            },
        ),
    ],
)
def test_transform_tools_reject_contract_expansion(
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
                    "geometry_indices": [0],
                    **arguments,
                },
            )
        )
