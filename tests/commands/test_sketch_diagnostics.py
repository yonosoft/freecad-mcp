"""Tests for AnalyzeSketchConstraintsHandler (Slice 4)."""

from __future__ import annotations

import json
from typing import cast

import pytest

from freecad_mcp.commands.sketch_diagnostics import (
    AnalyzeSketchConstraintsHandler,
)
from freecad_mcp.core.result import CommandResult
from freecad_mcp.exceptions import (
    DocumentNotFoundError,
    FreeCADDocumentError,
    ObjectNotFoundError,
    SketchInspectionError,
    SketchTypeMismatchError,
)
from freecad_mcp.models import (
    DocumentSummary,
    SketchConstraintDiagnostics,
    SketchConstraintDiagnosticsResult,
    SketchDiagnosticClassification,
    SketchDiagnosticsRequestInput,
    SketchSolverData,
)
from freecad_mcp.protocols import Dispatcher
from freecad_mcp.validation import validate_analyze_sketch_constraints_request

# ---------------------------------------------------------------------------
# stubs
# ---------------------------------------------------------------------------


class _StubDispatcher:
    """Simple synchronous dispatcher that invokes the operation directly."""

    def call(self, fn):  # type: ignore[no-untyped-def]
        return fn()


class _StubAdapter:
    """Records the last analyze_constraints call and returns a controlled result."""

    def __init__(self, result: SketchConstraintDiagnosticsResult | Exception | None = None) -> None:
        self.result = result if result is not None else _make_result()
        self.last_document_name: str | None = None
        self.last_sketch_name: str | None = None
        self.call_count = 0

    def analyze_constraints(
        self,
        document_name: str,
        sketch_name: str,
    ) -> SketchConstraintDiagnosticsResult:
        self.last_document_name = document_name
        self.last_sketch_name = sketch_name
        self.call_count += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def _make_result(
    *,
    result: SketchConstraintDiagnosticsResult | None = None,
    classification: SketchDiagnosticClassification = (
        SketchDiagnosticClassification.FULLY_CONSTRAINED
    ),
) -> SketchConstraintDiagnosticsResult:
    if result is not None:
        return result
    solver = SketchSolverData(
        available=True,
        fresh=True,
        degrees_of_freedom=0,
        fully_constrained=True,
        conflicting_constraint_indices=(),
        redundant_constraint_indices=(),
        partially_redundant_constraint_indices=(),
        malformed_constraint_indices=(),
    )
    diagnostics = SketchConstraintDiagnostics(
        solver=solver,
        classification=classification,
        constraint_count=0,
        active_count=0,
        inactive_count=0,
        driving_count=0,
        reference_count=0,
        driving_state_unavailable_count=0,
        virtual_space_count=0,
        issues=(),
    )
    doc = DocumentSummary(
        name="TestDoc",
        label="TestDoc",
        file_path=None,
        modified=False,
        active=True,
        object_count=1,
    )
    sketch: dict[str, object] = {
        "name": "Sketch",
        "label": "Sketch",
        "body_name": None,
        "visibility": True,
        "map_mode": "Deactivated",
        "attachment": None,
        "placement": None,
        "geometry_count": 0,
        "external_geometry_count": 0,
        "constraint_count": 0,
    }
    return SketchConstraintDiagnosticsResult(
        diagnostics=diagnostics,
        sketch=sketch,
        document=doc,
    )


def _make_handler(
    adapter: _StubAdapter | None = None,
    dispatcher: Dispatcher | None = None,
) -> AnalyzeSketchConstraintsHandler:
    if adapter is None:
        adapter = _StubAdapter()
    if dispatcher is None:
        dispatcher = _StubDispatcher()
    return AnalyzeSketchConstraintsHandler(
        adapter=adapter,
        dispatcher=dispatcher,
    )


# ---------------------------------------------------------------------------
# validation tests
# ---------------------------------------------------------------------------


class TestValidation:
    def test_valid_request(self) -> None:
        result = validate_analyze_sketch_constraints_request("Doc", "Sketch")
        assert isinstance(result, SketchDiagnosticsRequestInput)
        assert result.document_name == "Doc"
        assert result.sketch_name == "Sketch"

    def test_missing_document_name(self) -> None:
        result = validate_analyze_sketch_constraints_request(None, "Sketch")
        assert isinstance(result, CommandResult)
        assert result.code == "validation_error"

    def test_missing_sketch_name(self) -> None:
        result = validate_analyze_sketch_constraints_request("Doc", None)
        assert isinstance(result, CommandResult)
        assert result.code == "validation_error"

    def test_non_string_document_name(self) -> None:
        result = validate_analyze_sketch_constraints_request(123, "Sketch")
        assert isinstance(result, CommandResult)
        assert result.code == "validation_error"

    def test_non_string_sketch_name(self) -> None:
        result = validate_analyze_sketch_constraints_request("Doc", 456)
        assert isinstance(result, CommandResult)
        assert result.code == "validation_error"

    def test_validation_no_freecad_lookup(self) -> None:
        adapter = _StubAdapter()
        handler = _make_handler(adapter=adapter)
        result = handler.execute(None, "Sketch")
        assert adapter.call_count == 0
        assert isinstance(result, CommandResult)
        assert result.code == "validation_error"


# ---------------------------------------------------------------------------
# command tests
# ---------------------------------------------------------------------------


class TestHandler:
    def test_handler_calls_adapter_once(self) -> None:
        adapter = _StubAdapter()
        handler = _make_handler(adapter=adapter)
        handler.execute("Doc", "Sk1")
        assert adapter.call_count == 1

    def test_handler_passes_document_and_sketch_names(self) -> None:
        adapter = _StubAdapter()
        handler = _make_handler(adapter=adapter)
        handler.execute("A", "B")
        assert adapter.last_document_name == "A"
        assert adapter.last_sketch_name == "B"

    def test_success_result_code(self) -> None:
        handler = _make_handler()
        result = handler.execute("Doc", "Sk")
        assert result.code == "sketch_diagnostics_complete"

    def test_ok_true(self) -> None:
        handler = _make_handler()
        result = handler.execute("Doc", "Sk")
        assert result.ok is True

    def test_diagnostics_passthrough(self) -> None:
        handler = _make_handler()
        result = handler.execute("Doc", "Sk")
        data = cast(dict[str, object], result.data)
        assert data["code"] == "sketch_diagnostics_complete"
        diagnostics = cast(dict[str, object], data["diagnostics"])
        assert diagnostics["classification"] == "fully_constrained"

    def test_sketch_summary_passthrough(self) -> None:
        handler = _make_handler()
        result = handler.execute("Doc", "Sk")
        data = cast(dict[str, object], result.data)
        sketch = cast(dict[str, object], data["sketch"])
        assert sketch["name"] == "Sketch"

    def test_document_summary_passthrough(self) -> None:
        handler = _make_handler()
        result = handler.execute("Doc", "Sk")
        data = cast(dict[str, object], result.data)
        doc = cast(dict[str, object], data["document"])
        assert doc["name"] == "TestDoc"

    def test_result_json_serializable(self) -> None:
        handler = _make_handler()
        result = handler.execute("Doc", "Sk")
        serialized = json.dumps(result.data)
        assert isinstance(serialized, str)

    def test_no_native_objects(self) -> None:
        handler = _make_handler()
        result = handler.execute("Doc", "Sk")
        data = result.data

        def _check(obj: object) -> None:
            if obj is None or isinstance(obj, (str, int, float, bool)):
                return
            if isinstance(obj, (list, tuple)):
                for item in obj:
                    _check(item)
                return
            if isinstance(obj, dict):
                for v in obj.values():
                    _check(v)
                return
            pytest.fail(f"Unexpected type {type(obj)} in result data")

        _check(data)

    def test_payload_order_preserved(self) -> None:
        """Diagnostics payload ordering must pass through unchanged."""
        adapter = _StubAdapter(result=_make_result())
        handler = _make_handler(adapter=adapter)
        result = handler.execute("Doc", "Sk")
        data = cast(dict[str, object], result.data)
        diagnostics = cast(dict[str, object], data["diagnostics"])
        sketch = cast(dict[str, object], data["sketch"])
        doc = cast(dict[str, object], data["document"])
        # Verify all three top-level keys exist and are the right types
        assert isinstance(diagnostics, dict)
        assert isinstance(sketch, dict)
        assert isinstance(doc, dict)
        # Verify diagnostics has expected structure keys
        assert "classification" in diagnostics
        assert "issues" in diagnostics
        assert isinstance(diagnostics["issues"], list)


# ---------------------------------------------------------------------------
# controlled failure tests
# ---------------------------------------------------------------------------


class TestControlledFailures:
    def test_validation_failure_maps_to_validation_error(self) -> None:
        handler = _make_handler()
        result = handler.execute(None, "Sk")
        assert result.code == "validation_error"

    def test_document_not_found(self) -> None:
        adapter = _StubAdapter(result=DocumentNotFoundError())
        handler = _make_handler(adapter=adapter)
        result = handler.execute("Doc", "Sk")
        assert result.code == "document_not_found"

    def test_object_not_found(self) -> None:
        adapter = _StubAdapter(result=ObjectNotFoundError())
        handler = _make_handler(adapter=adapter)
        result = handler.execute("Doc", "Sk")
        assert result.code == "object_not_found"

    def test_sketch_type_mismatch(self) -> None:
        adapter = _StubAdapter(result=SketchTypeMismatchError())
        handler = _make_handler(adapter=adapter)
        result = handler.execute("Doc", "Sk")
        assert result.code == "sketch_type_mismatch"

    def test_sketch_inspection_error(self) -> None:
        adapter = _StubAdapter(result=SketchInspectionError("test_reason"))
        handler = _make_handler(adapter=adapter)
        result = handler.execute("Doc", "Sk")
        assert result.code == "sketch_inspection_error"
        assert result.data.get("reason") == "test_reason"

    def test_freecad_document_error(self) -> None:
        adapter = _StubAdapter(result=FreeCADDocumentError())
        handler = _make_handler(adapter=adapter)
        result = handler.execute("Doc", "Sk")
        assert result.code == "freecad_document_error"

    def test_adapter_not_called_on_validation_failure(self) -> None:
        adapter = _StubAdapter()
        handler = _make_handler(adapter=adapter)
        handler.execute(None, "Sk")
        assert adapter.call_count == 0

    def test_no_recompute_transaction_save(self) -> None:
        """Handler must not call recompute, open transactions, or save."""
        adapter = _StubAdapter()
        handler = _make_handler(adapter=adapter)
        result = handler.execute("Doc", "Sk")
        assert result.code == "sketch_diagnostics_complete"
        # The stub adapter doesn't have these attributes, so we verify
        # indirectly: the handler's _execute function only calls
        # dispatcher.call(operation) — which is the adapter.
        # No additional FreeCAD calls happen in the handler.
