from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from freecad_mcp.commands.sketch_diagnostics import DiagnoseSketchDoFHandler
from freecad_mcp.core.result import CommandResult
from freecad_mcp.exceptions import DocumentNotFoundError, SketchInspectionError
from freecad_mcp.models import SketchDoFDiagnosticsResult, SketchDoFGeometry

T = TypeVar("T")


class _Dispatcher:
    def call(self, operation: Callable[[], T]) -> T:
        return operation()


class _Adapter:
    def __init__(self, result: SketchDoFDiagnosticsResult | Exception) -> None:
        self.result = result
        self.calls: list[tuple[str, str]] = []

    def diagnose_sketch_dof(
        self,
        document_name: str,
        sketch_name: str,
    ) -> SketchDoFDiagnosticsResult:
        self.calls.append((document_name, sketch_name))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def _result() -> SketchDoFDiagnosticsResult:
    return SketchDoFDiagnosticsResult(
        document_name="Doc",
        sketch_name="Sketch",
        fully_constrained=False,
        degrees_of_freedom=1,
        unconstrained_geometry=(SketchDoFGeometry(geometry_index=17, type="line_segment"),),
    )


def test_handler_returns_compact_serializable_result() -> None:
    adapter = _Adapter(_result())
    handler = DiagnoseSketchDoFHandler(adapter, _Dispatcher())

    result = handler.execute("Doc", "Sketch")

    assert result.to_dict() == {
        "ok": True,
        "code": "sketch_dof_diagnosed",
        "message": "Diagnosed remaining sketch degrees of freedom.",
        "document_name": "Doc",
        "sketch_name": "Sketch",
        "fully_constrained": False,
        "degrees_of_freedom": 1,
        "unconstrained_geometry": [{"geometry_index": 17, "type": "line_segment"}],
    }
    assert adapter.calls == [("Doc", "Sketch")]


def test_handler_reuses_strict_two_name_validation() -> None:
    adapter = _Adapter(_result())
    handler = DiagnoseSketchDoFHandler(adapter, _Dispatcher())

    result = handler.execute(None, "Sketch")

    assert isinstance(result, CommandResult)
    assert result.code == "validation_error"
    assert adapter.calls == []


def test_handler_returns_controlled_native_inspection_failure() -> None:
    adapter = _Adapter(SketchInspectionError("dof_geometry_api_unavailable"))
    handler = DiagnoseSketchDoFHandler(adapter, _Dispatcher())

    result = handler.execute("Doc", "Sketch")

    assert result.ok is False
    assert result.code == "sketch_inspection_error"
    assert result.data == {
        "document_name": "Doc",
        "sketch_name": "Sketch",
        "reason": "dof_geometry_api_unavailable",
    }


def test_handler_preserves_existing_document_not_found_contract() -> None:
    adapter = _Adapter(DocumentNotFoundError("Missing"))
    handler = DiagnoseSketchDoFHandler(adapter, _Dispatcher())

    result = handler.execute("Missing", "Sketch")

    assert result.ok is False
    assert result.code == "document_not_found"
    assert result.data == {"document_name": "Missing"}
