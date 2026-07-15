"""Comprehensive handler tests for CreateSketchHandler."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar, cast

import pytest

from freecad_mcp.commands.document import (
    BodyNotFoundError,
    BodyTypeMismatchError,
    DocumentAdapter,
    DocumentNotFoundError,
    FreeCADDocumentError,
    ObjectAlreadyExistsError,
    ObjectDetail,
    PlacementData,
    PlacementPosition,
    PlacementRotation,
    SketchCreationError,
)
from freecad_mcp.commands.sketch import CreateSketchHandler
from freecad_mcp.core.dispatch import DispatchError

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Test fakes
# ---------------------------------------------------------------------------


class RecordingDispatcher:
    """Records every ``call`` invocation and executes the operation immediately."""

    def __init__(self) -> None:
        self.calls = 0

    def call(self, operation: Callable[[], T]) -> T:
        self.calls += 1
        return operation()


class SketchAdapterStub:
    """Stub ``DocumentAdapter`` that records ``create_sketch`` calls."""

    def __init__(
        self,
        detail: ObjectDetail | None = None,
        error: Exception | None = None,
    ) -> None:
        self.detail = detail if detail is not None else _make_default_detail()
        self.error = error
        self.create_calls: list[tuple[str, str, str, str | None]] = []

    def create_sketch(
        self, document_name: str, body_name: str, name: str, label: str | None
    ) -> ObjectDetail:
        self.create_calls.append((document_name, body_name, name, label))
        if self.error is not None:
            raise self.error
        return self.detail


# ---------------------------------------------------------------------------
# Detail builders
# ---------------------------------------------------------------------------


def _make_default_detail() -> ObjectDetail:
    """Return a standard Sketcher::SketchObject detail with identity placement."""
    return ObjectDetail(
        name="Sketch",
        label="Base Sketch",
        type_id="Sketcher::SketchObject",
        visibility=True,
        parent="Body",
        children=(),
        placement=PlacementData(
            position=PlacementPosition(x=0.0, y=0.0, z=0.0),
            rotation=PlacementRotation(
                axis=PlacementPosition(x=0.0, y=0.0, z=1.0),
                angle_degrees=0.0,
            ),
        ),
    )


def make_detail(
    name: str = "Sketch",
    label: str | None = "Sketch",
    type_id: str = "Sketcher::SketchObject",
    visibility: bool = True,
    parent: str | None = "Body",
    children: tuple[str, ...] = (),
    placement: PlacementData | None = None,
) -> ObjectDetail:
    """Create a fully specified ``ObjectDetail`` for use as a stub return value."""
    if placement is None:
        placement = PlacementData(
            position=PlacementPosition(x=0.0, y=0.0, z=0.0),
            rotation=PlacementRotation(
                axis=PlacementPosition(x=0.0, y=0.0, z=1.0),
                angle_degrees=0.0,
            ),
        )
    return ObjectDetail(
        name=name,
        label=label if label is not None else name,
        type_id=type_id,
        visibility=visibility,
        parent=parent,
        children=children,
        placement=placement,
    )


# ---------------------------------------------------------------------------
# Handler factory
# ---------------------------------------------------------------------------


def make_handler(
    adapter: DocumentAdapter | None = None,
    dispatcher: RecordingDispatcher | None = None,
) -> tuple[CreateSketchHandler, RecordingDispatcher, DocumentAdapter]:
    """Return ``(handler, dispatcher, adapter)`` ready for assertions."""
    disp = dispatcher or RecordingDispatcher()
    sketch_adapter = adapter or SketchAdapterStub()
    handler = CreateSketchHandler(
        adapter=cast(DocumentAdapter, sketch_adapter),
        dispatcher=disp,
    )
    return handler, disp, cast(DocumentAdapter, sketch_adapter)


# ============================================================================
# Validation - document_name
# ============================================================================


@pytest.mark.parametrize("value", [None, "", "   "])
def test_document_name_absent_empty_or_whitespace_rejected(value: object) -> None:
    """A missing, empty or whitespace-only document_name returns a validation
    failure with ``field == "name"``."""
    handler, _, _ = make_handler()
    result = handler.execute(document_name=value, body_name="Body", name="Sketch", label=None)
    assert result.ok is False
    data = result.data
    assert data["field"] == "name"


def test_document_name_must_be_string() -> None:
    """A non-str document_name (e.g. ``42``) is rejected."""
    handler, _, _ = make_handler()
    result = handler.execute(document_name=42, body_name="Body", name="Sketch", label=None)
    assert result.ok is False
    assert result.data["field"] == "name"
    assert result.data["actual_type"] == "int"


@pytest.mark.parametrize("value", ["Bracket Design", "2Brackets", "Bracket-Design"])
def test_document_name_invalid_pattern_rejected(value: str) -> None:
    """Document names that would be sanitised by FreeCAD are rejected."""
    handler, _, _ = make_handler()
    result = handler.execute(document_name=value, body_name="Body", name="Sketch", label=None)
    assert result.ok is False
    data = result.data
    assert data["field"] == "name"
    assert data.get("name") == value


# ============================================================================
# Validation - body_name
# ============================================================================


@pytest.mark.parametrize("value", [None, "", "   "])
def test_body_name_absent_empty_or_whitespace_rejected(value: object) -> None:
    """A missing, empty, or whitespace-only body name is rejected with
    ``field == "body_name"``."""
    handler, _, _ = make_handler()
    result = handler.execute(document_name="TestDoc", body_name=value, name="Sketch", label=None)
    assert result.ok is False
    assert result.data["field"] == "body_name"


def test_body_name_must_be_string() -> None:
    """Reject a non-str body name such as ``42``."""
    handler, _, _ = make_handler()
    result = handler.execute(document_name="TestDoc", body_name=42, name="Sketch", label=None)
    assert result.ok is False
    assert result.data["field"] == "body_name"
    assert result.data["actual_type"] == "int"


@pytest.mark.parametrize("value", ["Body Part", "2Bodies", "Body-001"])
def test_body_name_invalid_pattern_rejected(value: str) -> None:
    """Body names that FreeCAD would sanitise are rejected."""
    handler, _, _ = make_handler()
    result = handler.execute(document_name="TestDoc", body_name=value, name="Sketch", label=None)
    assert result.ok is False
    data = result.data
    assert data["field"] == "body_name"
    assert data.get("name") == value


# ============================================================================
# Validation - sketch name
# ============================================================================


@pytest.mark.parametrize("value", [None, "", "   "])
def test_sketch_name_absent_empty_or_whitespace_rejected(value: object) -> None:
    """A missing, empty, or whitespace-only sketch name is rejected with
    ``field == "name"``."""
    handler, _, _ = make_handler()
    result = handler.execute(document_name="TestDoc", body_name="Body", name=value, label=None)
    assert result.ok is False
    assert result.data["field"] == "name"


def test_sketch_name_must_be_string() -> None:
    """Reject a non-str sketch name such as ``42``."""
    handler, _, _ = make_handler()
    result = handler.execute(document_name="TestDoc", body_name="Body", name=42, label=None)
    assert result.ok is False
    assert result.data["field"] == "name"
    assert result.data["actual_type"] == "int"


@pytest.mark.parametrize("value", ["Sketch Part", "2Sketches", "Sketch-001"])
def test_sketch_name_invalid_pattern_rejected(value: str) -> None:
    """Sketch names that FreeCAD would sanitise are rejected."""
    handler, _, _ = make_handler()
    result = handler.execute(document_name="TestDoc", body_name="Body", name=value, label=None)
    assert result.ok is False
    data = result.data
    assert data["field"] == "name"
    assert data.get("name") == value


# ============================================================================
# Validation - label
# ============================================================================


def test_omitted_label_is_accepted() -> None:
    """A sketch created without an explicit label is allowed."""
    handler, _, _ = make_handler()
    result = handler.execute(document_name="TestDoc", body_name="Body", name="Sketch", label=None)
    assert result.ok is True


def test_non_string_label_is_rejected() -> None:
    """Supply a non-str label (e.g. ``42``) and expect a validation failure."""
    handler, _, _ = make_handler()
    result = handler.execute(document_name="TestDoc", body_name="Body", name="Sketch", label=42)
    assert result.ok is False
    assert result.data["field"] == "label"


# ============================================================================
# Success
# ============================================================================


def test_dispatcher_called_exactly_once() -> None:
    """The dispatcher ``call`` is invoked exactly once for a successful
    creation."""
    handler, disp, raw_adapter = make_handler()
    adapter = cast(SketchAdapterStub, raw_adapter)
    handler.execute("TestDoc", "Body", "Sketch", "Base Sketch")
    assert disp.calls == 1
    assert adapter.create_calls == [("TestDoc", "Body", "Sketch", "Base Sketch")]


def test_success_result_has_required_keys() -> None:
    """The structured result contains ``ok``, ``code``, ``document_name``,
    ``body_name``, ``object``, and ``message``."""
    handler, _, _ = make_handler()
    result = handler.execute("TestDoc", "Body", "Sketch", "Base Sketch")
    result_dict = result.to_dict()
    expected_keys = {"ok", "code", "document_name", "body_name", "object", "message"}
    assert set(result_dict.keys()) == expected_keys
    assert result_dict["ok"] is True
    assert result_dict["code"] == "sketch_created"
    assert result_dict["document_name"] == "TestDoc"
    assert result_dict["body_name"] == "Body"
    obj = result_dict["object"]
    assert obj["name"] == "Sketch"  # type: ignore[index]
    assert obj["label"] == "Base Sketch"  # type: ignore[index]
    assert obj["type_id"] == "Sketcher::SketchObject"  # type: ignore[index]


def test_default_placement_in_result() -> None:
    """The returned object contains an identity placement when the adapter
    returns the default detail."""
    handler, _, _ = make_handler()
    result = handler.execute("TestDoc", "Body", "Sketch", "Base Sketch")
    placement = result.data["object"]["placement"]  # type: ignore[index]
    assert placement["position"]["x"] == 0.0
    assert placement["position"]["y"] == 0.0
    assert placement["position"]["z"] == 0.0
    assert placement["rotation"]["angle_degrees"] == 0.0
    assert placement["rotation"]["axis"]["x"] == 0.0
    assert placement["rotation"]["axis"]["y"] == 0.0
    assert placement["rotation"]["axis"]["z"] == 1.0


def test_custom_label_preserved() -> None:
    """When a label is supplied, the returned object retains that label."""
    detail = make_detail(name="CustomSketch", label="Custom Label")
    adapter = SketchAdapterStub(detail=detail)
    handler, _, _ = make_handler(adapter=cast(DocumentAdapter, adapter))
    result = handler.execute("Doc", "Body", "CustomSketch", "Custom Label")
    assert result.data["object"]["label"] == "Custom Label"  # type: ignore[index]
    assert adapter.create_calls == [("Doc", "Body", "CustomSketch", "Custom Label")]


def test_omitted_label_behaviour() -> None:
    """When a label is omitted (``None``), the adapter is called with
    ``label=None`` and the returned ``object.label`` comes from the
    adapter stub's default detail."""
    adapter = SketchAdapterStub()
    handler, _, _ = make_handler(adapter=cast(DocumentAdapter, adapter))
    result = handler.execute("Doc", "Body", "Sketch", None)
    # adapter call recorded with None
    assert adapter.create_calls == [("Doc", "Body", "Sketch", None)]
    # the stub always returns the default detail whose label is "Base Sketch"
    assert result.data["object"]["label"] == "Base Sketch"  # type: ignore[index]


# ============================================================================
# Error translation
# ============================================================================


def test_document_not_found_returns_expected_code() -> None:
    adapter = SketchAdapterStub(error=DocumentNotFoundError("missing"))
    handler, _, _ = make_handler(adapter=cast(DocumentAdapter, adapter))
    result = handler.execute("NonExistent", "Body", "Sketch", None)
    assert result.code == "document_not_found"


def test_body_not_found_returns_expected_code() -> None:
    adapter = SketchAdapterStub(error=BodyNotFoundError("body missing"))
    handler, _, _ = make_handler(adapter=cast(DocumentAdapter, adapter))
    result = handler.execute("Doc", "MissingBody", "Sketch", None)
    assert result.code == "body_not_found"


def test_body_type_mismatch_returns_expected_code() -> None:
    adapter = SketchAdapterStub(error=BodyTypeMismatchError("wrong type"))
    handler, _, _ = make_handler(adapter=cast(DocumentAdapter, adapter))
    result = handler.execute("Doc", "Body", "Sketch", None)
    assert result.code == "body_type_mismatch"


def test_object_already_exists_returns_expected_code() -> None:
    adapter = SketchAdapterStub(error=ObjectAlreadyExistsError("duplicate"))
    handler, _, _ = make_handler(adapter=cast(DocumentAdapter, adapter))
    result = handler.execute("Doc", "Body", "Sketch", None)
    assert result.code == "object_already_exists"


def test_sketch_creation_failed_returns_code_with_reason() -> None:
    error = SketchCreationError("boom")
    adapter = SketchAdapterStub(error=error)
    handler, _, _ = make_handler(adapter=cast(DocumentAdapter, adapter))
    result = handler.execute("Doc", "Body", "Sketch", None)
    assert result.code == "sketch_creation_failed"
    assert result.data["reason"] == "boom"


def test_dispatch_error_returns_freecad_error() -> None:
    class FailingDispatcher:
        def call(self, operation: Callable[[], object]) -> object:
            raise DispatchError("unreachable")

    adapter = SketchAdapterStub()
    handler = CreateSketchHandler(
        adapter=cast(DocumentAdapter, adapter),
        dispatcher=FailingDispatcher(),  # type: ignore[arg-type]
    )
    result = handler.execute("Doc", "Body", "Sketch", None)
    assert result.code == "freecad_error"
    assert "reason" in result.data


def test_freecad_document_error_returns_freecad_error_with_reason() -> None:
    adapter = SketchAdapterStub(error=FreeCADDocumentError("inspect failure"))
    handler, _, _ = make_handler(adapter=cast(DocumentAdapter, adapter))
    result = handler.execute("Doc", "Body", "Sketch", None)
    assert result.code == "freecad_error"
    assert result.data["reason"] == "inspect failure"


def test_generic_exception_returns_internal_error_with_reason() -> None:
    adapter = SketchAdapterStub(error=RuntimeError("unexpected"))
    handler, _, _ = make_handler(adapter=cast(DocumentAdapter, adapter))
    result = handler.execute("Doc", "Body", "Sketch", None)
    assert result.code == "internal_error"
    assert result.data["reason"] == "unexpected"
