"""Native FreeCAD smoke for compact read-only sketch DoF diagnostics."""

from __future__ import annotations

import json
import uuid
from typing import Any

import FreeCAD as App  # type: ignore[import-not-found]
import Part  # type: ignore[import-not-found]
import Sketcher  # type: ignore[import-not-found]

from freecad_mcp.freecad.document import FreeCADDocumentAdapter


def _add_rectangle(sketch: Any) -> None:
    segments = (
        (App.Vector(1, 2), App.Vector(11, 2)),
        (App.Vector(11, 2), App.Vector(11, 7)),
        (App.Vector(11, 7), App.Vector(1, 7)),
        (App.Vector(1, 7), App.Vector(1, 2)),
    )
    sketch.addGeometry([Part.LineSegment(start, end) for start, end in segments], False)
    sketch.addConstraint(
        [
            Sketcher.Constraint("Horizontal", 0),
            Sketcher.Constraint("Vertical", 1),
            Sketcher.Constraint("Horizontal", 2),
            Sketcher.Constraint("Vertical", 3),
            Sketcher.Constraint("Coincident", 0, 2, 1, 1),
            Sketcher.Constraint("Coincident", 1, 2, 2, 1),
            Sketcher.Constraint("Coincident", 2, 2, 3, 1),
            Sketcher.Constraint("Coincident", 3, 2, 0, 1),
            Sketcher.Constraint("Distance", 0, 10.0),
            Sketcher.Constraint("Distance", 1, 5.0),
            Sketcher.Constraint("DistanceY", 0, 1, 2.0),
        ]
    )


def _snapshot(document: Any, sketch: Any) -> tuple[object, ...]:
    active = getattr(App.ActiveDocument, "Name", None)
    return (
        bool(document.isTouched()),
        int(document.UndoCount),
        int(document.RedoCount),
        active,
        tuple(str(item) for item in sketch.State),
        tuple(str(item) for item in sketch.Geometry),
        tuple(str(item) for item in sketch.Constraints),
        int(sketch.DoF),
        bool(sketch.FullyConstrained),
    )


def _diagnose_read_only(document: Any, sketch: Any) -> dict[str, object]:
    before = _snapshot(document, sketch)
    result = FreeCADDocumentAdapter().diagnose_sketch_dof(document.Name, sketch.Name)
    after = _snapshot(document, sketch)
    assert after == before
    return result.to_dict()


def main() -> None:
    document = App.newDocument(f"MCPDoFDiagnosticSmoke_{uuid.uuid4().hex[:8]}")
    try:
        window = document.addObject("Sketcher::SketchObject", "Window")
        _add_rectangle(window)

        fully = document.addObject("Sketcher::SketchObject", "FullyConstrainedWindow")
        _add_rectangle(fully)
        fully.addConstraint(Sketcher.Constraint("DistanceX", 0, 1, 1.0))

        circle = document.addObject("Sketcher::SketchObject", "FreeRadiusCircle")
        circle.addGeometry(Part.Circle(App.Vector(4, 6), App.Vector(0, 0, 1), 3), False)
        circle.addConstraint(Sketcher.Constraint("DistanceX", 0, 3, 4.0))
        circle.addConstraint(Sketcher.Constraint("DistanceY", 0, 3, 6.0))

        point = document.addObject("Sketcher::SketchObject", "FreeYPoint")
        point.addGeometry(Part.Point(App.Vector(4, 6)), False)
        point.addConstraint(Sketcher.Constraint("DistanceX", 0, 1, 4.0))

        document.recompute()
        results = {
            sketch.Name: _diagnose_read_only(document, sketch)
            for sketch in (window, fully, circle, point)
        }

        assert results["Window"]["degrees_of_freedom"] == 1
        assert results["Window"]["unconstrained_geometry"] == [
            {"geometry_index": index, "type": "line_segment"} for index in range(4)
        ]
        assert results["FullyConstrainedWindow"]["degrees_of_freedom"] == 0
        assert results["FullyConstrainedWindow"]["fully_constrained"] is True
        assert results["FullyConstrainedWindow"]["unconstrained_geometry"] == []
        assert results["FreeRadiusCircle"]["degrees_of_freedom"] == 1
        assert results["FreeRadiusCircle"]["unconstrained_geometry"] == [
            {"geometry_index": 0, "type": "circle"}
        ]
        assert results["FreeYPoint"]["degrees_of_freedom"] == 1
        assert results["FreeYPoint"]["unconstrained_geometry"] == [
            {"geometry_index": 0, "type": "point"}
        ]

        print(json.dumps({"status": "PASS", "results": results}, indent=2))
    finally:
        App.closeDocument(document.Name)


if __name__ == "__main__":
    main()
