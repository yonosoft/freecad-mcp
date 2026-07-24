"""MCP wiring evidence for Milestone 28 whole-sketch transform tools 55--58."""

from __future__ import annotations

import asyncio
import dataclasses
import json
from typing import Any, cast

from freecad_mcp.mcp.server import build_mcp_server
from freecad_mcp.mcp.sketch_whole_transform_tools import (
    MIRROR_SKETCH_DESCRIPTION,
    ROTATE_SKETCH_DESCRIPTION,
    SCALE_SKETCH_DESCRIPTION,
    TRANSLATE_SKETCH_DESCRIPTION,
)
from freecad_mcp.server.config import ServerConfig
from freecad_mcp.tool_registry import (
    MIRROR_SKETCH_TOOL,
    ROTATE_SKETCH_TOOL,
    SCALE_SKETCH_TOOL,
    TRANSLATE_SKETCH_TOOL,
)
from mcp_server_stubs import make_handlers


def _server() -> Any:
    handlers, _adapter = make_handlers()
    return build_mcp_server(handlers, ServerConfig())


def _defs(schema: dict[str, Any]) -> dict[str, Any]:
    key = next(k for k in schema if k.startswith(chr(36)))
    return schema[key]


# ---------------------------------------------------------------------------
# Discovery and count
# ---------------------------------------------------------------------------


def test_whole_sketch_tools_are_discoverable_at_positions_55_to_58() -> None:
    names = [item.name for item in asyncio.run(_server().list_tools())]

    assert len(names) == 58
    assert names[54:] == [
        TRANSLATE_SKETCH_TOOL,
        ROTATE_SKETCH_TOOL,
        SCALE_SKETCH_TOOL,
        MIRROR_SKETCH_TOOL,
    ]


def test_all_four_tools_are_retrievable_from_tool_manager() -> None:
    server = _server()
    for name in (
        TRANSLATE_SKETCH_TOOL,
        ROTATE_SKETCH_TOOL,
        SCALE_SKETCH_TOOL,
        MIRROR_SKETCH_TOOL,
    ):
        assert server._tool_manager.get_tool(name) is not None


# ---------------------------------------------------------------------------
# Schema — no geometry_indices
# ---------------------------------------------------------------------------


def test_whole_sketch_schemas_contain_no_geometry_indices_field() -> None:
    server = _server()
    for name in (
        TRANSLATE_SKETCH_TOOL,
        ROTATE_SKETCH_TOOL,
        SCALE_SKETCH_TOOL,
        MIRROR_SKETCH_TOOL,
    ):
        tool = server._tool_manager.get_tool(name)
        assert tool is not None
        schema = cast(dict[str, Any], tool.parameters)
        assert "geometry_indices" not in schema["properties"]


def test_whole_sketch_schemas_require_document_and_sketch_names() -> None:
    server = _server()
    for name in (
        TRANSLATE_SKETCH_TOOL,
        ROTATE_SKETCH_TOOL,
        SCALE_SKETCH_TOOL,
        MIRROR_SKETCH_TOOL,
    ):
        tool = server._tool_manager.get_tool(name)
        assert tool is not None
        schema = cast(dict[str, Any], tool.parameters)
        required = schema.get("required", [])
        assert "document_name" in required
        assert "sketch_name" in required


def test_whole_sketch_schemas_forbid_extra_fields() -> None:
    server = _server()
    for name in (
        TRANSLATE_SKETCH_TOOL,
        ROTATE_SKETCH_TOOL,
        SCALE_SKETCH_TOOL,
        MIRROR_SKETCH_TOOL,
    ):
        tool = server._tool_manager.get_tool(name)
        assert tool is not None
        schema = cast(dict[str, Any], tool.parameters)
        assert schema.get("additionalProperties") is False


# ---------------------------------------------------------------------------
# Mirror schema — restricted reference
# ---------------------------------------------------------------------------


def test_mirror_sketch_schema_permits_only_axis_and_origin() -> None:
    tool = _server()._tool_manager.get_tool(MIRROR_SKETCH_TOOL)
    assert tool is not None
    schema = cast(dict[str, Any], tool.parameters)

    # The reference field resolves to SketchMirrorAxisReferenceInput
    ref_path = schema["properties"]["reference"]["$ref"]
    def_name = ref_path.split("/")[-1]
    ref_schema = _defs(schema)[def_name]

    assert ref_schema["type"] == "object"
    assert ref_schema["additionalProperties"] is False
    assert "kind" in ref_schema["properties"]
    kind_schema = ref_schema["properties"]["kind"]
    assert kind_schema["type"] == "string"
    assert set(kind_schema["enum"]) == {"horizontal_axis", "vertical_axis", "origin"}

    # No geometry_index in the reference schema
    assert "geometry_index" not in ref_schema["properties"]

    # No discriminator or oneOf (it's a simple model, not a union)
    assert "discriminator" not in schema["properties"]["reference"]
    assert "oneOf" not in schema["properties"]["reference"]


def test_mirror_sketch_does_not_expose_construction_line_or_internal_point() -> None:
    tool = _server()._tool_manager.get_tool(MIRROR_SKETCH_TOOL)
    assert tool is not None
    schema = cast(dict[str, Any], tool.parameters)
    schema_str = json.dumps(schema)

    assert "construction_line" not in schema_str
    assert "internal_point" not in schema_str
    assert "SketchMirrorConstructionLineReferenceInput" not in schema_str
    assert "SketchMirrorInternalPointReferenceInput" not in schema_str


# ---------------------------------------------------------------------------
# Descriptions
# ---------------------------------------------------------------------------


_COPY_ONLY_PHRASES = (
    "copy-only",
    "original geometry remains unchanged",
    "sketch placement",
    "constraints",
)


def test_translate_sketch_description_states_copy_only_contract() -> None:
    tool = _server()._tool_manager.get_tool(TRANSLATE_SKETCH_TOOL)
    assert tool is not None
    assert tool.description == TRANSLATE_SKETCH_DESCRIPTION
    for phrase in _COPY_ONLY_PHRASES:
        assert phrase in tool.description.lower(), f"missing '{phrase}'"


def test_rotate_sketch_description_states_copy_only_contract() -> None:
    tool = _server()._tool_manager.get_tool(ROTATE_SKETCH_TOOL)
    assert tool is not None
    assert tool.description == ROTATE_SKETCH_DESCRIPTION
    for phrase in _COPY_ONLY_PHRASES:
        assert phrase in tool.description.lower(), f"missing '{phrase}'"


def test_scale_sketch_description_states_copy_only_contract() -> None:
    tool = _server()._tool_manager.get_tool(SCALE_SKETCH_TOOL)
    assert tool is not None
    assert tool.description == SCALE_SKETCH_DESCRIPTION
    for phrase in _COPY_ONLY_PHRASES:
        assert phrase in tool.description.lower(), f"missing '{phrase}'"


def test_mirror_sketch_description_states_copy_only_contract() -> None:
    tool = _server()._tool_manager.get_tool(MIRROR_SKETCH_TOOL)
    assert tool is not None
    assert tool.description == MIRROR_SKETCH_DESCRIPTION
    for phrase in _COPY_ONLY_PHRASES:
        assert phrase in tool.description.lower(), f"missing '{phrase}'"


# ---------------------------------------------------------------------------
# Successful result pass-through (end-to-end MCP path)
# ---------------------------------------------------------------------------


def test_translate_sketch_result_passes_through_mcp_path() -> None:
    handlers, _adapter = make_handlers()
    server = build_mcp_server(handlers, ServerConfig())
    _content, structured = asyncio.run(
        server.call_tool(
            TRANSLATE_SKETCH_TOOL,
            {
                "document_name": "TestDocument",
                "sketch_name": "BaseSketch",
                "displacement": {"x": 10.0, "y": -5.0},
            },
        )
    )
    assert structured["ok"] is True
    assert structured["code"] == "sketch_translated"
    assert structured.get("operation") == "translate_sketch"
    assert structured.get("changed") is True


def test_rotate_sketch_result_passes_through_mcp_path() -> None:
    handlers, _adapter = make_handlers()
    server = build_mcp_server(handlers, ServerConfig())
    _content, structured = asyncio.run(
        server.call_tool(
            ROTATE_SKETCH_TOOL,
            {
                "document_name": "TestDocument",
                "sketch_name": "BaseSketch",
                "center": {"x": 0.0, "y": 0.0},
                "angle_degrees": 45.0,
            },
        )
    )
    assert structured["ok"] is True
    assert structured["code"] == "sketch_rotated"
    assert structured.get("operation") == "rotate_sketch"


def test_scale_sketch_result_passes_through_mcp_path() -> None:
    handlers, _adapter = make_handlers()
    server = build_mcp_server(handlers, ServerConfig())
    _content, structured = asyncio.run(
        server.call_tool(
            SCALE_SKETCH_TOOL,
            {
                "document_name": "TestDocument",
                "sketch_name": "BaseSketch",
                "center": {"x": 1.0, "y": 2.0},
                "factor": 2.0,
            },
        )
    )
    assert structured["ok"] is True
    assert structured["code"] == "sketch_scaled"
    assert structured.get("operation") == "scale_sketch"


def test_mirror_sketch_result_passes_through_mcp_path() -> None:
    handlers, _adapter = make_handlers()
    server = build_mcp_server(handlers, ServerConfig())
    _content, structured = asyncio.run(
        server.call_tool(
            MIRROR_SKETCH_TOOL,
            {
                "document_name": "TestDocument",
                "sketch_name": "BaseSketch",
                "reference": {"kind": "horizontal_axis"},
            },
        )
    )
    assert structured["ok"] is True
    assert structured["code"] == "sketch_mirrored"
    assert structured.get("operation") == "mirror_sketch"


# ---------------------------------------------------------------------------
# Controlled failure pass-through
# ---------------------------------------------------------------------------


def test_mirror_sketch_unsupported_reference_failure_passes_through_mcp() -> None:
    handlers, _adapter = make_handlers()
    server = build_mcp_server(handlers, ServerConfig())

    # construction_line and internal_point are rejected by Pydantic schema
    # validation at the FastMCP layer before reaching our validation code.
    from mcp.server.fastmcp.exceptions import ToolError

    try:
        asyncio.run(
            server.call_tool(
                MIRROR_SKETCH_TOOL,
                {
                    "document_name": "TestDocument",
                    "sketch_name": "BaseSketch",
                    "reference": {"kind": "construction_line", "geometry_index": 0},
                },
            )
        )
        raise AssertionError("Expected ToolError")
    except ToolError:
        pass


def test_translate_sketch_zero_displacement_failure_passes_through_mcp() -> None:
    handlers, _adapter = make_handlers()
    server = build_mcp_server(handlers, ServerConfig())

    _content, structured = asyncio.run(
        server.call_tool(
            TRANSLATE_SKETCH_TOOL,
            {
                "document_name": "TestDocument",
                "sketch_name": "BaseSketch",
                "displacement": {"x": 0.0, "y": 0.0},
            },
        )
    )
    assert structured["ok"] is False
    error = structured["error"]
    assert error["code"] == "validation_error"
    assert error["details"]["reason"] == "zero_displacement"


# ---------------------------------------------------------------------------
# transaction_committed survival through MCP path
# ---------------------------------------------------------------------------


class _TransactionResult:
    def __init__(self, committed: bool) -> None:
        self._committed = committed

    def to_dict(self) -> dict[str, object]:
        return {
            "operation": "translate_sketch",
            "mode": "copy",
            "changed": True,
            "transaction_committed": self._committed,
        }


class _TransactionCommittedAdapter:
    def __init__(self, committed: bool) -> None:
        self._committed = committed

    def translate_sketch(self, *args: object) -> object:
        return _TransactionResult(self._committed)


class _PassthroughDispatcher:
    def call(self, op: Any) -> Any:
        return op()


def test_transaction_committed_true_survives_mcp_path() -> None:
    from freecad_mcp.commands import TranslateSketchHandler

    adapter = _TransactionCommittedAdapter(committed=True)
    base_handlers, _ = make_handlers()
    handlers = dataclasses.replace(
        base_handlers,
        translate_sketch=TranslateSketchHandler(adapter, _PassthroughDispatcher()),  # type: ignore[arg-type]
    )
    server = build_mcp_server(handlers, ServerConfig())
    _content, structured = asyncio.run(
        server.call_tool(
            TRANSLATE_SKETCH_TOOL,
            {
                "document_name": "TestDocument",
                "sketch_name": "BaseSketch",
                "displacement": {"x": 10.0, "y": 0.0},
            },
        )
    )
    assert structured["ok"] is True
    assert structured.get("transaction_committed") is True


def test_transaction_committed_false_survives_mcp_path() -> None:
    from freecad_mcp.commands import TranslateSketchHandler

    adapter = _TransactionCommittedAdapter(committed=False)
    base_handlers, _ = make_handlers()
    handlers = dataclasses.replace(
        base_handlers,
        translate_sketch=TranslateSketchHandler(adapter, _PassthroughDispatcher()),  # type: ignore[arg-type]
    )
    server = build_mcp_server(handlers, ServerConfig())
    _content, structured = asyncio.run(
        server.call_tool(
            TRANSLATE_SKETCH_TOOL,
            {
                "document_name": "TestDocument",
                "sketch_name": "BaseSketch",
                "displacement": {"x": 10.0, "y": 0.0},
            },
        )
    )
    assert structured["ok"] is True
    assert structured.get("transaction_committed") is False
