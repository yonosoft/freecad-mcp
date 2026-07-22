from __future__ import annotations

import asyncio
from typing import Any, cast

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from freecad_mcp.mcp.server import build_mcp_server
from freecad_mcp.server.config import ServerConfig
from freecad_mcp.tool_registry import (
    ADD_SKETCH_REFERENCE_CONSTRAINTS_TOOL,
    REGISTERED_TOOL_NAMES,
)
from mcp_server_stubs import make_handlers


def _server() -> Any:
    handlers, _ = make_handlers()
    return build_mcp_server(handlers, ServerConfig())


def test_reference_constraint_tool_is_exactly_tool_thirty_five() -> None:
    names = [tool.name for tool in asyncio.run(_server().list_tools())]

    assert len(names) == 39
    assert tuple(names) == REGISTERED_TOOL_NAMES
    assert names[:34] == list(REGISTERED_TOOL_NAMES[:34])
    assert names[34] == ADD_SKETCH_REFERENCE_CONSTRAINTS_TOOL


def test_reference_constraint_schema_is_strict_and_has_all_variants_modes() -> None:
    tool = _server()._tool_manager.get_tool(ADD_SKETCH_REFERENCE_CONSTRAINTS_TOOL)
    assert tool is not None
    schema = cast(dict[str, Any], tool.parameters)
    constraints = schema["properties"]["constraints"]
    items = constraints["items"]
    mapping = items["discriminator"]["mapping"]

    assert schema["additionalProperties"] is False
    assert schema["required"] == ["document_name", "sketch_name", "constraints"]
    assert constraints["minItems"] == 1
    assert constraints["maxItems"] == 100
    assert len(items["oneOf"]) == 17
    assert set(mapping) == {
        "angle",
        "coincident",
        "diameter",
        "distance",
        "distance_x",
        "distance_y",
        "equal",
        "horizontal",
        "horizontal_points",
        "parallel",
        "perpendicular",
        "point_on_object",
        "radius",
        "symmetric",
        "tangent",
        "vertical",
        "vertical_points",
    }
    assert set(mapping["distance"]["discriminator"]["mapping"]) == {
        "line_length",
        "point_to_origin",
        "between_points",
    }
    assert set(mapping["distance_x"]["discriminator"]["mapping"]) == {
        "point_to_origin",
        "between_points",
    }
    assert set(mapping["distance_y"]["discriminator"]["mapping"]) == {
        "point_to_origin",
        "between_points",
    }
    assert set(mapping["angle"]["discriminator"]["mapping"]) == {
        "line_angle",
        "between_lines",
    }
    definitions = schema["$defs"]
    object_definitions = [
        definition for definition in definitions.values() if definition.get("type") == "object"
    ]
    assert all(definition["additionalProperties"] is False for definition in object_definitions)
    assert definitions["SketchPointPosition"]["enum"] == ["start", "end", "center", "point"]
    assert (
        definitions["InternalSketchGeometryReferenceInput"]["properties"]["geometry_index"][
            "minimum"
        ]
        == 0
    )
    assert (
        definitions["ExternalSketchGeometryReferenceInput"]["properties"][
            "external_reference_number"
        ]["minimum"]
        == 0
    )


def test_reference_constraint_tool_delegates_once_without_mcp_chaining() -> None:
    handlers, adapter = make_handlers()
    server = build_mcp_server(handlers, ServerConfig())
    payload = {
        "document_name": "TestDocument",
        "sketch_name": "BaseSketch",
        "constraints": [
            {
                "type": "tangent",
                "first": {"kind": "internal", "geometry_index": 0},
                "second": {"kind": "external", "external_reference_number": 1},
            }
        ],
    }

    result = cast(
        tuple[list[Any], dict[str, object]],
        asyncio.run(server.call_tool(ADD_SKETCH_REFERENCE_CONSTRAINTS_TOOL, payload)),
    )[1]

    assert result["code"] == "sketch_reference_constraints_added"
    assert len(adapter.add_sketch_reference_constraints_calls) == 1
    assert adapter.add_sketch_constraints_calls == []
    parsed = adapter.add_sketch_reference_constraints_calls[0][2][0]
    assert parsed.type == "tangent"
    assert parsed.model_dump(mode="json") == payload["constraints"][0]


@pytest.mark.parametrize(
    "constraint",
    [
        {
            "type": "tangent",
            "first": {"kind": "internal", "geometry_index": True},
            "second": {"kind": "external", "external_reference_number": 0},
        },
        {
            "type": "tangent",
            "first": {"kind": "internal", "geometry_index": 0},
            "second": {"kind": "external", "external_reference_number": -1},
        },
        {
            "type": "tangent",
            "first": {"kind": "internal", "geometry_index": 0, "native_id": -3},
            "second": {"kind": "external", "external_reference_number": 0},
        },
    ],
)
def test_reference_constraint_tool_rejects_non_strict_or_native_identity_inputs(
    constraint: dict[str, object],
) -> None:
    with pytest.raises(ToolError):
        asyncio.run(
            _server().call_tool(
                ADD_SKETCH_REFERENCE_CONSTRAINTS_TOOL,
                {
                    "document_name": "TestDocument",
                    "sketch_name": "BaseSketch",
                    "constraints": [constraint],
                },
            )
        )
