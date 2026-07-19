from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

import pytest

from freecad_mcp.commands.sketch_analysis import (
    AnalyzeSketchHandler,
    ListSketchOpenVerticesHandler,
    ValidateSketchProfileHandler,
)
from freecad_mcp.exceptions import (
    DocumentNotFoundError,
    InvalidGeometrySelectionError,
    ObjectNotFoundError,
    SketchAnalysisError,
    SketchTypeMismatchError,
)
from freecad_mcp.models import (
    DocumentSummary,
    SketchAnalysisRequestInput,
    SketchAnalysisResult,
    SketchOpenVerticesResult,
    SketchProfileAnalysisRequestInput,
    SketchProfileValidationResult,
)
from freecad_mcp.validation import (
    validate_analyze_sketch_request,
    validate_sketch_profile_analysis_request,
)

T = TypeVar("T")


class _Dispatcher:
    def call(self, operation: Callable[[], T]) -> T:
        return operation()


_DOCUMENT = DocumentSummary("Doc", "Doc", None, True, True, 1)


class _Adapter:
    def __init__(self) -> None:
        self.analyze_requests: list[SketchAnalysisRequestInput] = []
        self.profile_requests: list[SketchProfileAnalysisRequestInput] = []
        self.open_requests: list[SketchProfileAnalysisRequestInput] = []
        self.error: BaseException | None = None

    def _raise(self) -> None:
        if self.error is not None:
            raise self.error

    def analyze_sketch(self, request: SketchAnalysisRequestInput) -> SketchAnalysisResult:
        self._raise()
        self.analyze_requests.append(request)
        return SketchAnalysisResult(
            analysis={"topology": {}, "findings": [], "tolerance": 1e-7},
            sketch={"name": request.sketch_name},
            document=_DOCUMENT,
        )

    def validate_sketch_profile(
        self, request: SketchProfileAnalysisRequestInput
    ) -> SketchProfileValidationResult:
        self._raise()
        self.profile_requests.append(request)
        return SketchProfileValidationResult(
            validation={
                "valid": True,
                "classification": "single_closed_profile",
                "profile_count": 1,
                "profiles": [],
                "open_vertices": [],
                "findings": [],
            },
            sketch={"name": request.sketch_name},
            document=_DOCUMENT,
        )

    def list_sketch_open_vertices(
        self, request: SketchProfileAnalysisRequestInput
    ) -> SketchOpenVerticesResult:
        self._raise()
        self.open_requests.append(request)
        return SketchOpenVerticesResult(
            open_vertices=(),
            findings=(),
            sketch={"name": request.sketch_name},
            document=_DOCUMENT,
        )


def test_broad_validation_builds_strict_typed_request_with_defaults() -> None:
    result = validate_analyze_sketch_request("Doc", "Sketch")
    assert isinstance(result, SketchAnalysisRequestInput)
    assert result.include_construction is False
    assert result.include_external is False


@pytest.mark.parametrize("field_value", [0, 1, "true", None, [], {}])
def test_broad_validation_rejects_non_boolean_flags(field_value: object) -> None:
    result = validate_analyze_sketch_request("Doc", "Sketch", field_value, False)
    assert result.code == "validation_error"  # type: ignore[union-attr]


@pytest.mark.parametrize(
    "indices",
    [[], [-1], [True], [1.0], ["1"], [0, 0], (0, 1)],
)
def test_selection_validation_rejects_invalid_arrays(indices: object) -> None:
    result = validate_sketch_profile_analysis_request("Doc", "Sketch", indices)
    assert result.code == "validation_error"  # type: ignore[union-attr]


def test_selection_validation_preserves_unique_order() -> None:
    result = validate_sketch_profile_analysis_request(
        "Doc",
        "Sketch",
        [4, 1, 3],
        True,
        True,
    )
    assert isinstance(result, SketchProfileAnalysisRequestInput)
    assert result.geometry_indices == (4, 1, 3)
    assert result.include_construction is True
    assert result.include_external is True


@pytest.mark.parametrize(
    ("document_name", "sketch_name"),
    [("", "Sketch"), ("Doc", ""), ("Bad Name", "Sketch"), ("Doc", 4)],
)
def test_analysis_names_use_existing_controlled_name_policy(
    document_name: object, sketch_name: object
) -> None:
    result = validate_analyze_sketch_request(document_name, sketch_name)
    assert result.code == "validation_error"  # type: ignore[union-attr]


def test_handlers_delegate_typed_requests_and_controlled_results() -> None:
    adapter = _Adapter()
    dispatcher = _Dispatcher()
    analyze = AnalyzeSketchHandler(adapter, dispatcher).execute("Doc", "Sketch", True, False)
    validate = ValidateSketchProfileHandler(adapter, dispatcher).execute(
        "Doc", "Sketch", [3, 1], False, True
    )
    opened = ListSketchOpenVerticesHandler(adapter, dispatcher).execute("Doc", "Sketch")

    assert analyze.to_dict()["code"] == "sketch_analyzed"
    assert validate.to_dict()["code"] == "sketch_profile_validated"
    assert opened.to_dict()["code"] == "sketch_open_vertices_listed"
    assert adapter.analyze_requests[0].include_construction is True
    assert adapter.profile_requests[0].geometry_indices == (3, 1)
    assert adapter.profile_requests[0].include_external is True
    assert adapter.open_requests[0].geometry_indices is None


@pytest.mark.parametrize(
    ("error", "expected_code"),
    [
        (DocumentNotFoundError(), "document_not_found"),
        (ObjectNotFoundError(), "sketch_not_found"),
        (SketchTypeMismatchError(), "sketch_type_mismatch"),
        (
            InvalidGeometrySelectionError(missing_indices=(7, 9)),
            "invalid_geometry_selection",
        ),
        (
            SketchAnalysisError(phase="topology", reason="controlled_failure"),
            "profile_validation_failed",
        ),
        (RuntimeError("native secret"), "internal_error"),
    ],
)
def test_profile_handler_maps_controlled_errors_without_native_exception_text(
    error: BaseException, expected_code: str
) -> None:
    adapter = _Adapter()
    adapter.error = error
    result = ValidateSketchProfileHandler(adapter, _Dispatcher()).execute("Doc", "Sketch")
    payload = result.to_dict()
    assert payload["ok"] is False
    public_error = payload["error"]
    assert public_error["code"] == expected_code  # type: ignore[index]
    assert "native secret" not in str(payload)


def test_missing_selection_error_reports_controlled_indices() -> None:
    adapter = _Adapter()
    adapter.error = InvalidGeometrySelectionError(missing_indices=(7, 9))
    result = ValidateSketchProfileHandler(adapter, _Dispatcher()).execute(
        "Doc", "Sketch", [0, 7, 9]
    )
    error = result.to_dict()["error"]
    assert error["details"] == {  # type: ignore[index]
        "document_name": "Doc",
        "sketch_name": "Sketch",
        "geometry_indices": [0, 7, 9],
        "missing_geometry_indices": [7, 9],
    }
