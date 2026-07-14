"""Comprehensive handler tests for CreateBodyHandler."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar, cast

import pytest

from freecad_mcp.commands.body import CreateBodyHandler
from freecad_mcp.commands.document import (
    BodyCreationError,
    DocumentAdapter,
    DocumentNotFoundError,
    FreeCADDocumentError,
    ObjectAlreadyExistsError,
    ObjectDetail,
    PlacementData,
    PlacementPosition,
    PlacementRotation,
)
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


class BodyAdapterStub:
    """Stub ``DocumentAdapter`` that records ``create_body`` calls."""

    def __init__(
        self,
        detail: ObjectDetail | None = None,
        error: Exception | None = None,
    ) -> None:
        self.detail = detail if detail is not None else _make_default_detail()
        self.error = error
        self.create_calls: list[tuple[str, str, str | None]] = []

    def create_body(self, document_name: str, name: str, label: str | None) -> ObjectDetail:
        self.create_calls.append((document_name, name, label))
        if self.error is not None:
            raise self.error
        return self.detail


# ---------------------------------------------------------------------------
# Detail builders
# ---------------------------------------------------------------------------


def _make_default_detail() -> ObjectDetail:
    """Return a standard PartDesign::Body detail with identity placement."""
    return ObjectDetail(
        name="Body",
        label="Bracket Body",
        type_id="PartDesign::Body",
        visibility=True,
        parent=None,
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
    name: str = "Body",
    label: str | None = "Bracket Body",
    type_id: str = "PartDesign::Body",
    visibility: bool = True,
    parent: str | None = None,
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
) -> tuple[CreateBodyHandler, RecordingDispatcher, DocumentAdapter]:
    """Return ``(handler, dispatcher, adapter)`` ready for assertions."""
    disp = dispatcher or RecordingDispatcher()
    body_adapter = adapter or BodyAdapterStub()
    handler = CreateBodyHandler(
        adapter=cast(DocumentAdapter, body_adapter),
        dispatcher=disp,
    )
    return handler, disp, cast(DocumentAdapter, body_adapter)


# ============================================================================
# Validation - document_name
# ============================================================================


@pytest.mark.parametrize("value", [None, "", "   "])
def test_document_name_absent_empty_or_whitespace_rejected(value: object) -> None:
    """A missing, empty or whitespace-only document_name returns a validation
    failure with ``field == "name"``."""
    handler, _, _ = make_handler()
    result = handler.execute(document_name=value, name="Body", label=None)
    assert result.ok is False
    data = result.data
    assert data["field"] == "name"


def test_document_name_must_be_string() -> None:
    """A non-str document_name (e.g. ``42``) is rejected."""
    handler, _, _ = make_handler()
    result = handler.execute(document_name=42, name="Body", label=None)
    assert result.ok is False
    assert result.data["field"] == "name"
    assert result.data["actual_type"] == "int"


@pytest.mark.parametrize("value", ["Bracket Design", "2Brackets", "Bracket-Design"])
def test_document_name_invalid_pattern_rejected(value: str) -> None:
    """Document names that would be sanitised by FreeCAD are rejected."""
    handler, _, _ = make_handler()
    result = handler.execute(document_name=value, name="Body", label=None)
    assert result.ok is False
    data = result.data
    assert data["field"] == "name"
    assert data.get("name") == value


# ============================================================================
# Validation - body name
# ============================================================================


@pytest.mark.parametrize("value", [None, "", "   "])
def test_body_name_absent_empty_or_whitespace_rejected(value: object) -> None:
    """A missing, empty, or whitespace-only object name is rejected with
    ``field == "name"``."""
    handler, _, _ = make_handler()
    result = handler.execute(document_name="TestDoc", name=value, label=None)
    assert result.ok is False
    assert result.data["field"] == "name"


def test_body_name_must_be_string() -> None:
    """Reject a non-str object name such as ``42``."""
    handler, _, _ = make_handler()
    result = handler.execute(document_name="TestDoc", name=42, label=None)
    assert result.ok is False
    assert result.data["field"] == "name"
    assert result.data["actual_type"] == "int"


@pytest.mark.parametrize("value", ["Body Part", "2Bodies", "Body-001"])
def test_body_name_invalid_pattern_rejected(value: str) -> None:
    """Object names that FreeCAD would sanitise are rejected."""
    handler, _, _ = make_handler()
    result = handler.execute(document_name="TestDoc", name=value, label=None)
    assert result.ok is False
    data = result.data
    assert data["field"] == "name"
    assert data.get("name") == value


# ============================================================================
# Validation - label
# ============================================================================


def test_omitted_label_is_accepted() -> None:
    """A body created without an explicit label is allowed."""
    handler, _, _ = make_handler()
    result = handler.execute(document_name="TestDoc", name="Body", label=None)
    assert result.ok is True


def test_non_string_label_is_rejected() -> None:
    """Supply a non-str label (e.g. ``42``) and expect a validation failure."""
    handler, _, _ = make_handler()
    result = handler.execute(document_name="TestDoc", name="Body", label=42)
    assert result.ok is False
    assert result.data["field"] == "label"


# ============================================================================
# Success
# ============================================================================


def test_dispatcher_called_exactly_once() -> None:
    """The dispatcher ``call`` is invoked exactly once for a successful
    creation."""
    handler, disp, raw_adapter = make_handler()
    adapter = cast(BodyAdapterStub, raw_adapter)
    handler.execute("TestDoc", "Body", "Bracket Body")
    assert disp.calls == 1
    assert adapter.create_calls == [("TestDoc", "Body", "Bracket Body")]


def test_success_result_has_required_keys() -> None:
    """The structured result contains ``ok``, ``code``, ``document_name``,
    ``object``, and ``message``."""
    handler, _, _ = make_handler()
    result = handler.execute("TestDoc", "Body", "Bracket Body")
    result_dict = result.to_dict()
    assert set(result_dict.keys()) == {"ok", "code", "document_name", "object", "message"}
    assert result_dict["ok"] is True
    assert result_dict["code"] == "body_created"
    assert result_dict["document_name"] == "TestDoc"
    obj = result_dict["object"]
    assert obj["name"] == "Body"  # type: ignore[index]
    assert obj["label"] == "Bracket Body"  # type: ignore[index]
    assert obj["type_id"] == "PartDesign::Body"  # type: ignore[index]


def test_default_placement_in_result() -> None:
    """The returned object contains an identity placement when the adapter
    returns the default detail."""
    handler, _, _ = make_handler()
    result = handler.execute("TestDoc", "Body", "Bracket Body")
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
    detail = make_detail(name="Custom", label="Custom Label")
    adapter = BodyAdapterStub(detail=detail)
    handler, _, _ = make_handler(adapter=cast(DocumentAdapter, adapter))
    result = handler.execute("Doc", "Custom", "Custom Label")
    assert result.data["object"]["label"] == "Custom Label"  # type: ignore[index]
    assert adapter.create_calls == [("Doc", "Custom", "Custom Label")]


def test_omitted_label_behaviour() -> None:
    """When a label is omitted (``None``), the adapter is called with
    ``label=None`` and the returned ``object.label`` comes from the
    adapter stub's default detail."""
    adapter = BodyAdapterStub()
    handler, _, _ = make_handler(adapter=cast(DocumentAdapter, adapter))
    result = handler.execute("Doc", "Body", None)
    # adapter call recorded with None
    assert adapter.create_calls == [("Doc", "Body", None)]
    # the stub always returns the default detail whose label is "Bracket Body"
    assert result.data["object"]["label"] == "Bracket Body"  # type: ignore[index]


# ============================================================================
# Error translation
# ============================================================================


def test_document_not_found_returns_expected_code() -> None:
    adapter = BodyAdapterStub(error=DocumentNotFoundError("missing"))
    handler, _, _ = make_handler(adapter=cast(DocumentAdapter, adapter))
    result = handler.execute("NonExistent", "Body", None)
    assert result.code == "document_not_found"


def test_object_already_exists_returns_expected_code() -> None:
    adapter = BodyAdapterStub(error=ObjectAlreadyExistsError("duplicate"))
    handler, _, _ = make_handler(adapter=cast(DocumentAdapter, adapter))
    result = handler.execute("Doc", "Body", None)
    assert result.code == "object_already_exists"


def test_body_creation_failed_returns_code_with_reason() -> None:
    error = BodyCreationError("boom")
    adapter = BodyAdapterStub(error=error)
    handler, _, _ = make_handler(adapter=cast(DocumentAdapter, adapter))
    result = handler.execute("Doc", "Body", None)
    assert result.code == "body_creation_failed"
    assert result.data["reason"] == "boom"


def test_dispatch_error_returns_freecad_error() -> None:
    class FailingDispatcher:
        def call(self, operation: Callable[[], object]) -> object:
            raise DispatchError("unreachable")

    adapter = BodyAdapterStub()
    handler = CreateBodyHandler(
        adapter=cast(DocumentAdapter, adapter),
        dispatcher=FailingDispatcher(),  # type: ignore[arg-type]
    )
    result = handler.execute("Doc", "Body", None)
    assert result.code == "freecad_error"
    assert "reason" in result.data


def test_freecad_document_error_returns_freecad_error_with_reason() -> None:
    adapter = BodyAdapterStub(error=FreeCADDocumentError("inspect failure"))
    handler, _, _ = make_handler(adapter=cast(DocumentAdapter, adapter))
    result = handler.execute("Doc", "Body", None)
    assert result.code == "freecad_error"
    assert result.data["reason"] == "inspect failure"


def test_generic_exception_returns_internal_error_with_reason() -> None:
    adapter = BodyAdapterStub(error=RuntimeError("unexpected"))
    handler, _, _ = make_handler(adapter=cast(DocumentAdapter, adapter))
    result = handler.execute("Doc", "Body", None)
    assert result.code == "internal_error"
    assert result.data["reason"] == "unexpected"
