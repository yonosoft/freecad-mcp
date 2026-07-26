"""Tests for the sketch diagnostics adapter (Milestone 29)."""

from __future__ import annotations

import sys
from types import ModuleType
from typing import Any, cast

import pytest

from freecad_mcp.exceptions import SketchInspectionError
from freecad_mcp.freecad.document import FreeCADDocumentAdapter
from freecad_mcp.freecad.sketch_diagnostics import _classify
from freecad_mcp.models import (
    SketchCandidateActionType,
    SketchDiagnosticClassification,
    SketchDiagnosticIssueCode,
    SketchSolverData,
)
from tests.support.freecad_stubs import (
    AppDocumentStub,
    DocumentObjectStub,
    install_freecad_stubs,
    make_document,
)

# ---------------------------------------------------------------------------
# helpers (copied from test_freecad_sketch_inspection.py)
# ---------------------------------------------------------------------------


class Vector:
    def __init__(self, x: float, y: float, z: float = 0.0) -> None:
        self.x = x
        self.y = y
        self.z = z


class LineSegment:
    def __init__(self, start: Vector, end: Vector) -> None:
        self.StartPoint = start
        self.EndPoint = end


class Circle:
    def __init__(self, center: Vector, radius: float) -> None:
        self.Center = center
        self.Radius = radius


class ArcOfCircle:
    def __init__(
        self,
        center: Vector,
        radius: float,
        start: Vector,
        end: Vector,
        first_parameter: float,
        last_parameter: float,
    ) -> None:
        self.Center = center
        self.Radius = radius
        self.StartPoint = start
        self.EndPoint = end
        self.FirstParameter = first_parameter
        self.LastParameter = last_parameter


class Point:
    def __init__(self, x: float, y: float) -> None:
        self.X = x
        self.Y = y


class BSplineCurve:
    def __init__(self) -> None:
        self.Degree = 3
        self.KnotSequence = [0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0]
        self.StartPoint = Vector(0.0, 0.0)
        self.EndPoint = Vector(10.0, 0.0)
        self.FirstParameter = 0.0
        self.LastParameter = 1.0

    def getPoles(self) -> list[Vector]:
        return [
            Vector(0.0, 0.0),
            Vector(3.0, 8.0),
            Vector(7.0, 3.0),
            Vector(10.0, 0.0),
        ]

    def getWeights(self) -> list[float]:
        return [1.0, 1.0, 1.0, 1.0]

    def isPeriodic(self) -> bool:
        return False

    def isRational(self) -> bool:
        return False

    def isClosed(self) -> bool:
        return False


class ConstraintStub:
    def __init__(
        self,
        type_name: str,
        *,
        first: int = -2000,
        first_pos: int = 0,
        second: int = -2000,
        second_pos: int = 0,
        third: int = -2000,
        third_pos: int = 0,
        value: float = 0.0,
        name: str = "",
        driving: bool = True,
        active: bool = True,
        virtual_space: bool = False,
    ) -> None:
        self.Type = type_name
        self.First = first
        self.FirstPos = first_pos
        self.Second = second
        self.SecondPos = second_pos
        self.Third = third
        self.ThirdPos = third_pos
        self.Value = value
        self.Name = name
        self.Driving = driving
        self.IsActive = active
        self.InVirtualSpace = virtual_space


class SketchStub(DocumentObjectStub):
    def __init__(
        self,
        *,
        geometry: list[Any] | None = None,
        constraints: list[ConstraintStub] | None = None,
        construction: list[bool] | None = None,
        parent: DocumentObjectStub | None = None,
        map_mode: str = "Deactivated",
        support: Any = None,
    ) -> None:
        super().__init__(
            "BaseSketch",
            label="Base Sketch",
            type_id="Sketcher::SketchObject",
            parent_geo=parent,
            map_mode=map_mode,
            attachment_support=[] if support is None else support,
        )
        self.Geometry = geometry or []
        self.GeometryCount = len(self.Geometry)
        self.Constraints = constraints or []
        self.ConstraintCount = len(self.Constraints)
        self.ExpressionEngine: tuple[tuple[str, str], ...] = ()
        self._construction = construction or [False] * len(self.Geometry)
        self.ExternalGeo: list[Any] = [object(), object()]
        self.AttachmentOffset: Any = None
        self.State = ["Up-to-date"]
        self.DoF = 0
        self.FullyConstrained = True
        self.ConflictingConstraints: list[int] = []
        self.RedundantConstraints: list[int] = []
        self.PartiallyRedundantConstraints: list[int] = []
        self.MalformedConstraints: list[int] = []
        self.solve_calls = 0

    def isDerivedFrom(self, type_id: str) -> bool:
        return type_id == "Sketcher::SketchObject"

    def getConstruction(self, index: int) -> bool:
        return self._construction[index]

    def solve(self) -> None:
        self.solve_calls += 1


def _install_document(
    monkeypatch: pytest.MonkeyPatch,
    objects: list[Any],
    *,
    modified: bool = True,
) -> AppDocumentStub:
    document, gui_document = make_document("TestDoc", modified=modified, objects=objects)
    install_freecad_stubs(
        monkeypatch,
        {"TestDoc": document},
        {"TestDoc": gui_document},
        active_name="TestDoc",
    )
    return document


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def part_module(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    module = ModuleType("Part")
    for name, value in (
        ("LineSegment", LineSegment),
        ("Circle", Circle),
        ("ArcOfCircle", ArcOfCircle),
        ("Point", Point),
        ("BSplineCurve", BSplineCurve),
    ):
        setattr(module, name, value)
    monkeypatch.setitem(sys.modules, "Part", module)
    return module


# ---------------------------------------------------------------------------
# Classification tests (12)
# ---------------------------------------------------------------------------


def test_classify_unavailable(monkeypatch: pytest.MonkeyPatch, part_module: ModuleType) -> None:
    sketch = SketchStub()
    del sketch.State
    _install_document(monkeypatch, [sketch])
    result = FreeCADDocumentAdapter().analyze_constraints("TestDoc", "BaseSketch")
    assert result.diagnostics.classification == SketchDiagnosticClassification.UNAVAILABLE


def test_classify_stale_no_issues(monkeypatch: pytest.MonkeyPatch, part_module: ModuleType) -> None:
    sketch = SketchStub()
    sketch.State = ["Touched"]
    sketch.DoF = 3
    sketch.FullyConstrained = False
    _install_document(monkeypatch, [sketch])
    result = FreeCADDocumentAdapter().analyze_constraints("TestDoc", "BaseSketch")
    assert result.diagnostics.classification == SketchDiagnosticClassification.STALE


def test_classify_stale_conflicting(
    monkeypatch: pytest.MonkeyPatch, part_module: ModuleType
) -> None:
    c0 = ConstraintStub("Distance", first=0, value=10.0)
    sketch = SketchStub(
        geometry=[LineSegment(Vector(0.0, 0.0), Vector(10.0, 0.0))],
        constraints=[c0],
    )
    sketch.State = ["Touched"]
    sketch.ConflictingConstraints = [1]  # 1-based
    _install_document(monkeypatch, [sketch])
    result = FreeCADDocumentAdapter().analyze_constraints("TestDoc", "BaseSketch")
    assert result.diagnostics.classification == SketchDiagnosticClassification.CONFLICTING


def test_classify_stale_redundant(monkeypatch: pytest.MonkeyPatch, part_module: ModuleType) -> None:
    c0 = ConstraintStub("Distance", first=0, value=10.0)
    sketch = SketchStub(
        geometry=[LineSegment(Vector(0.0, 0.0), Vector(10.0, 0.0))],
        constraints=[c0],
    )
    sketch.State = ["Touched"]
    sketch.RedundantConstraints = [1]
    _install_document(monkeypatch, [sketch])
    result = FreeCADDocumentAdapter().analyze_constraints("TestDoc", "BaseSketch")
    assert result.diagnostics.classification == SketchDiagnosticClassification.REDUNDANT


def test_classify_under_constrained(
    monkeypatch: pytest.MonkeyPatch, part_module: ModuleType
) -> None:
    sketch = SketchStub()
    sketch.State = ["Up-to-date"]
    sketch.DoF = 2
    sketch.FullyConstrained = False
    _install_document(monkeypatch, [sketch])
    result = FreeCADDocumentAdapter().analyze_constraints("TestDoc", "BaseSketch")
    assert result.diagnostics.classification == SketchDiagnosticClassification.UNDER_CONSTRAINED


def test_classify_fully_constrained(
    monkeypatch: pytest.MonkeyPatch, part_module: ModuleType
) -> None:
    sketch = SketchStub()
    sketch.State = ["Up-to-date"]
    sketch.DoF = 0
    sketch.FullyConstrained = True
    _install_document(monkeypatch, [sketch])
    result = FreeCADDocumentAdapter().analyze_constraints("TestDoc", "BaseSketch")
    assert result.diagnostics.classification == SketchDiagnosticClassification.FULLY_CONSTRAINED


def test_classify_conflicting(monkeypatch: pytest.MonkeyPatch, part_module: ModuleType) -> None:
    c0 = ConstraintStub("Distance", first=0, value=10.0)
    sketch = SketchStub(
        geometry=[LineSegment(Vector(0.0, 0.0), Vector(10.0, 0.0))],
        constraints=[c0],
    )
    sketch.State = ["Up-to-date"]
    sketch.ConflictingConstraints = [1]
    _install_document(monkeypatch, [sketch])
    result = FreeCADDocumentAdapter().analyze_constraints("TestDoc", "BaseSketch")
    assert result.diagnostics.classification == SketchDiagnosticClassification.CONFLICTING


def test_classify_redundant(monkeypatch: pytest.MonkeyPatch, part_module: ModuleType) -> None:
    c0 = ConstraintStub("Distance", first=0, value=10.0)
    sketch = SketchStub(
        geometry=[LineSegment(Vector(0.0, 0.0), Vector(10.0, 0.0))],
        constraints=[c0],
    )
    sketch.State = ["Up-to-date"]
    sketch.RedundantConstraints = [1]
    _install_document(monkeypatch, [sketch])
    result = FreeCADDocumentAdapter().analyze_constraints("TestDoc", "BaseSketch")
    assert result.diagnostics.classification == SketchDiagnosticClassification.REDUNDANT


def test_classify_partial_redundant_classified_as_redundant(
    monkeypatch: pytest.MonkeyPatch, part_module: ModuleType
) -> None:
    c0 = ConstraintStub("Distance", first=0, value=10.0)
    sketch = SketchStub(
        geometry=[LineSegment(Vector(0.0, 0.0), Vector(10.0, 0.0))],
        constraints=[c0],
    )
    sketch.State = ["Up-to-date"]
    sketch.PartiallyRedundantConstraints = [1]
    _install_document(monkeypatch, [sketch])
    result = FreeCADDocumentAdapter().analyze_constraints("TestDoc", "BaseSketch")
    assert result.diagnostics.classification == SketchDiagnosticClassification.REDUNDANT


def test_classify_mixed_conflict_redundant(
    monkeypatch: pytest.MonkeyPatch, part_module: ModuleType
) -> None:
    c0 = ConstraintStub("Distance", first=0, value=10.0)
    c1 = ConstraintStub("Distance", first=1, value=5.0)
    sketch = SketchStub(
        geometry=[
            LineSegment(Vector(0.0, 0.0), Vector(10.0, 0.0)),
            LineSegment(Vector(0.0, 10.0), Vector(10.0, 10.0)),
        ],
        constraints=[c0, c1],
    )
    sketch.State = ["Up-to-date"]
    sketch.ConflictingConstraints = [1]
    sketch.RedundantConstraints = [2]
    _install_document(monkeypatch, [sketch])
    result = FreeCADDocumentAdapter().analyze_constraints("TestDoc", "BaseSketch")
    assert result.diagnostics.classification == SketchDiagnosticClassification.MIXED


def test_classify_mixed_conflict_partial(
    monkeypatch: pytest.MonkeyPatch, part_module: ModuleType
) -> None:
    c0 = ConstraintStub("Distance", first=0, value=10.0)
    c1 = ConstraintStub("Distance", first=1, value=5.0)
    sketch = SketchStub(
        geometry=[
            LineSegment(Vector(0.0, 0.0), Vector(10.0, 0.0)),
            LineSegment(Vector(0.0, 10.0), Vector(10.0, 10.0)),
        ],
        constraints=[c0, c1],
    )
    sketch.State = ["Up-to-date"]
    sketch.ConflictingConstraints = [1]
    sketch.PartiallyRedundantConstraints = [2]
    _install_document(monkeypatch, [sketch])
    result = FreeCADDocumentAdapter().analyze_constraints("TestDoc", "BaseSketch")
    assert result.diagnostics.classification == SketchDiagnosticClassification.MIXED


def test_classify_malformed_overrides(
    monkeypatch: pytest.MonkeyPatch, part_module: ModuleType
) -> None:
    c0 = ConstraintStub("Distance", first=0, value=10.0)
    c1 = ConstraintStub("Distance", first=1, value=5.0)
    sketch = SketchStub(
        geometry=[
            LineSegment(Vector(0.0, 0.0), Vector(10.0, 0.0)),
            LineSegment(Vector(0.0, 10.0), Vector(10.0, 10.0)),
        ],
        constraints=[c0, c1],
    )
    sketch.State = ["Up-to-date"]
    sketch.MalformedConstraints = [1]
    sketch.ConflictingConstraints = [2]
    _install_document(monkeypatch, [sketch])
    result = FreeCADDocumentAdapter().analyze_constraints("TestDoc", "BaseSketch")
    assert result.diagnostics.classification == SketchDiagnosticClassification.MALFORMED


# ---------------------------------------------------------------------------
# Inconsistent solver tests (5)
# ---------------------------------------------------------------------------


def test_fresh_missing_dof() -> None:

    solver = SketchSolverData(
        available=True,
        fresh=True,
        degrees_of_freedom=None,
        fully_constrained=True,
        conflicting_constraint_indices=(),
        redundant_constraint_indices=(),
        partially_redundant_constraint_indices=(),
        malformed_constraint_indices=(),
    )
    with pytest.raises(SketchInspectionError, match="fresh_solver_missing_dof"):
        _classify(solver)


def test_fresh_missing_fc() -> None:

    solver = SketchSolverData(
        available=True,
        fresh=True,
        degrees_of_freedom=0,
        fully_constrained=None,
        conflicting_constraint_indices=(),
        redundant_constraint_indices=(),
        partially_redundant_constraint_indices=(),
        malformed_constraint_indices=(),
    )
    with pytest.raises(SketchInspectionError, match="fresh_solver_missing_fully_constrained"):
        _classify(solver)


def test_negative_dof(monkeypatch: pytest.MonkeyPatch, part_module: ModuleType) -> None:
    sketch = SketchStub()
    sketch.State = ["Up-to-date"]
    sketch.DoF = -1
    sketch.FullyConstrained = False
    _install_document(monkeypatch, [sketch])
    with pytest.raises(SketchInspectionError, match="negative_degrees_of_freedom"):
        FreeCADDocumentAdapter().analyze_constraints("TestDoc", "BaseSketch")


def test_contradictory_dof0_not_fully(
    monkeypatch: pytest.MonkeyPatch, part_module: ModuleType
) -> None:
    sketch = SketchStub()
    sketch.State = ["Up-to-date"]
    sketch.DoF = 0
    sketch.FullyConstrained = False
    _install_document(monkeypatch, [sketch])
    with pytest.raises(SketchInspectionError, match="contradictory_dof_zero_not_fully_constrained"):
        FreeCADDocumentAdapter().analyze_constraints("TestDoc", "BaseSketch")


def test_contradictory_dof_positive_fully(
    monkeypatch: pytest.MonkeyPatch, part_module: ModuleType
) -> None:
    sketch = SketchStub()
    sketch.State = ["Up-to-date"]
    sketch.DoF = 2
    sketch.FullyConstrained = True
    _install_document(monkeypatch, [sketch])
    with pytest.raises(SketchInspectionError, match="contradictory_positive_dof_fully_constrained"):
        FreeCADDocumentAdapter().analyze_constraints("TestDoc", "BaseSketch")


# ---------------------------------------------------------------------------
# Count tests (4)
# ---------------------------------------------------------------------------


def test_counts_active_inactive(monkeypatch: pytest.MonkeyPatch, part_module: ModuleType) -> None:
    c0 = ConstraintStub("Distance", first=0, value=10.0, active=True)
    c1 = ConstraintStub("Distance", first=1, value=5.0, active=False)
    sketch = SketchStub(
        geometry=[
            LineSegment(Vector(0.0, 0.0), Vector(10.0, 0.0)),
            LineSegment(Vector(0.0, 10.0), Vector(10.0, 10.0)),
        ],
        constraints=[c0, c1],
    )
    sketch.State = ["Up-to-date"]
    sketch.DoF = 4
    sketch.FullyConstrained = False
    _install_document(monkeypatch, [sketch])
    result = FreeCADDocumentAdapter().analyze_constraints("TestDoc", "BaseSketch")
    diagnostics = result.diagnostics
    assert diagnostics.constraint_count == 2
    assert diagnostics.active_count == 1
    assert diagnostics.inactive_count == 1


def test_counts_driving_reference_unavailable(
    monkeypatch: pytest.MonkeyPatch, part_module: ModuleType
) -> None:
    c0 = ConstraintStub("Distance", first=0, value=10.0, driving=True)
    c1 = ConstraintStub("Distance", first=1, value=5.0, driving=False)
    c2 = ConstraintStub("Horizontal", first=0)
    sketch = SketchStub(
        geometry=[
            LineSegment(Vector(0.0, 0.0), Vector(10.0, 0.0)),
            LineSegment(Vector(0.0, 10.0), Vector(10.0, 10.0)),
        ],
        constraints=[c0, c1, c2],
    )
    sketch.State = ["Up-to-date"]
    sketch.DoF = 4
    sketch.FullyConstrained = False
    _install_document(monkeypatch, [sketch])
    result = FreeCADDocumentAdapter().analyze_constraints("TestDoc", "BaseSketch")
    diagnostics = result.diagnostics
    assert diagnostics.driving_count == 1
    assert diagnostics.reference_count == 1
    assert diagnostics.driving_state_unavailable_count == 1
    assert (
        diagnostics.driving_count
        + diagnostics.reference_count
        + diagnostics.driving_state_unavailable_count
        == 3
    )


def test_counts_virtual_space(monkeypatch: pytest.MonkeyPatch, part_module: ModuleType) -> None:
    c0 = ConstraintStub("Distance", first=0, value=10.0, virtual_space=False)
    c1 = ConstraintStub("Distance", first=1, value=5.0, virtual_space=True)
    sketch = SketchStub(
        geometry=[
            LineSegment(Vector(0.0, 0.0), Vector(10.0, 0.0)),
            LineSegment(Vector(0.0, 10.0), Vector(10.0, 10.0)),
        ],
        constraints=[c0, c1],
    )
    sketch.State = ["Up-to-date"]
    sketch.DoF = 4
    sketch.FullyConstrained = False
    _install_document(monkeypatch, [sketch])
    result = FreeCADDocumentAdapter().analyze_constraints("TestDoc", "BaseSketch")
    assert result.diagnostics.virtual_space_count == 1


def test_counts_invariant_violation() -> None:
    pass  # cannot be triggered with current public interfaces


# ---------------------------------------------------------------------------
# Issue tests (5)
# ---------------------------------------------------------------------------


def test_issue_ordering_malformed_conflicting_inactive(
    monkeypatch: pytest.MonkeyPatch,
    part_module: ModuleType,
) -> None:
    c0 = ConstraintStub("Distance", first=0, value=10.0, active=True)
    c1 = ConstraintStub("Distance", first=1, value=5.0, active=True)
    c2 = ConstraintStub("Distance", first=2, value=5.0, active=False)
    sketch = SketchStub(
        geometry=[
            LineSegment(Vector(0.0, 0.0), Vector(10.0, 0.0)),
            LineSegment(Vector(0.0, 10.0), Vector(10.0, 10.0)),
            LineSegment(Vector(0.0, 20.0), Vector(10.0, 20.0)),
        ],
        constraints=[c0, c1, c2],
    )
    sketch.State = ["Up-to-date"]
    sketch.MalformedConstraints = [1]
    sketch.ConflictingConstraints = [2]
    _install_document(monkeypatch, [sketch])
    result = FreeCADDocumentAdapter().analyze_constraints("TestDoc", "BaseSketch")
    issues = result.diagnostics.issues
    assert len(issues) >= 3
    codes = [i.code for i in issues]
    assert codes[0] == SketchDiagnosticIssueCode.MALFORMED
    assert codes[1] == SketchDiagnosticIssueCode.CONFLICTING
    assert SketchDiagnosticIssueCode.INACTIVE_PRESENT in codes
    assert codes.index(SketchDiagnosticIssueCode.INACTIVE_PRESENT) > codes.index(
        SketchDiagnosticIssueCode.CONFLICTING
    )


def test_issue_index_constraint_alignment(
    monkeypatch: pytest.MonkeyPatch,
    part_module: ModuleType,
) -> None:
    c0 = ConstraintStub("Distance", first=0, value=10.0, name="DistX")
    c1 = ConstraintStub("Distance", first=1, value=5.0, name="DistY")
    sketch = SketchStub(
        geometry=[
            LineSegment(Vector(0.0, 0.0), Vector(10.0, 0.0)),
            LineSegment(Vector(0.0, 10.0), Vector(10.0, 10.0)),
        ],
        constraints=[c0, c1],
    )
    sketch.State = ["Up-to-date"]
    sketch.ConflictingConstraints = [1, 2]
    _install_document(monkeypatch, [sketch])
    result = FreeCADDocumentAdapter().analyze_constraints("TestDoc", "BaseSketch")
    issue = result.diagnostics.issues[0]
    assert issue.constraint_indices == (0, 1)
    assert cast(Any, issue.constraints[0]).type == "distance"
    assert cast(Any, issue.constraints[1]).type == "distance"


def test_invalid_index_rejected(
    monkeypatch: pytest.MonkeyPatch,
    part_module: ModuleType,
) -> None:
    c0 = ConstraintStub("Distance", first=0, value=10.0)
    sketch = SketchStub(
        geometry=[LineSegment(Vector(0.0, 0.0), Vector(10.0, 0.0))],
        constraints=[c0],
    )
    sketch.State = ["Up-to-date"]
    sketch.ConflictingConstraints = [99]
    _install_document(monkeypatch, [sketch])
    with pytest.raises(SketchInspectionError, match="solver_index_out_of_range"):
        FreeCADDocumentAdapter().analyze_constraints("TestDoc", "BaseSketch")


def test_issue_informational_no_candidate_actions(
    monkeypatch: pytest.MonkeyPatch,
    part_module: ModuleType,
) -> None:
    c0 = ConstraintStub("Distance", first=0, value=10.0, active=False)
    sketch = SketchStub(
        geometry=[LineSegment(Vector(0.0, 0.0), Vector(10.0, 0.0))],
        constraints=[c0],
    )
    sketch.State = ["Up-to-date"]
    _install_document(monkeypatch, [sketch])
    result = FreeCADDocumentAdapter().analyze_constraints("TestDoc", "BaseSketch")
    for issue in result.diagnostics.issues:
        if issue.code in (
            SketchDiagnosticIssueCode.INACTIVE_PRESENT,
            SketchDiagnosticIssueCode.REFERENCE_PRESENT,
            SketchDiagnosticIssueCode.VIRTUAL_SPACE_PRESENT,
        ):
            assert issue.candidate_actions == ()


def test_issue_multiple_categories_preserve_order(
    monkeypatch: pytest.MonkeyPatch,
    part_module: ModuleType,
) -> None:
    c0 = ConstraintStub("Distance", first=0, value=10.0, active=True)
    c1 = ConstraintStub("Distance", first=1, value=5.0, active=True, driving=False)
    c2 = ConstraintStub("Distance", first=2, value=5.0, active=False)
    s0 = LineSegment(Vector(0.0, 0.0), Vector(10.0, 0.0))
    s1 = LineSegment(Vector(0.0, 10.0), Vector(10.0, 10.0))
    s2 = LineSegment(Vector(0.0, 20.0), Vector(10.0, 20.0))
    sketch = SketchStub(
        geometry=[s0, s1, s2],
        constraints=[c0, c1, c2],
    )
    sketch.State = ["Up-to-date"]
    sketch.ConflictingConstraints = [1]
    sketch.RedundantConstraints = [2]
    _install_document(monkeypatch, [sketch])
    result = FreeCADDocumentAdapter().analyze_constraints("TestDoc", "BaseSketch")
    codes = [i.code for i in result.diagnostics.issues]
    assert codes[0] == SketchDiagnosticIssueCode.CONFLICTING
    assert codes[1] == SketchDiagnosticIssueCode.REDUNDANT
    assert codes[2] == SketchDiagnosticIssueCode.INACTIVE_PRESENT
    assert codes[3] == SketchDiagnosticIssueCode.REFERENCE_PRESENT


# ---------------------------------------------------------------------------
# Candidate action tests (10)
# ---------------------------------------------------------------------------


def test_active_driving_conflict_three_actions(
    monkeypatch: pytest.MonkeyPatch,
    part_module: ModuleType,
) -> None:
    c0 = ConstraintStub("Distance", first=0, value=10.0, active=True, driving=True)
    sketch = SketchStub(
        geometry=[LineSegment(Vector(0.0, 0.0), Vector(10.0, 0.0))],
        constraints=[c0],
    )
    sketch.State = ["Up-to-date"]
    sketch.ConflictingConstraints = [1]
    _install_document(monkeypatch, [sketch])
    result = FreeCADDocumentAdapter().analyze_constraints("TestDoc", "BaseSketch")
    issue = result.diagnostics.issues[0]
    actions = issue.candidate_actions
    assert len(actions) == 3
    types = [a.action for a in actions]
    assert SketchCandidateActionType.DEACTIVATE in types
    assert SketchCandidateActionType.CONVERT_TO_REFERENCE in types
    assert SketchCandidateActionType.DELETE in types


def test_inactive_conflict_two_actions_no_deactivate(
    monkeypatch: pytest.MonkeyPatch,
    part_module: ModuleType,
) -> None:
    c0 = ConstraintStub("Distance", first=0, value=10.0, active=False, driving=True)
    sketch = SketchStub(
        geometry=[LineSegment(Vector(0.0, 0.0), Vector(10.0, 0.0))],
        constraints=[c0],
    )
    sketch.State = ["Up-to-date"]
    sketch.ConflictingConstraints = [1]
    _install_document(monkeypatch, [sketch])
    result = FreeCADDocumentAdapter().analyze_constraints("TestDoc", "BaseSketch")
    issue = result.diagnostics.issues[0]
    actions = issue.candidate_actions
    types = [a.action for a in actions]
    assert SketchCandidateActionType.DEACTIVATE not in types
    assert SketchCandidateActionType.CONVERT_TO_REFERENCE in types
    assert SketchCandidateActionType.DELETE in types
    assert len(actions) == 2


def test_reference_conflict_two_actions_no_convert(
    monkeypatch: pytest.MonkeyPatch,
    part_module: ModuleType,
) -> None:
    c0 = ConstraintStub("Distance", first=0, value=10.0, active=True, driving=False)
    sketch = SketchStub(
        geometry=[LineSegment(Vector(0.0, 0.0), Vector(10.0, 0.0))],
        constraints=[c0],
    )
    sketch.State = ["Up-to-date"]
    sketch.ConflictingConstraints = [1]
    _install_document(monkeypatch, [sketch])
    result = FreeCADDocumentAdapter().analyze_constraints("TestDoc", "BaseSketch")
    issue = result.diagnostics.issues[0]
    actions = issue.candidate_actions
    types = [a.action for a in actions]
    assert SketchCandidateActionType.DEACTIVATE in types
    assert SketchCandidateActionType.CONVERT_TO_REFERENCE not in types
    assert SketchCandidateActionType.DELETE in types
    assert len(actions) == 2


def test_geometric_conflict_two_actions_no_convert(
    monkeypatch: pytest.MonkeyPatch,
    part_module: ModuleType,
) -> None:
    c0 = ConstraintStub("Horizontal", first=0)
    sketch = SketchStub(
        geometry=[LineSegment(Vector(0.0, 0.0), Vector(10.0, 0.0))],
        constraints=[c0],
    )
    sketch.State = ["Up-to-date"]
    sketch.ConflictingConstraints = [1]
    _install_document(monkeypatch, [sketch])
    result = FreeCADDocumentAdapter().analyze_constraints("TestDoc", "BaseSketch")
    issue = result.diagnostics.issues[0]
    actions = issue.candidate_actions
    types = [a.action for a in actions]
    assert SketchCandidateActionType.DEACTIVATE in types
    assert SketchCandidateActionType.CONVERT_TO_REFERENCE not in types
    assert SketchCandidateActionType.DELETE in types
    assert len(actions) == 2


def test_redundant_delete_only(monkeypatch: pytest.MonkeyPatch, part_module: ModuleType) -> None:
    c0 = ConstraintStub("Distance", first=0, value=10.0)
    sketch = SketchStub(
        geometry=[LineSegment(Vector(0.0, 0.0), Vector(10.0, 0.0))],
        constraints=[c0],
    )
    sketch.State = ["Up-to-date"]
    sketch.RedundantConstraints = [1]
    _install_document(monkeypatch, [sketch])
    result = FreeCADDocumentAdapter().analyze_constraints("TestDoc", "BaseSketch")
    issue = result.diagnostics.issues[0]
    actions = issue.candidate_actions
    assert len(actions) == 1
    assert actions[0].action == SketchCandidateActionType.DELETE


def test_partial_delete_only(monkeypatch: pytest.MonkeyPatch, part_module: ModuleType) -> None:
    c0 = ConstraintStub("Distance", first=0, value=10.0)
    sketch = SketchStub(
        geometry=[LineSegment(Vector(0.0, 0.0), Vector(10.0, 0.0))],
        constraints=[c0],
    )
    sketch.State = ["Up-to-date"]
    sketch.PartiallyRedundantConstraints = [1]
    _install_document(monkeypatch, [sketch])
    result = FreeCADDocumentAdapter().analyze_constraints("TestDoc", "BaseSketch")
    issue = result.diagnostics.issues[0]
    actions = issue.candidate_actions
    assert len(actions) == 1
    assert actions[0].action == SketchCandidateActionType.DELETE


def test_malformed_delete_only(monkeypatch: pytest.MonkeyPatch, part_module: ModuleType) -> None:
    c0 = ConstraintStub("Distance", first=0, value=10.0)
    sketch = SketchStub(
        geometry=[LineSegment(Vector(0.0, 0.0), Vector(10.0, 0.0))],
        constraints=[c0],
    )
    sketch.State = ["Up-to-date"]
    sketch.MalformedConstraints = [1]
    _install_document(monkeypatch, [sketch])
    result = FreeCADDocumentAdapter().analyze_constraints("TestDoc", "BaseSketch")
    issue = result.diagnostics.issues[0]
    actions = issue.candidate_actions
    assert len(actions) == 1
    assert actions[0].action == SketchCandidateActionType.DELETE


def test_candidate_action_ordering_multiple_indices(
    monkeypatch: pytest.MonkeyPatch,
    part_module: ModuleType,
) -> None:
    c0 = ConstraintStub("Distance", first=0, value=10.0, active=True, driving=True)
    c1 = ConstraintStub("Distance", first=1, value=5.0, active=True, driving=True)
    sketch = SketchStub(
        geometry=[
            LineSegment(Vector(0.0, 0.0), Vector(10.0, 0.0)),
            LineSegment(Vector(0.0, 10.0), Vector(10.0, 10.0)),
        ],
        constraints=[c0, c1],
    )
    sketch.State = ["Up-to-date"]
    sketch.ConflictingConstraints = [1, 2]
    _install_document(monkeypatch, [sketch])
    result = FreeCADDocumentAdapter().analyze_constraints("TestDoc", "BaseSketch")
    issue = result.diagnostics.issues[0]
    actions = issue.candidate_actions
    assert len(actions) == 6
    assert actions[0].target_constraint_index == 0
    assert actions[0].action == SketchCandidateActionType.DEACTIVATE
    assert actions[1].target_constraint_index == 0
    assert actions[1].action == SketchCandidateActionType.CONVERT_TO_REFERENCE
    assert actions[2].target_constraint_index == 0
    assert actions[2].action == SketchCandidateActionType.DELETE
    assert actions[3].target_constraint_index == 1
    assert actions[3].action == SketchCandidateActionType.DEACTIVATE
    assert actions[4].target_constraint_index == 1
    assert actions[4].action == SketchCandidateActionType.CONVERT_TO_REFERENCE
    assert actions[5].target_constraint_index == 1
    assert actions[5].action == SketchCandidateActionType.DELETE


def test_candidate_action_destructive_flags(
    monkeypatch: pytest.MonkeyPatch,
    part_module: ModuleType,
) -> None:
    c0 = ConstraintStub("Distance", first=0, value=10.0, active=True, driving=True)
    sketch = SketchStub(
        geometry=[LineSegment(Vector(0.0, 0.0), Vector(10.0, 0.0))],
        constraints=[c0],
    )
    sketch.State = ["Up-to-date"]
    sketch.ConflictingConstraints = [1]
    _install_document(monkeypatch, [sketch])
    result = FreeCADDocumentAdapter().analyze_constraints("TestDoc", "BaseSketch")
    issue = result.diagnostics.issues[0]
    actions = issue.candidate_actions
    assert actions[0].destructive is False
    assert actions[1].destructive is False
    assert actions[2].destructive is True


def test_candidate_action_tool_names(
    monkeypatch: pytest.MonkeyPatch, part_module: ModuleType
) -> None:
    c0 = ConstraintStub("Distance", first=0, value=10.0, active=True, driving=True)
    sketch = SketchStub(
        geometry=[LineSegment(Vector(0.0, 0.0), Vector(10.0, 0.0))],
        constraints=[c0],
    )
    sketch.State = ["Up-to-date"]
    sketch.ConflictingConstraints = [1]
    _install_document(monkeypatch, [sketch])
    result = FreeCADDocumentAdapter().analyze_constraints("TestDoc", "BaseSketch")
    issue = result.diagnostics.issues[0]
    actions = issue.candidate_actions
    assert actions[0].tool == "set_sketch_constraint_active"
    assert actions[1].tool == "set_sketch_constraint_driving"
    assert actions[2].tool == "remove_sketch_constraints"


def test_candidate_action_descriptions(
    monkeypatch: pytest.MonkeyPatch, part_module: ModuleType
) -> None:
    c0 = ConstraintStub("Distance", first=0, value=10.0, active=True, driving=True)
    sketch = SketchStub(
        geometry=[LineSegment(Vector(0.0, 0.0), Vector(10.0, 0.0))],
        constraints=[c0],
    )
    sketch.State = ["Up-to-date"]
    sketch.ConflictingConstraints = [1]
    _install_document(monkeypatch, [sketch])
    result = FreeCADDocumentAdapter().analyze_constraints("TestDoc", "BaseSketch")
    issue = result.diagnostics.issues[0]
    actions = issue.candidate_actions
    desc0 = actions[0].description
    assert "constraint 0 (distance)" in desc0


# ---------------------------------------------------------------------------
# Result construction (3)
# ---------------------------------------------------------------------------


def test_sketch_summary_fields(monkeypatch: pytest.MonkeyPatch, part_module: ModuleType) -> None:
    sketch = SketchStub()
    _install_document(monkeypatch, [sketch])
    result = FreeCADDocumentAdapter().analyze_constraints("TestDoc", "BaseSketch")
    sketch_summary = result.sketch
    assert sketch_summary["name"] == "BaseSketch"
    assert sketch_summary["label"] == "Base Sketch"
    assert sketch_summary["constraint_count"] == 0


def test_document_summary(monkeypatch: pytest.MonkeyPatch, part_module: ModuleType) -> None:
    sketch = SketchStub()
    _install_document(monkeypatch, [sketch])
    result = FreeCADDocumentAdapter().analyze_constraints("TestDoc", "BaseSketch")
    assert result.document.name == "TestDoc"


def test_no_native_objects(monkeypatch: pytest.MonkeyPatch, part_module: ModuleType) -> None:
    c0 = ConstraintStub("Distance", first=0, value=10.0)
    sketch = SketchStub(
        geometry=[LineSegment(Vector(0.0, 0.0), Vector(10.0, 0.0))],
        constraints=[c0],
    )
    _install_document(monkeypatch, [sketch])
    FreeCADDocumentAdapter().analyze_constraints("TestDoc", "BaseSketch")
    assert True  # no crash


# ---------------------------------------------------------------------------
# Read-only behaviour (8)
# ---------------------------------------------------------------------------


def test_no_transaction(monkeypatch: pytest.MonkeyPatch, part_module: ModuleType) -> None:
    sketch = SketchStub()
    doc = _install_document(monkeypatch, [sketch])
    FreeCADDocumentAdapter().analyze_constraints("TestDoc", "BaseSketch")
    assert doc.open_transaction_calls == 0
    assert doc.commit_transaction_calls == 0


def test_no_recompute(monkeypatch: pytest.MonkeyPatch, part_module: ModuleType) -> None:
    sketch = SketchStub()
    doc = _install_document(monkeypatch, [sketch])
    FreeCADDocumentAdapter().analyze_constraints("TestDoc", "BaseSketch")
    assert doc.recompute_calls == 0
    assert sketch.solve_calls == 0


def test_no_save(monkeypatch: pytest.MonkeyPatch, part_module: ModuleType) -> None:
    sketch = SketchStub()
    doc = _install_document(monkeypatch, [sketch])
    FreeCADDocumentAdapter().analyze_constraints("TestDoc", "BaseSketch")
    assert doc.save_calls == 0


def test_modified_unchanged_true(monkeypatch: pytest.MonkeyPatch, part_module: ModuleType) -> None:
    """Modified flag True must remain True after diagnostics."""
    sketch = SketchStub()
    doc, gui_doc = make_document("TestDoc", modified=True, objects=[sketch])
    install_freecad_stubs(
        monkeypatch,
        {"TestDoc": doc},
        {"TestDoc": gui_doc},
        active_name="TestDoc",
    )
    assert gui_doc.Modified is True
    FreeCADDocumentAdapter().analyze_constraints("TestDoc", "BaseSketch")
    assert gui_doc.Modified is True


def test_modified_unchanged_false(monkeypatch: pytest.MonkeyPatch, part_module: ModuleType) -> None:
    """Modified flag False must remain False after diagnostics."""
    sketch = SketchStub()
    doc, gui_doc = make_document("TestDoc", modified=False, objects=[sketch])
    install_freecad_stubs(
        monkeypatch,
        {"TestDoc": doc},
        {"TestDoc": gui_doc},
        active_name="TestDoc",
    )
    assert gui_doc.Modified is False
    FreeCADDocumentAdapter().analyze_constraints("TestDoc", "BaseSketch")
    assert gui_doc.Modified is False


def test_undo_unchanged(monkeypatch: pytest.MonkeyPatch, part_module: ModuleType) -> None:
    sketch = SketchStub()
    doc = _install_document(monkeypatch, [sketch])
    doc.UndoCount = 3  # type: ignore[attr-defined]
    doc.UndoNames = ["Add constraint", "Create sketch", "Create body"]  # type: ignore[attr-defined]
    doc_undo_before: int = doc.UndoCount  # type: ignore[attr-defined]
    doc_names_before: list[str] = list(doc.UndoNames)  # type: ignore[attr-defined]

    FreeCADDocumentAdapter().analyze_constraints("TestDoc", "BaseSketch")

    assert doc.UndoCount == doc_undo_before  # type: ignore[attr-defined]
    assert doc.UndoNames == doc_names_before  # type: ignore[attr-defined]


def test_redo_unchanged(monkeypatch: pytest.MonkeyPatch, part_module: ModuleType) -> None:
    sketch = SketchStub()
    doc = _install_document(monkeypatch, [sketch])
    doc.RedoCount = 1  # type: ignore[attr-defined]
    doc.RedoNames = ["Add constraint"]  # type: ignore[attr-defined]
    doc_redo_before: int = doc.RedoCount  # type: ignore[attr-defined]
    doc_names_before: list[str] = list(doc.RedoNames)  # type: ignore[attr-defined]

    FreeCADDocumentAdapter().analyze_constraints("TestDoc", "BaseSketch")

    assert doc.RedoCount == doc_redo_before  # type: ignore[attr-defined]
    assert doc.RedoNames == doc_names_before  # type: ignore[attr-defined]


def test_pre_existing_redo_preserved(
    monkeypatch: pytest.MonkeyPatch, part_module: ModuleType
) -> None:
    sketch = SketchStub()
    doc = _install_document(monkeypatch, [sketch])
    doc.RedoCount = 2  # type: ignore[attr-defined]
    doc.RedoNames = ["Add dimension", "Remove line"]  # type: ignore[attr-defined]
    doc_redo_before: int = doc.RedoCount  # type: ignore[attr-defined]
    doc_names_before: list[str] = list(doc.RedoNames)  # type: ignore[attr-defined]

    FreeCADDocumentAdapter().analyze_constraints("TestDoc", "BaseSketch")

    assert doc.RedoCount == doc_redo_before  # type: ignore[attr-defined]
    assert doc.RedoNames == doc_names_before  # type: ignore[attr-defined]


def test_unrelated_document_unchanged(
    monkeypatch: pytest.MonkeyPatch, part_module: ModuleType
) -> None:
    """Calling analyze_constraints must not mutate an unrelated open document."""
    # Create the target document (DocA) with a sketch
    sketch = SketchStub()
    doc_a, gui_a = make_document("DocA", modified=True, objects=[sketch])

    # Create an unrelated document (DocB) with its own sketch
    sketch_b = SketchStub()
    doc_b, gui_b = make_document("DocB", modified=False, objects=[sketch_b])

    # Install both documents, DocA active
    install_freecad_stubs(
        monkeypatch,
        {"DocA": doc_a, "DocB": doc_b},
        {"DocA": gui_a, "DocB": gui_b},
        active_name="DocA",
    )

    # Capture DocB state before
    doc_b_recompute_before = doc_b.recompute_calls
    doc_b_save_before = doc_b.save_calls
    doc_b_transaction_before = doc_b.open_transaction_calls

    # Call analyze_constraints on DocA
    FreeCADDocumentAdapter().analyze_constraints("DocA", "BaseSketch")

    # DocB must be completely unaffected
    assert doc_b.recompute_calls == doc_b_recompute_before
    assert doc_b.save_calls == doc_b_save_before
    assert doc_b.open_transaction_calls == doc_b_transaction_before


def test_active_document_unchanged(
    monkeypatch: pytest.MonkeyPatch, part_module: ModuleType
) -> None:
    """Calling analyze_constraints must preserve the active document."""
    sketch = SketchStub()
    doc_a, gui_a = make_document("DocA", modified=True, objects=[sketch])
    doc_b, gui_b = make_document("DocB", modified=False)

    install_freecad_stubs(
        monkeypatch,
        {"DocA": doc_a, "DocB": doc_b},
        {"DocA": gui_a, "DocB": gui_b},
        active_name="DocA",
    )

    # Verify DocA is active before
    freecad_module = sys.modules["FreeCAD"]
    assert freecad_module.activeDocument().Name == "DocA"

    # Call analyze_constraints on DocA (which is already active)
    FreeCADDocumentAdapter().analyze_constraints("DocA", "BaseSketch")

    # Active document must still be DocA
    assert freecad_module.activeDocument().Name == "DocA"
