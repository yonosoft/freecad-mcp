from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar, cast

import pytest

from freecad_mcp.commands.document import (
    Dispatcher,
    DocumentAdapter,
    DocumentNotFoundError,
    FreeCADDocumentError,
    ObjectDetail,
    ObjectNotFoundError,
    PlacementData,
    PlacementPosition,
    PlacementRotation,
    validate_object_reference,
)
from freecad_mcp.commands.object_query import GetObjectHandler
from freecad_mcp.core.dispatch import DispatchError

T = TypeVar("T")


class RecordingDispatcher:
    def __init__(self) -> None:
        self.calls = 0

    def call(self, operation: Callable[[], T]) -> T:
        self.calls += 1
        return operation()


class GetObjectAdapterStub:
    def __init__(
        self,
        detail: ObjectDetail | None = None,
        error: Exception | None = None,
    ) -> None:
        self.detail = detail or _make_default_detail()
        self.error = error
        self.get_object_calls: list[tuple[str, str]] = []

    def get_object(self, document_name: str, object_name: str) -> ObjectDetail:
        self.get_object_calls.append((document_name, object_name))
        if self.error is not None:
            raise self.error
        return self.detail


def _make_default_detail() -> ObjectDetail:
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
    *,
    label: str | None = None,
    type_id: str = "PartDesign::Body",
    visibility: bool = True,
    parent: str | None = None,
    children: tuple[str, ...] = (),
    placement: PlacementData | None = None,
) -> ObjectDetail:
    return ObjectDetail(
        name=name,
        label=label or name,
        type_id=type_id,
        visibility=visibility,
        parent=parent,
        children=children,
        placement=placement,
    )


def make_handler(
    adapter: GetObjectAdapterStub | None = None,
    dispatcher: RecordingDispatcher | None = None,
) -> tuple[GetObjectHandler, RecordingDispatcher, GetObjectAdapterStub]:
    actual_adapter = adapter or GetObjectAdapterStub()
    actual_dispatcher = dispatcher or RecordingDispatcher()
    return (
        GetObjectHandler(cast(DocumentAdapter, actual_adapter), actual_dispatcher),
        actual_dispatcher,
        actual_adapter,
    )


# --- Validation: document_name ---


@pytest.mark.parametrize("name", [None, "", "   "])
def test_get_object_rejects_missing_or_empty_document_name(name: object) -> None:
    handler, dispatcher, adapter = make_handler()

    result = handler.execute(name, "Body")

    assert result.ok is False
    assert result.code == "validation_error"
    assert dispatcher.calls == 0
    assert adapter.get_object_calls == []


def test_get_object_rejects_non_string_document_name() -> None:
    handler, dispatcher, _adapter = make_handler()

    result = handler.execute(42, "Body")

    assert result.ok is False
    assert result.code == "validation_error"
    assert dispatcher.calls == 0


@pytest.mark.parametrize("name", ["Bracket Design", "2Brackets", "Bracket-Design"])
def test_get_object_rejects_document_names_freecad_would_sanitize(name: str) -> None:
    handler, dispatcher, _adapter = make_handler()

    result = handler.execute(name, "Body")

    assert result.ok is False
    assert result.code == "validation_error"
    assert dispatcher.calls == 0


# --- Validation: object_name ---


@pytest.mark.parametrize("name", [None, "", "   "])
def test_get_object_rejects_missing_or_empty_object_name(name: object) -> None:
    handler, dispatcher, adapter = make_handler()

    result = handler.execute("TestDoc", name)

    assert result.ok is False
    assert result.code == "validation_error"
    assert dispatcher.calls == 0
    assert adapter.get_object_calls == []


def test_get_object_rejects_non_string_object_name() -> None:
    handler, dispatcher, _adapter = make_handler()

    result = handler.execute("TestDoc", 42)

    assert result.ok is False
    assert result.code == "validation_error"
    assert dispatcher.calls == 0


@pytest.mark.parametrize("name", ["Body Part", "2Bodies", "Body-001"])
def test_get_object_rejects_object_names_freecad_would_sanitize(name: str) -> None:
    handler, dispatcher, _adapter = make_handler()

    result = handler.execute("TestDoc", name)

    assert result.ok is False
    assert result.code == "validation_error"
    assert dispatcher.calls == 0


# --- validate_object_reference function ---


def test_validate_object_reference_accepts_valid_names() -> None:
    assert validate_object_reference("TestDoc", "Body") is None


def test_validate_object_reference_rejects_empty_document_name() -> None:
    error = validate_object_reference("", "Body")
    assert error is not None
    assert error.ok is False
    assert error.code == "validation_error"


def test_validate_object_reference_rejects_empty_object_name() -> None:
    error = validate_object_reference("TestDoc", "")
    assert error is not None
    assert error.ok is False
    assert error.code == "validation_error"
    assert "object_name" in str(error.data)


# --- Success path ---


def test_get_object_returns_success_with_default_placement() -> None:
    handler, dispatcher, adapter = make_handler()

    result = handler.execute("TestDoc", "Body")

    assert result.ok is True
    assert result.code == "object_retrieved"
    assert result.message == "FreeCAD object retrieved."
    assert result.data["document_name"] == "TestDoc"
    result_dict = result.to_dict()
    assert "code" in result_dict
    assert result_dict["code"] == "object_retrieved"
    obj = cast(dict[str, object], result.data["object"])
    assert obj["name"] == "Body"
    assert obj["label"] == "Bracket Body"
    assert obj["type_id"] == "PartDesign::Body"
    assert obj["visibility"] is True
    assert obj["parent"] is None
    assert obj["children"] == []
    placement = cast(dict[str, object], obj["placement"])
    assert placement["position"] == {"x": 0.0, "y": 0.0, "z": 0.0}
    assert placement["rotation"] == {
        "axis": {"x": 0.0, "y": 0.0, "z": 1.0},
        "angle_degrees": 0.0,
    }
    assert dispatcher.calls == 1
    assert adapter.get_object_calls == [("TestDoc", "Body")]


def test_get_object_returns_null_placement_when_not_available() -> None:
    detail = make_detail("Sketch001", type_id="Sketcher::SketchObject", placement=None)
    adapter = GetObjectAdapterStub(detail=detail)

    result = make_handler(adapter=adapter)[0].execute("TestDoc", "Sketch001")

    assert result.ok is True
    obj = cast(dict[str, object], result.data["object"])
    assert obj["placement"] is None


# --- Hierarchy ---


def test_get_object_returns_parent_and_children() -> None:
    detail = make_detail(
        "Body",
        parent=None,
        children=("Pad001", "Sketch001"),
        placement=_make_default_detail().placement,
    )
    adapter = GetObjectAdapterStub(detail=detail)

    result = make_handler(adapter=adapter)[0].execute("TestDoc", "Body")

    obj = cast(dict[str, object], result.data["object"])
    assert obj["parent"] is None
    assert obj["children"] == ["Pad001", "Sketch001"]


# --- Visibility ---


def test_get_object_returns_visibility_true() -> None:
    detail = make_detail("Body", visibility=True, placement=_make_default_detail().placement)
    adapter = GetObjectAdapterStub(detail=detail)

    result = make_handler(adapter=adapter)[0].execute("TestDoc", "Body")

    obj = cast(dict[str, object], result.data["object"])
    assert obj["visibility"] is True


def test_get_object_returns_visibility_false() -> None:
    detail = make_detail("Body", visibility=False, placement=_make_default_detail().placement)
    adapter = GetObjectAdapterStub(detail=detail)

    result = make_handler(adapter=adapter)[0].execute("TestDoc", "Body")

    obj = cast(dict[str, object], result.data["object"])
    assert obj["visibility"] is False


# --- Error: document not found ---


def test_get_object_returns_document_not_found() -> None:
    adapter = GetObjectAdapterStub(error=DocumentNotFoundError("UnknownDoc"))

    result = make_handler(adapter=adapter)[0].execute("UnknownDoc", "Body")

    assert result.ok is False
    assert result.code == "document_not_found"
    assert result.data == {"document_name": "UnknownDoc"}


# --- Error: object not found ---


def test_get_object_returns_object_not_found() -> None:
    adapter = GetObjectAdapterStub(error=ObjectNotFoundError("Body001 not found"))

    result = make_handler(adapter=adapter)[0].execute("TestDoc", "Body001")

    assert result.ok is False
    assert result.code == "object_not_found"
    assert result.data == {"document_name": "TestDoc", "object_name": "Body001"}


# --- Error: adapter failure ---


def test_get_object_converts_adapter_failure() -> None:
    adapter = GetObjectAdapterStub(error=FreeCADDocumentError("inspection failed"))

    result = make_handler(adapter=adapter)[0].execute("TestDoc", "Body")

    assert result.ok is False
    assert result.code == "freecad_error"
    assert result.data["document_name"] == "TestDoc"
    assert result.data["object_name"] == "Body"
    assert result.data["reason"] == "inspection failed"


# --- Error: dispatch failure ---


def test_get_object_reports_dispatch_failure() -> None:
    class FailingDispatcher:
        def call(self, operation: Callable[[], object]) -> object:
            raise DispatchError("Qt is shutting down")

    handler = GetObjectHandler(
        cast(DocumentAdapter, GetObjectAdapterStub()),
        cast("Dispatcher", FailingDispatcher()),
    )

    result = handler.execute("TestDoc", "Body")

    assert result.ok is False
    assert result.code == "freecad_error"
    assert result.data["document_name"] == "TestDoc"
    assert result.data["object_name"] == "Body"
    assert result.data["reason"] == "Qt is shutting down"


# --- Dispatcher routing ---


def test_get_object_routes_through_dispatcher() -> None:
    handler, dispatcher, adapter = make_handler()

    handler.execute("TestDoc", "Body")

    assert dispatcher.calls == 1
    assert adapter.get_object_calls == [("TestDoc", "Body")]


# --- Placement details ---


def test_get_object_returns_nonzero_placement() -> None:
    detail = make_detail(
        "Body",
        placement=PlacementData(
            position=PlacementPosition(x=10.0, y=-5.5, z=0.0),
            rotation=PlacementRotation(
                axis=PlacementPosition(x=0.0, y=1.0, z=0.0),
                angle_degrees=45.0,
            ),
        ),
    )
    adapter = GetObjectAdapterStub(detail=detail)

    result = make_handler(adapter=adapter)[0].execute("TestDoc", "Body")

    obj = cast(dict[str, object], result.data["object"])
    placement = cast(dict[str, object], obj["placement"])
    assert placement["position"] == {"x": 10.0, "y": -5.5, "z": 0.0}
    assert placement["rotation"] == {
        "axis": {"x": 0.0, "y": 1.0, "z": 0.0},
        "angle_degrees": 45.0,
    }


def test_get_object_returns_fractional_coordinates() -> None:
    detail = make_detail(
        "Body",
        placement=PlacementData(
            position=PlacementPosition(x=-0.25, y=0.125, z=1.5),
            rotation=PlacementRotation(
                axis=PlacementPosition(x=1.0, y=0.0, z=0.0),
                angle_degrees=90.0,
            ),
        ),
    )
    adapter = GetObjectAdapterStub(detail=detail)

    result = make_handler(adapter=adapter)[0].execute("TestDoc", "Body")

    obj = cast(dict[str, object], result.data["object"])
    placement = cast(dict[str, object], obj["placement"])
    assert placement["position"] == {"x": -0.25, "y": 0.125, "z": 1.5}


def test_get_object_success_result_has_exact_outer_keys() -> None:
    """Regression: success result must include code, ok, document_name, object, message."""
    handler, _dispatcher, _adapter = make_handler()

    result = handler.execute("TestDoc", "Body")
    result_dict = result.to_dict()

    assert result.ok is True
    assert result.code == "object_retrieved"
    # Exact outer keys
    assert set(result_dict.keys()) == {"ok", "code", "document_name", "object", "message"}
    assert result_dict["ok"] is True
    assert result_dict["code"] == "object_retrieved"
    assert result_dict["document_name"] == "TestDoc"
    assert result_dict["message"] == "FreeCAD object retrieved."
