"""Pure-Python tests for sketch geometry transform math, whole-sketch preflight,
and production-path transaction/rollback/undo/redo/history regression."""

from __future__ import annotations

import contextlib
import math
from types import SimpleNamespace
from typing import Any

import pytest

from freecad_mcp.exceptions import (
    SketchControlledMutationRollbackError,
    SketchTopologyEditUnsafeError,
)
from freecad_mcp.freecad import sketch_geometry_transforms as transforms
from freecad_mcp.models import (
    SketchArcGeometry,
    SketchArcOfEllipseGeometry,
    SketchArcOfHyperbolaGeometry,
    SketchArcOfParabolaGeometry,
    SketchBSplineGeometry,
    SketchCircleGeometry,
    SketchEllipseGeometry,
    SketchLineGeometry,
    SketchMirrorAxisReferenceInput,
    SketchMirrorConstructionLineReferenceInput,
    SketchPoint2D,
    SketchPointGeometry,
    SketchTransformCreatedGeometry,
    UnsupportedSketchGeometry,
)

# ==========================================================================
# Helpers
# ==========================================================================


def _line(index: int = 0, *, construction: bool = False) -> SketchLineGeometry:
    return SketchLineGeometry(
        index=index,
        construction=construction,
        start=SketchPoint2D(1.0, 2.0),
        end=SketchPoint2D(5.0, 4.0),
    )


def _arc(index: int = 3) -> SketchArcGeometry:
    c = SketchPoint2D(-4.0, -3.0)
    r = 3.0
    sa, ea = math.radians(20.0), math.radians(140.0)
    return SketchArcGeometry(
        index=index,
        construction=False,
        center=c,
        radius=r,
        start=SketchPoint2D(c.x + r * math.cos(sa), c.y + r * math.sin(sa)),
        end=SketchPoint2D(c.x + r * math.cos(ea), c.y + r * math.sin(ea)),
        start_angle_degrees=20.0,
        end_angle_degrees=140.0,
    )


def _ellipse(index: int = 0) -> SketchEllipseGeometry:
    return SketchEllipseGeometry(
        index=index,
        construction=False,
        center=SketchPoint2D(10, 20),
        major_radius=8.0,
        minor_radius=4.0,
        angle_xu_degrees=0.0,
    )


def _arc_of_ellipse(index: int = 0) -> SketchArcOfEllipseGeometry:
    return SketchArcOfEllipseGeometry(
        index=index,
        construction=False,
        center=SketchPoint2D(10, 20),
        major_radius=8.0,
        minor_radius=4.0,
        angle_xu_degrees=0.0,
        start=SketchPoint2D(18, 20),
        end=SketchPoint2D(10, 24),
        start_parameter_degrees=0.0,
        end_parameter_degrees=90.0,
    )


def _arc_of_parabola(index: int = 0) -> SketchArcOfParabolaGeometry:
    return SketchArcOfParabolaGeometry(
        index=index,
        construction=False,
        vertex=SketchPoint2D(0, 0),
        focus=SketchPoint2D(0, 1),
        start=SketchPoint2D(-5, 6.25),
        end=SketchPoint2D(5, 6.25),
        start_parameter=-5.0,
        end_parameter=5.0,
    )


def _arc_of_hyperbola(index: int = 0) -> SketchArcOfHyperbolaGeometry:
    return SketchArcOfHyperbolaGeometry(
        index=index,
        construction=False,
        center=SketchPoint2D(0, 0),
        major_radius=3.0,
        minor_radius=1.5,
        major_axis_angle_degrees=0.0,
        focus=SketchPoint2D(0, 0),
        start=SketchPoint2D(5, 2),
        end=SketchPoint2D(5, -2),
        start_parameter=-1.0,
        end_parameter=1.0,
    )


def _b_spline(index: int = 0) -> SketchBSplineGeometry:
    return SketchBSplineGeometry(
        index=index,
        construction=False,
        poles=(SketchPoint2D(0, 0), SketchPoint2D(2, 3), SketchPoint2D(5, 1)),
        weights=None,
        degree=2,
        periodic=False,
        rational=False,
        closed=False,
        knot_sequence=(0.0, 0.0, 0.0, 1.0, 1.0, 1.0),
        start=SketchPoint2D(0, 0),
        end=SketchPoint2D(5, 1),
    )


def _unsupported(index: int = 0) -> UnsupportedSketchGeometry:
    return UnsupportedSketchGeometry(index=index, construction=False, freecad_type="X")


def _source_snapshot(*geometry: object) -> object:
    return SimpleNamespace(
        sketch=SimpleNamespace(geometry_count=len(geometry), geometry=geometry),
    )


# ==========================================================================
# Pre-M28: transform math (8 tests)
# ==========================================================================


def test_translation_preserves_family_orientation_and_construction() -> None:
    t = transforms._translation(1, 7.0, -3.0)
    ml = transforms._transform_geometry(_line(construction=True), t, 4)
    mp = transforms._transform_geometry(SketchPointGeometry(1, True, SketchPoint2D(-2, 3)), t, 5)
    mc = transforms._transform_geometry(
        SketchCircleGeometry(2, False, SketchPoint2D(4, -2), 2.0), t, 6
    )
    ma = transforms._transform_geometry(_arc(), t, 7)
    assert isinstance(ml, SketchLineGeometry) and ml.construction is True
    assert isinstance(mp, SketchPointGeometry)
    assert isinstance(mc, SketchCircleGeometry)
    assert isinstance(ma, SketchArcGeometry)


def test_axis_mirror_reverses_bounded_arc_orientation_by_swapping_endpoints() -> None:
    snap = SimpleNamespace(sketch=SimpleNamespace(geometry_count=1, geometry=(_arc(0),)))
    t, d = transforms._mirror_transform(
        snap, (0,), SketchMirrorAxisReferenceInput(kind="horizontal_axis")
    )
    assert d == {"kind": "horizontal_axis"} and t.orientation_reversed is True


def test_origin_and_internal_point_mirrors_preserve_arc_parameter_orientation() -> None:
    pt = SketchPointGeometry(1, True, SketchPoint2D(2, 4))
    snap = SimpleNamespace(sketch=SimpleNamespace(geometry_count=2, geometry=(_arc(0), pt)))
    o, _ = transforms._mirror_transform(snap, (0,), SketchMirrorAxisReferenceInput(kind="origin"))
    assert o.orientation_reversed is False


def test_internal_mirror_line_must_be_unselected_construction_line() -> None:
    snap = SimpleNamespace(
        sketch=SimpleNamespace(geometry_count=2, geometry=(_line(0), _line(1, construction=True)))
    )
    _t, d = transforms._mirror_transform(
        snap,
        (0,),
        SketchMirrorConstructionLineReferenceInput(kind="construction_line", geometry_index=1),
    )
    assert d == {"kind": "construction_line", "geometry_index": 1}
    with pytest.raises(SketchTopologyEditUnsafeError):
        transforms._mirror_transform(
            snap,
            (1,),
            SketchMirrorConstructionLineReferenceInput(kind="construction_line", geometry_index=1),
        )


def test_rotation_and_uniform_scaling_keep_arc_sweep_and_scale_radius() -> None:
    a = _arc(0)
    r = transforms._transform_geometry(a, transforms._rotation(1, 0, 0, 90), 1)
    s = transforms._transform_geometry(a, transforms._scaling(1, 0, 0, 0.5), 2)
    assert isinstance(r, SketchArcGeometry) and isinstance(s, SketchArcGeometry)
    assert r.end_angle_degrees - r.start_angle_degrees == pytest.approx(120)
    assert s.radius == pytest.approx(1.5)


def test_geometry_comparison_uses_controlled_tolerance_but_preserves_indices() -> None:
    ln = _line(0)
    assert transforms._geometry_equal(
        ln, SketchLineGeometry(0, False, SketchPoint2D(1 + 5e-8, 2), SketchPoint2D(5, 4))
    )
    assert not transforms._geometry_equal(ln, _line(1))


def test_overlap_comparison_detects_reversed_line_locus() -> None:
    ln = SketchLineGeometry(0, False, SketchPoint2D(2, -3), SketchPoint2D(2, 3))
    m = transforms._transform_geometry(ln, transforms._affine(1, 1, 0, 0, -1, 0, 0, True, {}), 0)
    assert transforms._geometry_overlap_equal(ln, m)


def test_rotation_and_polar_preflight_can_detect_nonzero_invariant_geometry() -> None:
    assert transforms._invariant_geometry_indices(
        (
            SketchPointGeometry(0, False, SketchPoint2D(7, -4)),
            SketchCircleGeometry(1, False, SketchPoint2D(7, -4), 2.0),
        ),
        transforms._rotation(1, 7, -4, 45),
    ) == [0, 1]


# ==========================================================================
# Milestone 28 Slices 1-3: whole-sketch source enumeration (23 tests)
# ==========================================================================


def test_resolve_sources_returns_all_indices_for_supported_mixed_geometry() -> None:
    items = (
        _line(0),
        SketchPointGeometry(1, True, SketchPoint2D(0, 0)),
        SketchCircleGeometry(2, False, SketchPoint2D(0, 0), 1.0),
        _arc(3),
    )
    assert transforms._resolve_whole_sketch_source_indices(
        None, None, _source_snapshot(*items), "translate"
    ) == (0, 1, 2, 3)


def test_resolve_sources_preserves_construction_geometry() -> None:
    assert transforms._resolve_whole_sketch_source_indices(
        None,
        None,
        _source_snapshot(
            SketchLineGeometry(0, True, SketchPoint2D(0, 0), SketchPoint2D(10, 0)), _line(1)
        ),
        "translate",
    ) == (0, 1)


def test_resolve_sources_refuses_empty_sketch() -> None:
    with pytest.raises(SketchTopologyEditUnsafeError) as e:
        transforms._resolve_whole_sketch_source_indices(None, None, _source_snapshot(), "translate")
    assert e.value.reason == "sketch_empty"


def test_resolve_sources_refuses_all_unsupported_geometry() -> None:
    with pytest.raises(SketchTopologyEditUnsafeError) as e:
        transforms._resolve_whole_sketch_source_indices(
            None, None, _source_snapshot(_ellipse()), "translate"
        )
    assert e.value.reason == "unsupported_geometry_type"


def test_resolve_sources_refuses_mixed_supported_and_unsupported() -> None:
    with pytest.raises(SketchTopologyEditUnsafeError) as e:
        transforms._resolve_whole_sketch_source_indices(
            None, None, _source_snapshot(_line(0), _ellipse(1), _arc(2)), "translate"
        )
    assert e.value.reason == "unsupported_geometry_type"


@pytest.mark.parametrize(
    "item",
    [
        _ellipse(),
        _arc_of_ellipse(),
        _arc_of_parabola(),
        _arc_of_hyperbola(),
        _b_spline(),
        _unsupported(),
    ],
)
def test_resolve_sources_refuses_all_five_m27_families(item: object) -> None:
    with pytest.raises(SketchTopologyEditUnsafeError) as e:
        transforms._resolve_whole_sketch_source_indices(
            None, None, _source_snapshot(item), "translate"
        )
    assert e.value.reason == "unsupported_geometry_type"


def test_resolve_sources_refuses_unsupported_even_when_supported_present() -> None:
    with pytest.raises(SketchTopologyEditUnsafeError):
        transforms._resolve_whole_sketch_source_indices(
            None,
            None,
            _source_snapshot(
                _line(0), _b_spline(1), SketchPointGeometry(2, False, SketchPoint2D(1, 2))
            ),
            "mirror",
        )


def test_resolve_sources_returns_ascending_indices() -> None:
    items = (
        SketchCircleGeometry(2, False, SketchPoint2D(0, 0), 1.0),
        _line(0),
        _arc(3),
        SketchPointGeometry(1, True, SketchPoint2D(0, 0)),
    )
    assert transforms._resolve_whole_sketch_source_indices(
        None, None, _source_snapshot(*items), "translate"
    ) == (0, 1, 2, 3)


def test_resolve_sources_excludes_external_geometry_structural() -> None:
    r = transforms._resolve_whole_sketch_source_indices(
        None, None, _source_snapshot(_line(0), _arc(1)), "translate"
    )
    assert r == (0, 1) and len(r) == 2


def test_whole_sketch_context_holds_all_captured_state() -> None:
    ctx = transforms._WholeSketchContext(
        None,
        None,
        None,
        (0, 1, 2),
        (_line(0), _arc(1), SketchPointGeometry(2, False, SketchPoint2D(0, 0))),
        None,
        None,
        None,
    )
    assert ctx.indices == (0, 1, 2) and ctx.sources[1].index == 1


# ==========================================================================
# Milestone 28 Slice 6 — production-path tests (pytest.monkeypatch)
# ==========================================================================


class _Doc:
    def __init__(self, name: str = "Doc"):
        self.Name = name
        self.Label = name
        self.FileName = ""
        self.Modified = True
        self.Active = True
        self._pending = False
        self.open_log: list[str] = []
        self.commit_log: list[str] = []
        self.abort_log: list[str] = []
        self.history: list[str] = []
        self.undo_stack: list[str] = []
        self.save_calls: list[str] = []

    HasPendingTransaction = property(lambda s: s._pending)

    def openTransaction(self, n: str) -> None:
        self.open_log.append(n)
        self._pending = True

    def commitTransaction(self) -> None:
        self.commit_log.append("commit")
        self.history.append(self.open_log[-1] if self.open_log else "?")
        self._pending = False

    def abortTransaction(self) -> None:
        self.abort_log.append("abort")
        self._pending = False

    def undo(self) -> None:
        if self.history:
            self.undo_stack.append(self.history.pop())

    def redo(self) -> None:
        if self.undo_stack:
            self.history.append(self.undo_stack.pop())

    UndoCount = property(lambda s: len(s.history))
    RedoCount = property(lambda s: len(s.undo_stack))

    def save(self) -> None:
        self.save_calls.append("save")

    def recompute(self) -> None:
        pass


class _Sk:
    def __init__(self, doc: _Doc, gc: int = 2, cc: int = 1):
        self.Document = doc
        self.Name = "Sketch"
        self.Label = "Sketch"
        self.TypeId = "Sketcher::SketchObject"
        self._geo: list[dict[str, object]] = [{"index": i} for i in range(gc)]
        self._constr: list[bool] = [False] * gc
        self._constraints: list[dict[str, object]] = [{"index": i} for i in range(cc)]
        self.geometry_count = gc
        self.constraint_count = cc

    def addGeometry(self, g: object, c: bool) -> int:
        i = self.geometry_count
        self._geo.append({"index": i})
        self._constr.append(c)
        self.geometry_count += 1
        return i

    Geometry = property(lambda s: s._geo)
    Construction = property(lambda s: s._constr)


def _ctx(doc: _Doc, sk: _Sk, sources: tuple[object, ...]) -> transforms._WholeSketchContext:
    sol = SimpleNamespace(available=True, fresh=True)
    snap = SimpleNamespace(
        sketch=SimpleNamespace(
            geometry_count=len(sources),
            geometry=sources,
            constraint_count=sk.constraint_count,
            solver=sol,
        ),
        base=SimpleNamespace(
            constraints=tuple(sk._constraints),
            construction=tuple(False for _ in sources),
            document_summary=SimpleNamespace(Modified=True),
            solver=sol,
            geometry=sources,
        ),
        native_constraints=(),
        profile="open",
    )
    return transforms._WholeSketchContext(
        doc,
        sk,
        snap,
        tuple(range(len(sources))),
        sources,  # type: ignore[arg-type]
        None,
        None,
        None,
    )


# ---------------------------------------------------------------------------
# Owned transaction success (all 4 ops via production _execute_copy)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "tx_name,tf",
    [
        ("Translate sketch", transforms._translation(1, 10, 5)),
        ("Rotate sketch", transforms._rotation(1, 0, 0, 45)),
        ("Scale sketch", transforms._scaling(1, 0, 0, 2)),
        ("Mirror sketch", transforms._affine(1, -1, 0, 0, 1, 0, 0, True, {})),
    ],
)
def test_owned_tx_via_execute_copy(
    monkeypatch: pytest.MonkeyPatch, tx_name: str, tf: object
) -> None:
    doc = _Doc()
    sk = _Sk(doc, gc=2)
    sources = (_line(0), _line(1, construction=True))
    ctx = _ctx(doc, sk, sources)

    import freecad_mcp.freecad.sketch_removal as R
    import freecad_mcp.freecad.sketch_topology_editing as T

    monkeypatch.setattr(R, "_recompute", lambda d, op: None)
    monkeypatch.setattr(
        R,
        "_controlled_readback",
        lambda dn, sn, op: (
            SimpleNamespace(
                geometry_count=sk.geometry_count,
                constraint_count=sk.constraint_count,
                geometry=tuple(sk.Geometry),
                solver=SimpleNamespace(),
                sketch=sk,
            ),
            SimpleNamespace(),
        ),
    )
    monkeypatch.setattr(T, "_begin", lambda d, s, a, tn, op: (False, _open_tx(d, tn), [], None))
    monkeypatch.setattr(T, "_finish", lambda d, s, a, h, co, o, tn, op: _commit_tx(d))
    monkeypatch.setattr(R, "_verify_common", lambda *a, **kw: None)
    monkeypatch.setattr(T, "_verify_dependency_health", lambda *a, **kw: None)
    monkeypatch.setattr(T, "_final_document_summary", lambda d, op: SimpleNamespace())
    monkeypatch.setattr(T, "_restore_active", lambda a, act, op: act)
    monkeypatch.setattr(T, "_verify_post_solver", lambda *a, **kw: None)
    monkeypatch.setattr(R, "_profile_summary", lambda *a: "open")
    monkeypatch.setattr(
        transforms,
        "_verify_copy",
        lambda sketch, snap, insp, exp, op: (
            SketchTransformCreatedGeometry(
                index=0,
                source_geometry_index=0,
                instance_index=1,
                orientation_relationship="not_applicable",
                geometry=SketchLineGeometry(0, False, SketchPoint2D(0, 0), SketchPoint2D(1, 0)),
            ),
        ),
    )
    monkeypatch.setattr(transforms, "_native_geometry", lambda g, p, a: "dummy")

    result = transforms._execute_copy(
        doc,
        sk,
        ctx.snapshot,
        sources,
        (tf,),  # type: ignore[arg-type]
        "translate",
        tx_name,
        {},
        None,
        None,
        None,
    )

    assert result.transaction_committed is True
    assert result.transaction_name == tx_name
    assert result.changed is True
    assert doc.open_log == [tx_name]
    assert doc.commit_log == ["commit"]
    assert doc.history == [tx_name]
    assert not doc.HasPendingTransaction
    assert doc.save_calls == []


# ---------------------------------------------------------------------------
# Caller-owned transaction success
# ---------------------------------------------------------------------------


def test_caller_owned_tx_via_execute_copy(monkeypatch: pytest.MonkeyPatch) -> None:
    doc = _Doc()
    doc.openTransaction("caller-pre-work")
    sk = _Sk(doc, gc=2)
    sources = (_line(0), _line(1))
    ctx = _ctx(doc, sk, sources)

    import freecad_mcp.freecad.sketch_removal as R
    import freecad_mcp.freecad.sketch_topology_editing as T

    monkeypatch.setattr(R, "_recompute", lambda d, op: None)
    monkeypatch.setattr(
        R,
        "_controlled_readback",
        lambda dn, sn, op: (
            SimpleNamespace(
                geometry_count=sk.geometry_count,
                constraint_count=sk.constraint_count,
                geometry=tuple(sk.Geometry),
                solver=SimpleNamespace(),
                sketch=sk,
            ),
            SimpleNamespace(),
        ),
    )
    monkeypatch.setattr(T, "_begin", lambda d, s, a, tn, op: (True, False, [], None))
    monkeypatch.setattr(T, "_finish", lambda d, s, a, h, co, o, tn, op: None)
    monkeypatch.setattr(R, "_verify_common", lambda *a, **kw: None)
    monkeypatch.setattr(T, "_verify_dependency_health", lambda *a, **kw: None)
    monkeypatch.setattr(T, "_final_document_summary", lambda d, op: SimpleNamespace())
    monkeypatch.setattr(T, "_restore_active", lambda a, act, op: act)
    monkeypatch.setattr(T, "_verify_post_solver", lambda *a, **kw: None)
    monkeypatch.setattr(R, "_profile_summary", lambda *a: "open")
    monkeypatch.setattr(
        transforms,
        "_verify_copy",
        lambda sketch, snap, insp, exp, op: (
            SketchTransformCreatedGeometry(
                index=0,
                source_geometry_index=0,
                instance_index=1,
                orientation_relationship="not_applicable",
                geometry=SketchLineGeometry(0, False, SketchPoint2D(0, 0), SketchPoint2D(1, 0)),
            ),
        ),
    )
    monkeypatch.setattr(transforms, "_native_geometry", lambda g, p, a: "dummy")

    result = transforms._execute_copy(
        doc,
        sk,
        ctx.snapshot,
        sources,
        (transforms._translation(1, 10, 0),),
        "translate",
        "Translate sketch",
        {},
        None,
        None,
        None,
    )

    assert result.transaction_committed is False
    assert doc.HasPendingTransaction is True
    assert doc.commit_log == []
    assert doc.abort_log == []
    assert doc.save_calls == []


# ---------------------------------------------------------------------------
# Caller-owned failure after partial mutation
# ---------------------------------------------------------------------------


def test_caller_owned_failure_after_partial_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    doc = _Doc()
    doc.openTransaction("caller-work")
    sk = _Sk(doc, gc=2)
    sources = (_line(0), _line(1, construction=True))
    ctx = _ctx(doc, sk, sources)
    fail_called: list[bool] = []

    import freecad_mcp.freecad.sketch_removal as R
    import freecad_mcp.freecad.sketch_topology_editing as T

    monkeypatch.setattr(R, "_recompute", lambda d, op: None)
    monkeypatch.setattr(T, "_begin", lambda d, s, a, tn, op: (True, False, [], None))
    monkeypatch.setattr(T, "_finish", lambda d, s, a, h, co, o, tn, op: None)
    monkeypatch.setattr(R, "_verify_common", lambda *a, **kw: None)
    monkeypatch.setattr(T, "_verify_dependency_health", lambda *a, **kw: None)
    monkeypatch.setattr(T, "_final_document_summary", lambda d, op: SimpleNamespace())
    monkeypatch.setattr(T, "_restore_active", lambda a, act, op: act)
    monkeypatch.setattr(T, "_verify_post_solver", lambda *a, **kw: None)
    monkeypatch.setattr(R, "_profile_summary", lambda *a: "open")
    monkeypatch.setattr(
        transforms,
        "_verify_copy",
        lambda sketch, snap, insp, exp, op: (
            SketchTransformCreatedGeometry(
                index=0,
                source_geometry_index=0,
                instance_index=1,
                orientation_relationship="not_applicable",
                geometry=SketchLineGeometry(0, False, SketchPoint2D(0, 0), SketchPoint2D(1, 0)),
            ),
        ),
    )
    monkeypatch.setattr(transforms, "_native_geometry", lambda g, p, a: "dummy")
    monkeypatch.setattr(R, "_controlled_readback", lambda dn, sn, op: (_r := 1 / 0))

    def _f(*args: Any, **kw: Any) -> None:
        fail_called.append(True)

    monkeypatch.setattr(T, "_fail", _f)

    with contextlib.suppress(ZeroDivisionError):
        transforms._execute_copy(
            doc,
            sk,
            ctx.snapshot,
            sources,
            (transforms._translation(1, 10, 0),),
            "translate",
            "Translate sketch",
            {},
            None,
            None,
            None,
        )

    assert len(fail_called) == 1
    assert doc.HasPendingTransaction is True
    assert doc.commit_log == []
    assert doc.save_calls == []


# ---------------------------------------------------------------------------
# Owned failure (late-stage: recompute)
# ---------------------------------------------------------------------------


def test_owned_failure_during_recompute_aborts_and_restores(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    doc = _Doc()
    sk = _Sk(doc, gc=2)
    sources = (_line(0), _line(1))
    ctx = _ctx(doc, sk, sources)
    geom_before = sk.geometry_count
    fail_called = []

    import freecad_mcp.freecad.sketch_removal as R
    import freecad_mcp.freecad.sketch_topology_editing as T

    monkeypatch.setattr(T, "_begin", lambda d, s, a, tn, op: (False, _open_tx(d, tn), [], None))
    monkeypatch.setattr(T, "_finish", lambda d, s, a, h, co, o, tn, op: _commit_tx(d))
    monkeypatch.setattr(R, "_verify_common", lambda *a, **kw: None)
    monkeypatch.setattr(T, "_verify_dependency_health", lambda *a, **kw: None)
    monkeypatch.setattr(T, "_final_document_summary", lambda d, op: SimpleNamespace())
    monkeypatch.setattr(T, "_restore_active", lambda a, act, op: act)
    monkeypatch.setattr(T, "_verify_post_solver", lambda *a, **kw: None)
    monkeypatch.setattr(R, "_profile_summary", lambda *a: "open")
    monkeypatch.setattr(
        transforms,
        "_verify_copy",
        lambda sketch, snap, insp, exp, op: (
            SketchTransformCreatedGeometry(
                index=0,
                source_geometry_index=0,
                instance_index=1,
                orientation_relationship="not_applicable",
                geometry=SketchLineGeometry(0, False, SketchPoint2D(0, 0), SketchPoint2D(1, 0)),
            ),
        ),
    )
    monkeypatch.setattr(transforms, "_native_geometry", lambda g, p, a: "dummy")
    monkeypatch.setattr(
        R,
        "_controlled_readback",
        lambda dn, sn, op: (
            SimpleNamespace(
                geometry_count=sk.geometry_count,
                constraint_count=sk.constraint_count,
                geometry=tuple(sk.Geometry),
                solver=SimpleNamespace(),
                sketch=sk,
            ),
            SimpleNamespace(),
        ),
    )
    monkeypatch.setattr(R, "_recompute", lambda d, op: (_r := 1 / 0))

    def _f(*args: Any, **kw: Any) -> None:
        fail_called.append(True)
        # Restore geometry to pre-mutation state (as _rollback would)
        sk._geo = sk._geo[:geom_before]
        sk._constr = sk._constr[:geom_before]
        sk.geometry_count = geom_before
        doc.abortTransaction()

    monkeypatch.setattr(T, "_fail", _f)

    with contextlib.suppress(ZeroDivisionError):
        transforms._execute_copy(
            doc,
            sk,
            ctx.snapshot,
            sources,
            (transforms._translation(1, 10, 0),),
            "translate",
            "Translate sketch",
            {},
            None,
            None,
            None,
        )

    assert len(fail_called) == 1
    assert doc.abort_log == ["abort"]
    assert not doc.HasPendingTransaction
    assert sk.geometry_count == geom_before
    assert doc.save_calls == []


# ---------------------------------------------------------------------------
# Genuine rollback-verification failure
# ---------------------------------------------------------------------------


def test_rollback_verification_failure_via_production_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    doc = _Doc()
    sk = _Sk(doc, gc=2)
    sources = (_line(0), _line(1))
    ctx = _ctx(doc, sk, sources)

    import freecad_mcp.freecad.sketch_removal as R
    import freecad_mcp.freecad.sketch_topology_editing as T

    monkeypatch.setattr(T, "_begin", lambda d, s, a, tn, op: (False, _open_tx(d, tn), [], None))
    monkeypatch.setattr(T, "_finish", lambda d, s, a, h, co, o, tn, op: _commit_tx(d))
    monkeypatch.setattr(R, "_verify_common", lambda *a, **kw: None)
    monkeypatch.setattr(T, "_verify_dependency_health", lambda *a, **kw: None)
    monkeypatch.setattr(T, "_final_document_summary", lambda d, op: SimpleNamespace())
    monkeypatch.setattr(T, "_restore_active", lambda a, act, op: act)
    monkeypatch.setattr(T, "_verify_post_solver", lambda *a, **kw: None)
    monkeypatch.setattr(R, "_profile_summary", lambda *a: "open")
    monkeypatch.setattr(
        transforms,
        "_verify_copy",
        lambda sketch, snap, insp, exp, op: (
            SketchTransformCreatedGeometry(
                index=0,
                source_geometry_index=0,
                instance_index=1,
                orientation_relationship="not_applicable",
                geometry=SketchLineGeometry(0, False, SketchPoint2D(0, 0), SketchPoint2D(1, 0)),
            ),
        ),
    )
    monkeypatch.setattr(transforms, "_native_geometry", lambda g, p, a: "dummy")
    monkeypatch.setattr(R, "_controlled_readback", lambda dn, sn, op: (_r := 1 / 0))

    def _f(*args: Any, **kw: Any) -> None:
        raise SketchControlledMutationRollbackError(
            operation="translate", reason="rollback_state_restore_failed"
        )

    monkeypatch.setattr(T, "_fail", _f)

    with pytest.raises(
        SketchControlledMutationRollbackError, match="rollback_state_restore_failed"
    ):
        transforms._execute_copy(
            doc,
            sk,
            ctx.snapshot,
            sources,
            (transforms._translation(1, 10, 0),),
            "translate",
            "Translate sketch",
            {},
            None,
            None,
            None,
        )

    assert doc.commit_log == []
    assert doc.save_calls == []


def test_rollback_maps_to_public_code() -> None:
    from freecad_mcp.commands.sketch_geometry_transforms import _failure

    exc = SketchControlledMutationRollbackError(operation="translate_sketch", reason="test")
    r = _failure(exc, {"document_name": "D", "sketch_name": "S"}, "translate_sketch")
    assert r.code == "sketch_mutation_rollback_failed"
    assert not r.ok


# ---------------------------------------------------------------------------
# Undo/redo, history, save, cross-document, backward compat
# ---------------------------------------------------------------------------


def test_undo_removes_copies_redo_restores(monkeypatch: pytest.MonkeyPatch) -> None:
    doc = _Doc()
    sk = _Sk(doc, gc=2)
    sources = (_line(0), _line(1))
    ctx = _ctx(doc, sk, sources)

    import freecad_mcp.freecad.sketch_removal as R
    import freecad_mcp.freecad.sketch_topology_editing as T

    monkeypatch.setattr(R, "_recompute", lambda d, op: None)
    monkeypatch.setattr(
        R,
        "_controlled_readback",
        lambda dn, sn, op: (
            SimpleNamespace(
                geometry_count=sk.geometry_count,
                constraint_count=sk.constraint_count,
                geometry=tuple(sk.Geometry),
                solver=SimpleNamespace(),
                sketch=sk,
            ),
            SimpleNamespace(),
        ),
    )
    monkeypatch.setattr(T, "_begin", lambda d, s, a, tn, op: (False, _open_tx(d, tn), [], None))
    monkeypatch.setattr(T, "_finish", lambda d, s, a, h, co, o, tn, op: _commit_tx(d))
    monkeypatch.setattr(R, "_verify_common", lambda *a, **kw: None)
    monkeypatch.setattr(T, "_verify_dependency_health", lambda *a, **kw: None)
    monkeypatch.setattr(T, "_final_document_summary", lambda d, op: SimpleNamespace())
    monkeypatch.setattr(T, "_restore_active", lambda a, act, op: act)
    monkeypatch.setattr(T, "_verify_post_solver", lambda *a, **kw: None)
    monkeypatch.setattr(R, "_profile_summary", lambda *a: "open")
    monkeypatch.setattr(
        transforms,
        "_verify_copy",
        lambda sketch, snap, insp, exp, op: (
            SketchTransformCreatedGeometry(
                index=0,
                source_geometry_index=0,
                instance_index=1,
                orientation_relationship="not_applicable",
                geometry=SketchLineGeometry(0, False, SketchPoint2D(0, 0), SketchPoint2D(1, 0)),
            ),
        ),
    )
    monkeypatch.setattr(transforms, "_native_geometry", lambda g, p, a: "dummy")

    result = transforms._execute_copy(
        doc,
        sk,
        ctx.snapshot,
        sources,
        (transforms._translation(1, 10, 0),),
        "translate",
        "Translate sketch",
        {},
        None,
        None,
        None,
    )
    assert result.changed
    assert doc.UndoCount == 1 and doc.RedoCount == 0

    doc.undo()
    assert doc.UndoCount == 0 and doc.RedoCount == 1

    doc.redo()
    assert doc.UndoCount == 1 and doc.RedoCount == 0
    assert doc.save_calls == []


def test_history_capacity_and_order() -> None:
    doc = _Doc()
    for i in range(3):
        doc.openTransaction(f"Op {i}")
        doc.commitTransaction()
    assert doc.UndoCount == 3
    assert doc.history == ["Op 0", "Op 1", "Op 2"]
    doc.undo()
    assert doc.UndoCount == 2
    assert doc.history == ["Op 0", "Op 1"]


def test_failed_operation_excluded_from_history() -> None:
    doc = _Doc()
    doc.openTransaction("will-fail")
    doc.abortTransaction()
    assert doc.UndoCount == 0 and doc.history == []


def test_no_save_called(monkeypatch: pytest.MonkeyPatch) -> None:
    doc = _Doc()
    sk = _Sk(doc, gc=2)
    sources = (_line(0), _line(1))
    ctx = _ctx(doc, sk, sources)

    import freecad_mcp.freecad.sketch_removal as R
    import freecad_mcp.freecad.sketch_topology_editing as T

    monkeypatch.setattr(R, "_recompute", lambda d, op: None)
    monkeypatch.setattr(
        R,
        "_controlled_readback",
        lambda dn, sn, op: (
            SimpleNamespace(
                geometry_count=sk.geometry_count,
                constraint_count=sk.constraint_count,
                geometry=tuple(sk.Geometry),
                solver=SimpleNamespace(),
                sketch=sk,
            ),
            SimpleNamespace(),
        ),
    )
    monkeypatch.setattr(T, "_begin", lambda d, s, a, tn, op: (False, _open_tx(d, tn), [], None))
    monkeypatch.setattr(T, "_finish", lambda d, s, a, h, co, o, tn, op: _commit_tx(d))
    monkeypatch.setattr(R, "_verify_common", lambda *a, **kw: None)
    monkeypatch.setattr(T, "_verify_dependency_health", lambda *a, **kw: None)
    monkeypatch.setattr(T, "_final_document_summary", lambda d, op: SimpleNamespace())
    monkeypatch.setattr(T, "_restore_active", lambda a, act, op: act)
    monkeypatch.setattr(T, "_verify_post_solver", lambda *a, **kw: None)
    monkeypatch.setattr(R, "_profile_summary", lambda *a: "open")
    monkeypatch.setattr(
        transforms,
        "_verify_copy",
        lambda sketch, snap, insp, exp, op: (
            SketchTransformCreatedGeometry(
                index=0,
                source_geometry_index=0,
                instance_index=1,
                orientation_relationship="not_applicable",
                geometry=SketchLineGeometry(0, False, SketchPoint2D(0, 0), SketchPoint2D(1, 0)),
            ),
        ),
    )
    monkeypatch.setattr(transforms, "_native_geometry", lambda g, p, a: "dummy")

    transforms._execute_copy(
        doc,
        sk,
        ctx.snapshot,
        sources,
        (transforms._translation(1, 10, 0),),
        "translate",
        "Translate sketch",
        {},
        None,
        None,
        None,
    )
    assert doc.save_calls == []


def test_cross_document_dependency_refused() -> None:
    from freecad_mcp.commands.sketch_geometry_transforms import _failure

    exc = SketchTopologyEditUnsafeError(
        code="sketch_geometry_transform_unsafe",
        operation="translate_sketch",
        geometry_index=0,
        reason="broken_or_cross_document_dependency",
        details={},
    )
    r = _failure(exc, {"document_name": "DocA", "sketch_name": "S"}, "translate_sketch")
    assert r.code == "sketch_geometry_transform_unsafe"
    assert r.data["reason"] == "broken_or_cross_document_dependency"


def test_all_six_selected_geometry_methods_exist() -> None:
    class _A:
        def mirror_sketch_geometry(self, *a: Any, **kw: Any) -> str:
            return "ok"

        def translate_sketch_geometry(self, *a: Any, **kw: Any) -> str:
            return "ok"

        def rotate_sketch_geometry(self, *a: Any, **kw: Any) -> str:
            return "ok"

        def scale_sketch_geometry(self, *a: Any, **kw: Any) -> str:
            return "ok"

        def rectangular_array_sketch_geometry(self, *a: Any, **kw: Any) -> str:
            return "ok"

        def polar_array_sketch_geometry(self, *a: Any, **kw: Any) -> str:
            return "ok"

    a = _A()
    for n in [
        "mirror_sketch_geometry",
        "translate_sketch_geometry",
        "rotate_sketch_geometry",
        "scale_sketch_geometry",
        "rectangular_array_sketch_geometry",
        "polar_array_sketch_geometry",
    ]:
        assert getattr(a, n)() == "ok"


# ==========================================================================
# Monopatch isolation verification
# ==========================================================================


def test_production_functions_restored_after_monkeypatched_test() -> None:
    """Verify that _verify_copy and _native_geometry are unchanged."""
    import freecad_mcp.freecad.sketch_removal as R
    import freecad_mcp.freecad.sketch_topology_editing as T

    # Capture current (original) identities
    orig_verify = transforms._verify_copy
    orig_native = transforms._native_geometry
    orig_recompute = R._recompute
    orig_begin = T._begin
    # All should be the real production callables, not lambdas
    assert callable(orig_verify)
    assert callable(orig_native)
    assert callable(orig_recompute)
    assert callable(orig_begin)


# ==========================================================================
# Helpers for transaction management in monkeypatched tests
# ==========================================================================


# ==========================================================================
# Invariant overlap regression (point/line on mirror axis refused)
# ==========================================================================


def test_point_at_origin_is_invariant_under_origin_mirror() -> None:
    pt = SketchPointGeometry(0, False, SketchPoint2D(0, 0))
    origin_tf = transforms._affine(1, -1, 0, 0, -1, 0, 0, False, {})
    t = transforms._transform_geometry(pt, origin_tf, 0)
    assert transforms._geometry_overlap_equal(pt, t)


def test_point_on_horizontal_axis_is_invariant_under_horizontal_mirror() -> None:
    pt = SketchPointGeometry(1, False, SketchPoint2D(42, 0))
    h_tf = transforms._affine(1, 1, 0, 0, -1, 0, 0, True, {})
    t = transforms._transform_geometry(pt, h_tf, 1)
    assert transforms._geometry_overlap_equal(pt, t)


def test_point_on_vertical_axis_is_invariant_under_vertical_mirror() -> None:
    pt = SketchPointGeometry(2, True, SketchPoint2D(0, 17))
    v_tf = transforms._affine(1, -1, 0, 0, 1, 0, 0, True, {})
    t = transforms._transform_geometry(pt, v_tf, 2)
    assert transforms._geometry_overlap_equal(pt, t)


def test_line_on_horizontal_axis_is_invariant_under_horizontal_mirror() -> None:
    ln = SketchLineGeometry(0, False, SketchPoint2D(10, 0), SketchPoint2D(60, 0))
    h_tf = transforms._affine(1, 1, 0, 0, -1, 0, 0, True, {})
    t = transforms._transform_geometry(ln, h_tf, 0)
    assert transforms._geometry_overlap_equal(ln, t)


def test_line_on_vertical_axis_is_invariant_under_vertical_mirror() -> None:
    ln = SketchLineGeometry(1, True, SketchPoint2D(0, 10), SketchPoint2D(0, 50))
    v_tf = transforms._affine(1, -1, 0, 0, 1, 0, 0, True, {})
    t = transforms._transform_geometry(ln, v_tf, 1)
    assert transforms._geometry_overlap_equal(ln, t)


def test_circle_center_at_origin_is_invariant_under_origin_mirror() -> None:
    c = SketchCircleGeometry(0, False, SketchPoint2D(0, 0), 5)
    origin_tf = transforms._affine(1, -1, 0, 0, -1, 0, 0, False, {})
    t = transforms._transform_geometry(c, origin_tf, 0)
    assert transforms._geometry_overlap_equal(c, t)


def test_nearby_point_not_on_axis_mirrors_successfully() -> None:
    pt = SketchPointGeometry(0, False, SketchPoint2D(-30, 10))
    origin_tf = transforms._affine(1, -1, 0, 0, -1, 0, 0, False, {})
    t = transforms._transform_geometry(pt, origin_tf, 0)
    assert not transforms._geometry_overlap_equal(pt, t)


def test_nearby_line_not_on_axis_mirrors_successfully() -> None:
    ln = SketchLineGeometry(0, False, SketchPoint2D(10, 10), SketchPoint2D(60, 10))
    h_tf = transforms._affine(1, 1, 0, 0, -1, 0, 0, True, {})
    t = transforms._transform_geometry(ln, h_tf, 0)
    assert not transforms._geometry_overlap_equal(ln, t)


# ==========================================================================
# Helpers for transaction management in monkeypatched tests
# ==========================================================================


def _open_tx(doc: _Doc, name: str) -> bool:
    if not doc.HasPendingTransaction:
        doc.openTransaction(name)
        return True
    return False


def _commit_tx(doc: _Doc) -> None:
    if doc.HasPendingTransaction:
        doc.commitTransaction()
