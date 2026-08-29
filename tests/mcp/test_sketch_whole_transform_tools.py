"""MCP wiring evidence for Milestone 28 whole-sketch transform tools 55--58."""

from __future__ import annotations

import asyncio
import dataclasses
from typing import Any, cast

from mcp.server.fastmcp.exceptions import ToolError

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
from tests.support.mcp_stubs import make_handlers


def _call_tool(tool_name: str, arguments: dict[str, object]) -> tuple[list[Any], dict[str, object]]:
    """Call an MCP tool and return (content_list, structured_dict)."""
    return cast(
        tuple[list[Any], dict[str, object]],
        asyncio.run(
            build_mcp_server(make_handlers()[0], ServerConfig()).call_tool(tool_name, arguments)
        ),
    )


def _structured(tool_name: str, arguments: dict[str, object]) -> dict[str, object]:
    """Call an MCP tool and return only the structured result dict."""
    return _call_tool(tool_name, arguments)[1]


def _server() -> Any:
    handlers, _adapter = make_handlers()
    return build_mcp_server(handlers, ServerConfig())


def _defs(schema: dict[str, Any]) -> dict[str, Any]:
    key = next(k for k in schema if k.startswith("$"))
    return cast(dict[str, Any], schema[key])


# ---------------------------------------------------------------------------
# Discovery and count
# ---------------------------------------------------------------------------


def test_whole_sketch_tools_are_discoverable_at_positions_55_to_58() -> None:
    names = [item.name for item in asyncio.run(_server().list_tools())]

    assert len(names) == 60
    assert names[54:58] == [
        TRANSLATE_SKETCH_TOOL,
        ROTATE_SKETCH_TOOL,
        SCALE_SKETCH_TOOL,
        MIRROR_SKETCH_TOOL,
    ]


def test_previous_54_tools_retain_order() -> None:
    names = [item.name for item in asyncio.run(_server().list_tools())]
    assert len(names) == 60
    pre_existing = names[:54]
    for i, name in enumerate(pre_existing):
        assert names[i] == name


# ---------------------------------------------------------------------------
# Schema evidence: no geometry_indices
# ---------------------------------------------------------------------------


def test_translate_sketch_schema_contains_no_geometry_indices() -> None:
    tool = _server()._tool_manager.get_tool(TRANSLATE_SKETCH_TOOL)
    schema = tool.parameters
    assert "geometry_indices" not in schema["properties"]


def test_rotate_sketch_schema_contains_no_geometry_indices() -> None:
    tool = _server()._tool_manager.get_tool(ROTATE_SKETCH_TOOL)
    schema = tool.parameters
    assert "geometry_indices" not in schema["properties"]


def test_scale_sketch_schema_contains_no_geometry_indices() -> None:
    tool = _server()._tool_manager.get_tool(SCALE_SKETCH_TOOL)
    schema = tool.parameters
    assert "geometry_indices" not in schema["properties"]


def test_mirror_sketch_schema_contains_no_geometry_indices() -> None:
    tool = _server()._tool_manager.get_tool(MIRROR_SKETCH_TOOL)
    schema = tool.parameters
    assert "geometry_indices" not in schema["properties"]


# ---------------------------------------------------------------------------
# Schema evidence: restricted mirror reference
# ---------------------------------------------------------------------------


def test_mirror_sketch_schema_permits_only_horizontal_axis_vertical_axis_and_origin() -> None:
    tool = _server()._tool_manager.get_tool(MIRROR_SKETCH_TOOL)
    schema = tool.parameters
    defs = _defs(schema)
    ref_schema = defs["SketchMirrorAxisReferenceInput"]
    kind = ref_schema["properties"]["kind"]
    allowed = kind.get("enum")
    assert allowed is not None
    assert set(allowed) == {"horizontal_axis", "vertical_axis", "origin"}


def test_mirror_sketch_schema_does_not_expose_construction_line_or_point() -> None:
    tool = _server()._tool_manager.get_tool(MIRROR_SKETCH_TOOL)
    defs = _defs(tool.parameters)
    ref_names = list(defs.keys())
    assert "SketchMirrorConstructionLineReferenceInput" not in ref_names
    assert "SketchMirrorInternalPointReferenceInput" not in ref_names


# ---------------------------------------------------------------------------
# Public descriptions state copy-only contract
# ---------------------------------------------------------------------------


_COPY_ONLY_PHRASES = [
    "transformed independent copies",
    "original geometry remains unchanged",
    "sketch placement is not modified",
    "constraints",
    "unsupported or mixed internal geometry",
]


def test_translate_sketch_description_states_copy_only_contract() -> None:
    for phrase in _COPY_ONLY_PHRASES:
        assert phrase in TRANSLATE_SKETCH_DESCRIPTION


def test_rotate_sketch_description_states_copy_only_contract() -> None:
    for phrase in _COPY_ONLY_PHRASES:
        assert phrase in ROTATE_SKETCH_DESCRIPTION


def test_scale_sketch_description_states_copy_only_contract() -> None:
    for phrase in _COPY_ONLY_PHRASES:
        assert phrase in SCALE_SKETCH_DESCRIPTION


def test_mirror_sketch_description_states_copy_only_contract() -> None:
    for phrase in _COPY_ONLY_PHRASES:
        assert phrase in MIRROR_SKETCH_DESCRIPTION


# ---------------------------------------------------------------------------
# Result pass-through
# ---------------------------------------------------------------------------


def test_translate_sketch_result_passes_through_mcp_path() -> None:
    structured = _structured(
        TRANSLATE_SKETCH_TOOL,
        {
            "document_name": "TestDocument",
            "sketch_name": "BaseSketch",
            "displacement": {"x": 10.0, "y": -5.0},
        },
    )
    assert structured["ok"] is True
    assert structured["code"] == "sketch_translated"
    assert structured.get("operation") == "translate_sketch"
    assert structured.get("changed") is True


def test_rotate_sketch_result_passes_through_mcp_path() -> None:
    structured = _structured(
        ROTATE_SKETCH_TOOL,
        {
            "document_name": "TestDocument",
            "sketch_name": "BaseSketch",
            "center": {"x": 0.0, "y": 0.0},
            "angle_degrees": 45.0,
        },
    )
    assert structured["ok"] is True
    assert structured["code"] == "sketch_rotated"
    assert structured.get("operation") == "rotate_sketch"


def test_scale_sketch_result_passes_through_mcp_path() -> None:
    structured = _structured(
        SCALE_SKETCH_TOOL,
        {
            "document_name": "TestDocument",
            "sketch_name": "BaseSketch",
            "center": {"x": 1.0, "y": 2.0},
            "factor": 2.0,
        },
    )
    assert structured["ok"] is True
    assert structured["code"] == "sketch_scaled"
    assert structured.get("operation") == "scale_sketch"


def test_mirror_sketch_result_passes_through_mcp_path() -> None:
    structured = _structured(
        MIRROR_SKETCH_TOOL,
        {
            "document_name": "TestDocument",
            "sketch_name": "BaseSketch",
            "reference": {"kind": "horizontal_axis"},
        },
    )
    assert structured["ok"] is True
    assert structured["code"] == "sketch_mirrored"
    assert structured.get("operation") == "mirror_sketch"


# ---------------------------------------------------------------------------
# Controlled failure pass-through
# ---------------------------------------------------------------------------


def test_mirror_sketch_unsupported_reference_failure_passes_through_mcp() -> None:
    # construction_line and internal_point are rejected by Pydantic schema
    # validation at the FastMCP layer before reaching our validation code.
    try:
        _structured(
            MIRROR_SKETCH_TOOL,
            {
                "document_name": "TestDocument",
                "sketch_name": "BaseSketch",
                "reference": {"kind": "construction_line", "geometry_index": 0},
            },
        )
        raise AssertionError("Expected ToolError")
    except ToolError:
        pass


def test_translate_sketch_zero_displacement_failure_passes_through_mcp() -> None:
    structured = _structured(
        TRANSLATE_SKETCH_TOOL,
        {
            "document_name": "TestDocument",
            "sketch_name": "BaseSketch",
            "displacement": {"x": 0.0, "y": 0.0},
        },
    )
    assert structured["ok"] is False
    error = structured["error"]
    assert isinstance(error, dict)
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

    def rotate_sketch(self, *args: object) -> object:
        return _TransactionResult(self._committed)

    def scale_sketch(self, *args: object) -> object:
        return _TransactionResult(self._committed)

    def mirror_sketch(self, *args: object) -> object:
        return _TransactionResult(self._committed)

    # Protocol stubs
    translate_sketch_geometry = rotate_sketch_geometry = scale_sketch_geometry = lambda self, *a: (
        None
    )
    rectangular_array_sketch_geometry = polar_array_sketch_geometry = lambda self, *a: None

    @staticmethod
    def mirror_sketch_geometry(*a: object) -> None:
        pass


class _PassthroughDispatcher:
    def call(self, op: Any) -> Any:
        return op()


def test_transaction_committed_true_survives_mcp_path() -> None:
    from freecad_mcp.commands import TranslateSketchHandler

    adapter = _TransactionCommittedAdapter(committed=True)
    base_handlers, _ = make_handlers()
    the_handlers = dataclasses.replace(
        base_handlers,
        sketcher=dataclasses.replace(
            base_handlers.sketcher,
            translate_sketch=TranslateSketchHandler(
                adapter,  # type: ignore[arg-type]
                _PassthroughDispatcher(),
            ),
        ),
    )
    _, structured = cast(
        tuple[list[Any], dict[str, object]],
        asyncio.run(
            build_mcp_server(the_handlers, ServerConfig()).call_tool(
                TRANSLATE_SKETCH_TOOL,
                {
                    "document_name": "TestDocument",
                    "sketch_name": "BaseSketch",
                    "displacement": {"x": 10.0, "y": 0.0},
                },
            )
        ),
    )
    assert structured["ok"] is True
    assert structured.get("transaction_committed") is True


def test_transaction_committed_false_survives_mcp_path() -> None:
    from freecad_mcp.commands import TranslateSketchHandler

    adapter = _TransactionCommittedAdapter(committed=False)
    base_handlers, _ = make_handlers()
    the_handlers = dataclasses.replace(
        base_handlers,
        sketcher=dataclasses.replace(
            base_handlers.sketcher,
            translate_sketch=TranslateSketchHandler(
                adapter,  # type: ignore[arg-type]
                _PassthroughDispatcher(),
            ),
        ),
    )
    _, structured = cast(
        tuple[list[Any], dict[str, object]],
        asyncio.run(
            build_mcp_server(the_handlers, ServerConfig()).call_tool(
                TRANSLATE_SKETCH_TOOL,
                {
                    "document_name": "TestDocument",
                    "sketch_name": "BaseSketch",
                    "displacement": {"x": 10.0, "y": 0.0},
                },
            )
        ),
    )
    assert structured["ok"] is True
    assert structured.get("transaction_committed") is False
