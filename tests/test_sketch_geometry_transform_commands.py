from __future__ import annotations

import math
from typing import Any

import pytest

from freecad_mcp.commands.sketch_geometry_transforms import (
    MirrorSketchGeometryHandler,
    MirrorSketchHandler,
    PolarArraySketchGeometryHandler,
    RectangularArraySketchGeometryHandler,
    RotateSketchGeometryHandler,
    RotateSketchHandler,
    ScaleSketchGeometryHandler,
    ScaleSketchHandler,
    TranslateSketchGeometryHandler,
    TranslateSketchHandler,
)
from freecad_mcp.exceptions import (
    DocumentNotFoundError,
    ObjectNotFoundError,
    SketchControlledMutationError,
    SketchControlledMutationRollbackError,
    SketchTypeMismatchError,
)
from freecad_mcp.models import (
    SketchMirrorAxisReferenceInput,
    SketchMirrorConstructionLineReferenceInput,
    SketchPoint2DInput,
)
from mcp_server_stubs import AdapterStub, DispatcherStub, _SemanticResultStub


def _handlers() -> tuple[dict[str, Any], AdapterStub]:
    adapter = AdapterStub()
    dispatcher = DispatcherStub()
    return (
        {
            "mirror": MirrorSketchGeometryHandler(adapter, dispatcher),
            "translate": TranslateSketchGeometryHandler(adapter, dispatcher),
            "rotate": RotateSketchGeometryHandler(adapter, dispatcher),
            "scale": ScaleSketchGeometryHandler(adapter, dispatcher),
            "rectangular": RectangularArraySketchGeometryHandler(adapter, dispatcher),
            "polar": PolarArraySketchGeometryHandler(adapter, dispatcher),
        },
        adapter,
    )


def test_all_transform_handlers_canonicalize_selection_and_delegate_typed_inputs() -> None:
    handlers, adapter = _handlers()
    names = ("TestDocument", "BaseSketch", [3, 1])

    assert handlers["mirror"].execute(*names, {"kind": "horizontal_axis"}).ok
    assert handlers["translate"].execute(*names, {"x": 4.0, "y": -2.0}).ok
    assert handlers["rotate"].execute(*names, {"x": 0.0, "y": 0.0}, -45.0).ok
    assert handlers["scale"].execute(*names, {"x": 1.0, "y": 2.0}, 0.5).ok
    assert (
        handlers["rectangular"]
        .execute(
            *names,
            2,
            3,
            {"x": 0.0, "y": 5.0},
            {"x": 8.0, "y": 0.0},
        )
        .ok
    )
    assert (
        handlers["polar"]
        .execute(
            *names,
            {"x": 0.0, "y": 0.0},
            4,
            90.0,
        )
        .ok
    )

    assert [item[0] for item in adapter.sketch_geometry_transform_calls] == [
        "mirror",
        "translate",
        "rotate",
        "scale",
        "rectangular_array",
        "polar_array",
    ]
    assert all(call[1][2] == (1, 3) for call in adapter.sketch_geometry_transform_calls)


def test_transform_handlers_return_stable_operation_specific_success_codes() -> None:
    handlers, _adapter = _handlers()
    names = ("TestDocument", "BaseSketch", [0])

    results = [
        handlers["mirror"].execute(*names, {"kind": "horizontal_axis"}),
        handlers["translate"].execute(*names, {"x": 4.0, "y": -2.0}),
        handlers["rotate"].execute(*names, {"x": 0.0, "y": 0.0}, -45.0),
        handlers["scale"].execute(*names, {"x": 1.0, "y": 2.0}, 0.5),
        handlers["rectangular"].execute(*names, 2, 3, {"x": 0.0, "y": 5.0}, {"x": 8.0, "y": 0.0}),
        handlers["polar"].execute(*names, {"x": 0.0, "y": 0.0}, 4, 90.0),
    ]

    assert [result.code for result in results] == [
        "sketch_geometry_mirrored",
        "sketch_geometry_translated",
        "sketch_geometry_rotated",
        "sketch_geometry_scaled",
        "sketch_geometry_rectangular_array_copied",
        "sketch_geometry_polar_array_copied",
    ]


@pytest.mark.parametrize("selection", [[], [0, 0], [True], [-1], [1.5], "0"])
def test_transform_selection_is_nonempty_unique_and_strict(selection: object) -> None:
    handlers, adapter = _handlers()
    result = handlers["translate"].execute(
        "TestDocument", "BaseSketch", selection, {"x": 1.0, "y": 0.0}
    )

    assert not result.ok
    assert result.code == "validation_error"
    assert adapter.sketch_geometry_transform_calls == []


# ---------------------------------------------------------------------------
# Milestone 28 Slice 4 — whole-sketch transform command handlers
# ---------------------------------------------------------------------------


def _whole_handlers() -> tuple[dict[str, Any], AdapterStub]:
    adapter = AdapterStub()
    dispatcher = DispatcherStub()
    return (
        {
            "translate": TranslateSketchHandler(adapter, dispatcher),
            "rotate": RotateSketchHandler(adapter, dispatcher),
            "scale": ScaleSketchHandler(adapter, dispatcher),
            "mirror": MirrorSketchHandler(adapter, dispatcher),
        },
        adapter,
    )


# ---------------------------------------------------------------------------
# Successful invocation
# ---------------------------------------------------------------------------


def test_translate_sketch_success() -> None:
    handlers, adapter = _whole_handlers()
    result = handlers["translate"].execute("Doc", "Sketch", {"x": 10.0, "y": -5.0})
    assert result.ok
    assert result.code == "sketch_translated"
    assert len(adapter.sketch_geometry_transform_calls) == 1
    op, args = adapter.sketch_geometry_transform_calls[0]
    assert op == "translate_sketch"
    assert args == ("Doc", "Sketch", SketchPoint2DInput(x=10.0, y=-5.0))


def test_rotate_sketch_success() -> None:
    handlers, adapter = _whole_handlers()
    result = handlers["rotate"].execute("Doc", "Sketch", {"x": 0.0, "y": 0.0}, 45.0)
    assert result.ok
    assert result.code == "sketch_rotated"
    assert len(adapter.sketch_geometry_transform_calls) == 1
    op, args = adapter.sketch_geometry_transform_calls[0]
    assert op == "rotate_sketch"
    assert args == ("Doc", "Sketch", SketchPoint2DInput(x=0.0, y=0.0), 45.0)


def test_scale_sketch_success() -> None:
    handlers, adapter = _whole_handlers()
    result = handlers["scale"].execute("Doc", "Sketch", {"x": 1.0, "y": 2.0}, 2.0)
    assert result.ok
    assert result.code == "sketch_scaled"
    assert len(adapter.sketch_geometry_transform_calls) == 1
    op, args = adapter.sketch_geometry_transform_calls[0]
    assert op == "scale_sketch"
    assert args == ("Doc", "Sketch", SketchPoint2DInput(x=1.0, y=2.0), 2.0)


def test_mirror_sketch_horizontal_axis_success() -> None:
    handlers, adapter = _whole_handlers()
    ref = {"kind": "horizontal_axis"}
    result = handlers["mirror"].execute("Doc", "Sketch", ref)
    assert result.ok
    assert result.code == "sketch_mirrored"
    assert len(adapter.sketch_geometry_transform_calls) == 1
    op, args = adapter.sketch_geometry_transform_calls[0]
    assert op == "mirror_sketch"
    assert args[0] == "Doc"
    assert args[1] == "Sketch"


def test_mirror_sketch_vertical_axis_success() -> None:
    handlers, _adapter = _whole_handlers()
    ref = {"kind": "vertical_axis"}
    result = handlers["mirror"].execute("Doc", "Sketch", ref)
    assert result.ok
    assert result.code == "sketch_mirrored"


def test_mirror_sketch_origin_success() -> None:
    handlers, _adapter = _whole_handlers()
    ref = {"kind": "origin"}
    result = handlers["mirror"].execute("Doc", "Sketch", ref)
    assert result.ok
    assert result.code == "sketch_mirrored"


# ---------------------------------------------------------------------------
# No geometry_indices accepted or forwarded
# ---------------------------------------------------------------------------


def test_whole_sketch_handlers_have_no_geometry_indices_parameter() -> None:
    """The whole-sketch handlers structurally accept no geometry_indices argument."""
    handlers, adapter = _whole_handlers()
    # Translate handler only takes 3 args (doc, sketch, displacement)
    result = handlers["translate"].execute("Doc", "Sketch", {"x": 5.0, "y": 0.0})
    assert result.ok
    assert adapter.sketch_geometry_transform_calls[0][0] == "translate_sketch"
    # geometry_indices ARE NOT forwarded to the adapter
    _op, args = adapter.sketch_geometry_transform_calls[0]
    assert len(args) == 3  # (doc, sketch, displacement) — no geometry_indices

    adapter.sketch_geometry_transform_calls.clear()
    # Rotate handler only takes 4 args (doc, sketch, center, angle)
    result = handlers["rotate"].execute("Doc", "Sketch", {"x": 0.0, "y": 0.0}, 90.0)
    assert result.ok
    _op, args = adapter.sketch_geometry_transform_calls[0]
    assert len(args) == 4  # (doc, sketch, center, angle) — no geometry_indices

    adapter.sketch_geometry_transform_calls.clear()
    # Mirror handler only takes 3 args (doc, sketch, reference)
    result = handlers["mirror"].execute("Doc", "Sketch", {"kind": "horizontal_axis"})
    assert result.ok
    _op, args = adapter.sketch_geometry_transform_calls[0]
    assert len(args) == 3  # (doc, sketch, reference) — no geometry_indices


def test_whole_sketch_scale_adapter_called_without_geometry_indices() -> None:
    handlers, adapter = _whole_handlers()
    result = handlers["scale"].execute("Doc", "Sketch", {"x": 1.0, "y": 1.0}, 2.0)
    assert result.ok
    _, args = adapter.sketch_geometry_transform_calls[0]
    # args: (doc, sketch, center, factor) — no geometry_indices
    assert len(args) == 4
    assert isinstance(args[2], SketchPoint2DInput)


# ---------------------------------------------------------------------------
# SketchGeometryTransformResult preserved via SketchWholeMirrorRequestInput
# ---------------------------------------------------------------------------


def test_translate_sketch_result_preserves_fields() -> None:
    handlers, _adapter = _whole_handlers()
    result = handlers["translate"].execute("Doc", "Sketch", {"x": 1.0, "y": 0.0})
    assert result.ok
    assert "changed" in result.data
    assert "operation" in result.data


def test_mirror_sketch_result_preserves_fields() -> None:
    handlers, _adapter = _whole_handlers()
    result = handlers["mirror"].execute("Doc", "Sketch", {"kind": "horizontal_axis"})
    assert result.ok
    assert "changed" in result.data
    assert "operation" in result.data


# ---------------------------------------------------------------------------
# Controlled errors
# ---------------------------------------------------------------------------


def test_whole_sketch_missing_document_name_fails() -> None:
    handlers, adapter = _whole_handlers()
    result = handlers["translate"].execute(None, "Sketch", {"x": 1.0, "y": 0.0})
    assert not result.ok
    assert result.code in ("validation_error", "document_not_found")
    assert adapter.sketch_geometry_transform_calls == []


def test_whole_sketch_missing_sketch_name_fails() -> None:
    handlers, adapter = _whole_handlers()
    result = handlers["translate"].execute("Doc", None, {"x": 1.0, "y": 0.0})
    assert not result.ok
    assert adapter.sketch_geometry_transform_calls == []


def test_whole_sketch_unsupported_mirror_reference_rejected_before_adapter() -> None:
    handlers, adapter = _whole_handlers()
    result = handlers["mirror"].execute(
        "Doc", "Sketch", {"kind": "construction_line", "geometry_index": 0}
    )
    assert not result.ok
    assert result.code == "validation_error"
    assert "unsupported_mirror_reference" in str(result.data.get("reason", ""))
    assert adapter.sketch_geometry_transform_calls == []


def test_whole_sketch_internal_point_mirror_reference_rejected() -> None:
    handlers, adapter = _whole_handlers()
    result = handlers["mirror"].execute(
        "Doc", "Sketch", {"kind": "internal_point", "geometry_index": 0}
    )
    assert not result.ok
    assert result.code == "validation_error"
    assert "unsupported_mirror_reference" in str(result.data.get("reason", ""))
    assert adapter.sketch_geometry_transform_calls == []


def test_whole_sketch_scale_with_zero_center_is_valid() -> None:
    handlers, _adapter = _whole_handlers()
    result = handlers["scale"].execute("Doc", "Sketch", {"x": 0.0, "y": 0.0}, 2.0)
    # zero center is fine for scale; this is a valid operation
    assert result.ok


def test_whole_sketch_translate_zero_vector_rejected() -> None:
    handlers, adapter = _whole_handlers()
    result = handlers["translate"].execute("Doc", "Sketch", {"x": 0.0, "y": 0.0})
    assert not result.ok
    assert result.code == "validation_error"
    assert result.data.get("reason") == "zero_displacement"
    assert adapter.sketch_geometry_transform_calls == []


def test_whole_sketch_rotate_zero_angle_rejected() -> None:
    handlers, adapter = _whole_handlers()
    result = handlers["rotate"].execute("Doc", "Sketch", {"x": 0.0, "y": 0.0}, 0.0)
    assert not result.ok
    assert result.code == "validation_error"
    assert adapter.sketch_geometry_transform_calls == []


def test_whole_sketch_scale_identity_factor_rejected() -> None:
    handlers, adapter = _whole_handlers()
    result = handlers["scale"].execute("Doc", "Sketch", {"x": 0.0, "y": 0.0}, 1.0)
    assert not result.ok
    assert result.code == "validation_error"
    assert result.data.get("reason") == "identity_scale"
    assert adapter.sketch_geometry_transform_calls == []


def test_whole_sketch_scale_negative_factor_rejected() -> None:
    handlers, adapter = _whole_handlers()
    result = handlers["scale"].execute("Doc", "Sketch", {"x": 0.0, "y": 0.0}, -1.0)
    assert not result.ok
    assert result.code == "validation_error"
    assert adapter.sketch_geometry_transform_calls == []


# ---------------------------------------------------------------------------
# Native / controlled error mapping via exception raising
# ---------------------------------------------------------------------------


class _ErrorRaisingAdapter:
    """Adapter stub that raises a controlled exception from the named method."""

    def __init__(self, method_name: str, exc: Exception) -> None:
        self.method_name = method_name
        self.exc = exc
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def translate_sketch(self, *args: object) -> object:
        self.calls.append(("translate_sketch", args))
        if self.method_name == "translate_sketch":
            raise self.exc
        return _dummy_result()

    def rotate_sketch(self, *args: object) -> object:
        self.calls.append(("rotate_sketch", args))
        if self.method_name == "rotate_sketch":
            raise self.exc
        return _dummy_result()

    def scale_sketch(self, *args: object) -> object:
        self.calls.append(("scale_sketch", args))
        if self.method_name == "scale_sketch":
            raise self.exc
        return _dummy_result()

    def mirror_sketch(self, *args: object) -> object:
        self.calls.append(("mirror_sketch", args))
        if self.method_name == "mirror_sketch":
            raise self.exc
        return _dummy_result()

    # Needed to satisfy the protocol stubs (unused in these tests)
    mirror_sketch_geometry = translate_sketch_geometry = rotate_sketch_geometry = (
        scale_sketch_geometry
    ) = lambda self, *a: None
    rectangular_array_sketch_geometry = polar_array_sketch_geometry = lambda self, *a: None


def _dummy_result() -> object:
    return _SemanticResultStub({"operation": "test", "changed": True, "mode": "copy"})


def _make_error_handler(method_name: str, exc: Exception) -> Any:
    adapter = _ErrorRaisingAdapter(method_name, exc)
    dispatcher = DispatcherStub()
    return {
        "translate": TranslateSketchHandler(adapter, dispatcher),  # type: ignore[arg-type]
        "rotate": RotateSketchHandler(adapter, dispatcher),  # type: ignore[arg-type]
        "scale": ScaleSketchHandler(adapter, dispatcher),  # type: ignore[arg-type]
        "mirror": MirrorSketchHandler(adapter, dispatcher),  # type: ignore[arg-type]
    }


def _exec_whole_handler(handlers: dict[str, Any], op: str) -> Any:
    if op == "translate_sketch":
        return handlers["translate"].execute("Doc", "Sketch", {"x": 10.0, "y": 0.0})
    if op == "rotate_sketch":
        return handlers["rotate"].execute("Doc", "Sketch", {"x": 0.0, "y": 0.0}, 45.0)
    if op == "scale_sketch":
        return handlers["scale"].execute("Doc", "Sketch", {"x": 0.0, "y": 0.0}, 2.0)
    if op == "mirror_sketch":
        return handlers["mirror"].execute("Doc", "Sketch", {"kind": "horizontal_axis"})
    raise ValueError(f"Unknown operation: {op}")


def test_native_sketch_transform_failed_mapped() -> None:
    handlers = _make_error_handler(
        "translate_sketch",
        SketchControlledMutationError(
            operation="translate_sketch", phase="execution", reason="test failure"
        ),
    )
    result = _exec_whole_handler(handlers, "translate_sketch")
    assert not result.ok
    assert result.code == "native_sketch_transform_failed"


def test_sketch_mutation_rollback_failed_mapped() -> None:
    handlers = _make_error_handler(
        "rotate_sketch",
        SketchControlledMutationRollbackError(operation="rotate_sketch", reason="rollback failure"),
    )
    result = _exec_whole_handler(handlers, "rotate_sketch")
    assert not result.ok
    assert result.code == "sketch_mutation_rollback_failed"


def test_document_not_found_mapped() -> None:
    handlers = _make_error_handler(
        "scale_sketch",
        DocumentNotFoundError("Doc"),
    )
    result = _exec_whole_handler(handlers, "scale_sketch")
    assert not result.ok
    assert result.code == "document_not_found"


def test_sketch_not_found_mapped() -> None:
    handlers = _make_error_handler(
        "mirror_sketch",
        ObjectNotFoundError("Doc", "Sketch"),
    )
    result = _exec_whole_handler(handlers, "mirror_sketch")
    assert not result.ok
    assert result.code == "sketch_not_found"


def test_sketch_type_mismatch_mapped() -> None:
    handlers = _make_error_handler(
        "translate_sketch",
        SketchTypeMismatchError("Doc", "Sketch"),
    )
    result = _exec_whole_handler(handlers, "translate_sketch")
    assert not result.ok
    assert result.code == "sketch_type_mismatch"


def test_unexpected_exception_mapped_to_internal_error() -> None:
    handlers = _make_error_handler("translate_sketch", RuntimeError("unexpected boom"))
    result = _exec_whole_handler(handlers, "translate_sketch")
    assert not result.ok
    assert result.code == "internal_error"


# ---------------------------------------------------------------------------
# transaction_committed preservation
# ---------------------------------------------------------------------------


class _TransactionCommittedResult:
    def __init__(self, committed: bool) -> None:
        self._committed = committed

    def to_dict(self) -> dict[str, object]:
        return {
            "operation": "test",
            "mode": "copy",
            "changed": True,
            "transaction_committed": self._committed,
        }


class _TransactionCommittedAdapter:
    def __init__(self, committed: bool) -> None:
        self._committed = committed
        self.calls: list[str] = []

    def translate_sketch(self, *args: object) -> object:
        self.calls.append("translate_sketch")
        return _TransactionCommittedResult(self._committed)

    def rotate_sketch(self, *args: object) -> object:
        self.calls.append("rotate_sketch")
        return _TransactionCommittedResult(self._committed)

    def scale_sketch(self, *args: object) -> object:
        self.calls.append("scale_sketch")
        return _TransactionCommittedResult(self._committed)

    def mirror_sketch(self, *args: object) -> object:
        self.calls.append("mirror_sketch")
        return _TransactionCommittedResult(self._committed)

    # Protocol stubs
    mirror_sketch_geometry = translate_sketch_geometry = rotate_sketch_geometry = (
        scale_sketch_geometry
    ) = lambda self, *a: None
    rectangular_array_sketch_geometry = polar_array_sketch_geometry = lambda self, *a: None


def test_transaction_committed_true_preserved() -> None:
    adapter = _TransactionCommittedAdapter(committed=True)
    dispatcher = DispatcherStub()
    handler = TranslateSketchHandler(adapter, dispatcher)  # type: ignore[arg-type]
    result = handler.execute("Doc", "Sketch", {"x": 10.0, "y": 0.0})
    assert result.ok
    assert result.data.get("transaction_committed") is True


def test_transaction_committed_false_preserved() -> None:
    adapter = _TransactionCommittedAdapter(committed=False)
    dispatcher = DispatcherStub()
    handler = TranslateSketchHandler(adapter, dispatcher)  # type: ignore[arg-type]
    result = handler.execute("Doc", "Sketch", {"x": 10.0, "y": 0.0})
    assert result.ok
    assert result.data.get("transaction_committed") is False


def test_command_handler_performs_no_transaction_commit_or_abort() -> None:
    """The handler only delegates to adapter; no commit/abort methods are called."""
    adapter = _TransactionCommittedAdapter(committed=False)
    dispatcher = DispatcherStub()
    handler = TranslateSketchHandler(adapter, dispatcher)  # type: ignore[arg-type]
    result = handler.execute("Doc", "Sketch", {"x": 10.0, "y": 0.0})
    assert result.ok
    # Adapter was called, but the handler itself has no commit/abort methods
    assert adapter.calls == ["translate_sketch"]


# ---------------------------------------------------------------------------
# Existing selected-geometry handlers remain unchanged
# ---------------------------------------------------------------------------


def test_existing_selected_geometry_handlers_still_functional() -> None:
    handlers, adapter = _handlers()
    result = handlers["translate"].execute("Doc", "Sketch", [0, 2], {"x": 1.0, "y": 0.0})
    assert result.ok
    assert result.code == "sketch_geometry_translated"
    assert len(adapter.sketch_geometry_transform_calls) == 1
    op, args = adapter.sketch_geometry_transform_calls[0]
    assert op == "translate"
    # geometry_indices ARE forwarded for selected-geometry handler
    assert args[2] == (0, 2)


# ---------------------------------------------------------------------------
# Milestone 28 — whole-sketch adapter stub delegation
# ---------------------------------------------------------------------------


def test_whole_sketch_translate_stub_delegates_without_geometry_indices() -> None:
    adapter = AdapterStub()
    result = adapter.translate_sketch("Doc", "Sketch", SketchPoint2DInput(x=10.0, y=0.0))
    assert result.to_dict()["operation"] == "translate_sketch"
    assert len(adapter.sketch_geometry_transform_calls) == 1
    op, args = adapter.sketch_geometry_transform_calls[0]
    assert op == "translate_sketch"
    # No geometry_indices in args
    assert args == ("Doc", "Sketch", SketchPoint2DInput(x=10.0, y=0.0))


def test_whole_sketch_rotate_stub_delegates_without_geometry_indices() -> None:
    adapter = AdapterStub()
    result = adapter.rotate_sketch("Doc", "Sketch", SketchPoint2DInput(x=0.0, y=0.0), 90.0)
    assert result.to_dict()["operation"] == "rotate_sketch"
    assert len(adapter.sketch_geometry_transform_calls) == 1
    op, args = adapter.sketch_geometry_transform_calls[0]
    assert op == "rotate_sketch"
    assert args == ("Doc", "Sketch", SketchPoint2DInput(x=0.0, y=0.0), 90.0)


def test_whole_sketch_scale_stub_delegates_without_geometry_indices() -> None:
    adapter = AdapterStub()
    result = adapter.scale_sketch("Doc", "Sketch", SketchPoint2DInput(x=1.0, y=2.0), 0.5)
    assert result.to_dict()["operation"] == "scale_sketch"
    assert len(adapter.sketch_geometry_transform_calls) == 1
    op, args = adapter.sketch_geometry_transform_calls[0]
    assert op == "scale_sketch"
    assert args == ("Doc", "Sketch", SketchPoint2DInput(x=1.0, y=2.0), 0.5)


def test_whole_sketch_mirror_stub_delegates_without_geometry_indices() -> None:
    adapter = AdapterStub()
    ref = SketchMirrorAxisReferenceInput(kind="horizontal_axis")
    result = adapter.mirror_sketch("Doc", "Sketch", ref)
    assert result.to_dict()["operation"] == "mirror_sketch"
    assert len(adapter.sketch_geometry_transform_calls) == 1
    op, args = adapter.sketch_geometry_transform_calls[0]
    assert op == "mirror_sketch"
    assert args == ("Doc", "Sketch", ref)


def test_existing_selected_geometry_adapter_behaviour_unchanged() -> None:
    """Existing mirror/translate/rotate/scale with geometry_indices still works."""
    adapter = AdapterStub()
    r1 = adapter.translate_sketch_geometry(
        "Doc", "Sketch", (0, 1), SketchPoint2DInput(x=5.0, y=0.0)
    )
    r2 = adapter.mirror_sketch_geometry(
        "Doc",
        "Sketch",
        (0,),
        SketchMirrorConstructionLineReferenceInput(kind="construction_line", geometry_index=1),
    )
    assert r1.to_dict()["operation"] == "translate"
    assert r2.to_dict()["operation"] == "mirror"
    ops = [call[0] for call in adapter.sketch_geometry_transform_calls]
    assert "translate" in ops
    assert "mirror" in ops


@pytest.mark.parametrize(
    "reference",
    [
        {"kind": "external_geometry", "geometry_index": 0},
        {"kind": "origin", "geometry_index": 0},
        {"kind": "construction_line", "geometry_index": True},
        {"kind": "internal_point", "geometry_index": -1},
        {"kind": "horizontal_axis", "extra": 1},
    ],
)
def test_mirror_reference_is_closed_and_discriminated(reference: object) -> None:
    handlers, adapter = _handlers()
    result = handlers["mirror"].execute("TestDocument", "BaseSketch", [0], reference)

    assert not result.ok
    assert result.code == "validation_error"
    assert adapter.sketch_geometry_transform_calls == []


@pytest.mark.parametrize("value", [math.inf, -math.inf, math.nan, True, "90"])
def test_angles_and_coordinates_reject_nonfinite_or_nonnumeric_values(value: object) -> None:
    handlers, adapter = _handlers()
    result = handlers["rotate"].execute(
        "TestDocument", "BaseSketch", [0], {"x": 0.0, "y": 0.0}, value
    )

    assert not result.ok
    assert result.code == "validation_error"
    assert adapter.sketch_geometry_transform_calls == []


@pytest.mark.parametrize("factor", [0.0, -1.0, 1e-7, math.inf, True, "2"])
def test_scale_factor_enforces_finite_controlled_positive_minimum(factor: object) -> None:
    handlers, adapter = _handlers()
    result = handlers["scale"].execute(
        "TestDocument", "BaseSketch", [0], {"x": 0.0, "y": 0.0}, factor
    )

    assert not result.ok
    assert result.code == "validation_error"
    assert adapter.sketch_geometry_transform_calls == []


@pytest.mark.parametrize(
    ("rows", "columns"),
    [(True, 2), (2.5, 2), (0, 2), (21, 1), (11, 10)],
)
def test_rectangular_array_enforces_axis_instance_and_generated_limits(
    rows: object,
    columns: object,
) -> None:
    handlers, adapter = _handlers()
    result = handlers["rectangular"].execute(
        "TestDocument",
        "BaseSketch",
        list(range(6)),
        rows,
        columns,
        {"x": 0.0, "y": 5.0},
        {"x": 8.0, "y": 0.0},
    )

    assert not result.ok
    assert result.code == "validation_error"
    assert adapter.sketch_geometry_transform_calls == []


@pytest.mark.parametrize("instance_count", [True, 1, 101, 2.5])
def test_polar_array_instance_count_is_strict_and_bounded(instance_count: object) -> None:
    handlers, adapter = _handlers()
    result = handlers["polar"].execute(
        "TestDocument",
        "BaseSketch",
        [0],
        {"x": 0.0, "y": 0.0},
        instance_count,
        30.0,
    )

    assert not result.ok
    assert result.code == "validation_error"
    assert adapter.sketch_geometry_transform_calls == []
