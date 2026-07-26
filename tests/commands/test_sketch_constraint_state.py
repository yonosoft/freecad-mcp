"""Focused tests for Milestone 25 constraint state management commands."""

from __future__ import annotations

from typing import Any

import pytest

from freecad_mcp.commands.sketch_constraint_state import (
    SetSketchConstraintActiveHandler,
    SetSketchConstraintDrivingHandler,
    SetSketchConstraintVirtualSpaceHandler,
)
from freecad_mcp.core.result import CommandResult
from freecad_mcp.exceptions import SketchConstraintStateUnsafeError
from freecad_mcp.validation import (
    validate_set_sketch_constraint_active_request,
    validate_set_sketch_constraint_driving_request,
    validate_set_sketch_constraint_virtual_space_request,
)


class _Dispatcher:
    def call(self, operation: Any) -> Any:
        return operation()


class _Result:
    def __init__(self, driving: bool = True, no_change: bool = False) -> None:
        self.no_change = no_change
        self.driving = driving

    def to_dict(self) -> dict[str, object]:
        return {
            "constraint_index": 0,
            "constraint_type": "distance",
            "requested_state": {"driving": self.driving},
            "previous_state": {"driving": True, "active": True, "virtual_space": False},
            "before_constraint": {
                "index": 0,
                "type": "distance",
                "name": None,
                "active": True,
                "virtual_space": False,
                "driving": True,
                "references": [],
                "value": {"value": 20.0, "unit": "millimeter"},
                "expression": None,
                "expression_supported": None,
            },
            "after_constraint": {
                "index": 0,
                "type": "distance",
                "name": None,
                "active": True,
                "virtual_space": False,
                "driving": self.driving,
                "references": [],
                "value": {"value": 20.0, "unit": "millimeter"},
                "expression": None,
                "expression_supported": None,
            },
            "changed": not self.no_change,
            "transaction_committed": not self.no_change,
            "affected_geometry_indices": [],
        }


class _Adapter:
    def __init__(self) -> None:
        self.driving_calls: list[tuple[str, str, int, bool]] = []
        self.active_calls: list[tuple[str, str, int, bool]] = []
        self.virtual_calls: list[tuple[str, str, int, bool]] = []
        self.no_change = False
        self.unsafe: str | None = None

    def set_sketch_constraint_driving(
        self,
        document_name: str,
        sketch_name: str,
        constraint_index: int,
        driving: bool,
    ) -> Any:
        self.driving_calls.append((document_name, sketch_name, constraint_index, driving))
        if self.unsafe == "driving":
            raise SketchConstraintStateUnsafeError(
                reason="test_reason", constraint_index=constraint_index
            )
        return _Result(driving=driving, no_change=self.no_change)

    def set_sketch_constraint_active(
        self,
        document_name: str,
        sketch_name: str,
        constraint_index: int,
        active: bool,
    ) -> Any:
        self.active_calls.append((document_name, sketch_name, constraint_index, active))
        if self.unsafe == "active":
            raise SketchConstraintStateUnsafeError(
                reason="test_reason", constraint_index=constraint_index
            )
        return _Result(driving=active, no_change=self.no_change)

    def set_sketch_constraint_virtual_space(
        self,
        document_name: str,
        sketch_name: str,
        constraint_index: int,
        virtual: bool,
    ) -> Any:
        self.virtual_calls.append((document_name, sketch_name, constraint_index, virtual))
        if self.unsafe == "virtual":
            raise SketchConstraintStateUnsafeError(
                reason="test_reason", constraint_index=constraint_index
            )
        return _Result(driving=virtual, no_change=self.no_change)

    def update_sketch_geometry(
        self,
        document_name: str,
        sketch_name: str,
        geometry_index: int,
        geometry: Any,
    ) -> Any:
        raise NotImplementedError

    def replace_sketch_constraint(
        self,
        document_name: str,
        sketch_name: str,
        constraint_index: int,
        replacement: Any,
    ) -> Any:
        raise NotImplementedError

    def update_sketch_constraint_value(
        self,
        document_name: str,
        sketch_name: str,
        constraint_index: int,
        value: float,
    ) -> Any:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Validation tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_driving", [1, "yes", None, [], {}])
def test_validate_driving_rejects_non_bool(bad_driving: object) -> None:
    result = validate_set_sketch_constraint_driving_request("Doc", "Sketch", 0, bad_driving)
    assert isinstance(result, CommandResult)
    assert result.code == "validation_error"
    assert result.data["field"] == "driving"


@pytest.mark.parametrize("bad_index", [-1, -5])
def test_validate_driving_rejects_negative_index(bad_index: int) -> None:
    result = validate_set_sketch_constraint_driving_request("Doc", "Sketch", bad_index, True)
    assert isinstance(result, CommandResult)
    assert result.code == "validation_error"
    assert result.data["field"] == "constraint_index"


@pytest.mark.parametrize("bad_value", [1, "yes", None])
def test_validate_active_rejects_non_bool(bad_value: object) -> None:
    result = validate_set_sketch_constraint_active_request("Doc", "Sketch", 0, bad_value)
    assert isinstance(result, CommandResult)
    assert result.code == "validation_error"
    assert result.data["field"] == "active"


@pytest.mark.parametrize("bad_value", [1, "yes", None])
def test_validate_virtual_rejects_non_bool(bad_value: object) -> None:
    result = validate_set_sketch_constraint_virtual_space_request("Doc", "Sketch", 0, bad_value)
    assert isinstance(result, CommandResult)
    assert result.code == "validation_error"
    assert result.data["field"] == "virtual"


def test_validate_driving_accepts_valid() -> None:
    result = validate_set_sketch_constraint_driving_request("Doc", "Sketch", 2, True)
    assert not isinstance(result, CommandResult)
    index, driving = result
    assert index == 2
    assert driving is True


@pytest.mark.parametrize("bad_doc", [123, None, "", []])
def test_validate_driving_rejects_bad_document(bad_doc: object) -> None:
    result = validate_set_sketch_constraint_driving_request(bad_doc, "Sketch", 0, True)
    assert isinstance(result, CommandResult)
    assert result.code == "validation_error"


@pytest.mark.parametrize("bad_sketch", [123, None, ""])
def test_validate_driving_rejects_bad_sketch(bad_sketch: object) -> None:
    result = validate_set_sketch_constraint_driving_request("Doc", bad_sketch, 0, True)
    assert isinstance(result, CommandResult)
    assert result.code == "validation_error"


# ---------------------------------------------------------------------------
# Driving handler tests
# ---------------------------------------------------------------------------


def test_driving_handler_delegates_correctly() -> None:
    adapter = _Adapter()
    handler = SetSketchConstraintDrivingHandler(adapter, _Dispatcher())
    result = handler.execute("Model", "Sketch", 3, False)
    assert result.code == "sketch_constraint_driving_set"
    assert adapter.driving_calls == [("Model", "Sketch", 3, False)]


def test_driving_handler_unsafe_error() -> None:
    adapter = _Adapter()
    adapter.unsafe = "driving"
    handler = SetSketchConstraintDrivingHandler(adapter, _Dispatcher())
    result = handler.execute("Model", "Sketch", 0, True)
    assert result.code == "sketch_constraint_state_unsafe"
    assert result.data["reason"] == "test_reason"
    assert result.data["constraint_index"] == 0


def test_driving_handler_no_change() -> None:
    adapter = _Adapter()
    adapter.no_change = True
    handler = SetSketchConstraintDrivingHandler(adapter, _Dispatcher())
    result = handler.execute("Model", "Sketch", 0, True)
    assert result.code == "sketch_constraint_driving_unchanged"
    assert result.data["changed"] is False


def test_driving_handler_success() -> None:
    adapter = _Adapter()
    handler = SetSketchConstraintDrivingHandler(adapter, _Dispatcher())
    result = handler.execute("Model", "Sketch", 0, False)
    assert result.code == "sketch_constraint_driving_set"
    assert result.data["constraint_index"] == 0
    assert result.data["requested_state"] == {"driving": False}


# ---------------------------------------------------------------------------
# Active handler tests
# ---------------------------------------------------------------------------


def test_active_handler_delegates_correctly() -> None:
    adapter = _Adapter()
    handler = SetSketchConstraintActiveHandler(adapter, _Dispatcher())
    result = handler.execute("Model", "Sketch", 5, True)
    assert result.code == "sketch_constraint_active_set"
    assert adapter.active_calls == [("Model", "Sketch", 5, True)]


def test_active_handler_unsafe_error() -> None:
    adapter = _Adapter()
    adapter.unsafe = "active"
    handler = SetSketchConstraintActiveHandler(adapter, _Dispatcher())
    result = handler.execute("Model", "Sketch", 0, False)
    assert result.code == "sketch_constraint_state_unsafe"
    assert result.data["reason"] == "test_reason"
    assert result.data["constraint_index"] == 0


# ---------------------------------------------------------------------------
# Virtual space handler tests
# ---------------------------------------------------------------------------


def test_virtual_handler_delegates_correctly() -> None:
    adapter = _Adapter()
    handler = SetSketchConstraintVirtualSpaceHandler(adapter, _Dispatcher())
    result = handler.execute("Model", "Sketch", 7, True)
    assert result.code == "sketch_constraint_virtual_space_set"
    assert adapter.virtual_calls == [("Model", "Sketch", 7, True)]


def test_virtual_handler_unsafe_error() -> None:
    adapter = _Adapter()
    adapter.unsafe = "virtual"
    handler = SetSketchConstraintVirtualSpaceHandler(adapter, _Dispatcher())
    result = handler.execute("Model", "Sketch", 0, True)
    assert result.code == "sketch_constraint_state_unsafe"
    assert result.data["reason"] == "test_reason"
    assert result.data["constraint_index"] == 0
