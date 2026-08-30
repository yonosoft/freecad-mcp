# Sketch DoF Diagnostics

## Native interface

The implementation uses the Python-visible
`Sketcher::SketchObject.getGeometryWithDependentParameters()` binding together
with the cached `DoF` and `FullyConstrained` properties. The binding returns
`(GeoId, PointPos)` pairs for internal geometry whose solver parameters remain
dependent. The public adapter groups the non-negative current-state `GeoId`
values, distinguishes native edge parameters (`PointPos::none`) from collapsed
point parameters, and adds a compact geometry type plus conservative motion
hints.

This is the same underlying `SolverGeometryExtension` information used by the
GUI command `Sketcher_SelectElementsWithDoFs`. The GUI command clears and
rewrites GUI selection and is edit-mode-only, so the MCP tool does not invoke
it. The direct Python call requires neither GUI mode nor Sketch edit mode and
does not change selection.

Authoritative source locations:

- [FreeCAD 1.1.3 SketchObject implementation](https://github.com/FreeCAD/FreeCAD/blob/1.1.3/src/Mod/Sketcher/App/SketchObject.cpp)
- [FreeCAD 1.1.3 Python binding](https://github.com/FreeCAD/FreeCAD/blob/1.1.3/src/Mod/Sketcher/App/SketchObjectPyImp.cpp)
- [FreeCAD 1.1.3 GUI selection command](https://github.com/FreeCAD/FreeCAD/blob/1.1.3/src/Mod/Sketcher/Gui/CommandSketcherTools.cpp)
- [Current FreeCAD solver implementation](https://github.com/FreeCAD/FreeCAD/blob/main/src/Mod/Sketcher/App/Sketch.cpp)

## Deliberate output boundary

`diagnose_sketch_dof` accepts exactly:

```json
{"document_name": "Doc", "sketch_name": "Sketch"}
```

Its controlled result adds:

```json
{
  "fully_constrained": false,
  "degrees_of_freedom": 1,
  "unconstrained_geometry": [
    {
      "geometry_index": 0,
      "type": "circle",
      "dependent_elements": ["edge_parameters"],
      "motion_hints": ["radius_change"]
    }
  ],
  "motion_analysis": {
    "detail_level": "coarse_native_elements",
    "coordinate_directions_available": false,
    "independent_motion_modes_available": false,
    "coupled_motion_groups_available": false,
    "point_position_detail": "collapsed",
    "limitations": [
      "coordinate_directions_unavailable",
      "independent_motion_modes_unavailable",
      "coupled_motion_groups_unavailable",
      "point_position_labels_collapsed_for_cross_version_safety"
    ]
  }
}
```

`geometry_index` is explicitly a current-state index, not persistent identity.
Repeated native entries are collapsed into `edge_parameters` and
`point_parameters`, because this binding reports geometry-element categories,
not one record per independent DoF.

The motion hints are deliberately geometry-safe rather than solver-mode claims:

- dependent point parameters on a line report `endpoint_movement`;
- dependent point parameters on a circle report `center_movement`;
- dependent edge parameters on a circle report `radius_change`;
- point geometry reports `point_movement`;
- circular arcs and other curves use conservative combined/generic movement or
  curve-parameter labels.

These labels describe what kind of geometry element remains movable. They do
not claim that each label is one independent mode or identify the X/Y direction
of that motion.

FreeCAD's internal solver also maintains parameter-to-geometry mappings,
dependent parameter sets, and dependency groups. Those structures are C++
solver details and are not exposed through the supported `SketchObject` Python
API. The public binding does not provide coordinate-specific free directions,
an independent translation/rotation decomposition, exact per-geometry parameter
counts, or coupled motion groups. The result states those limitations directly.
The tool does not perturb geometry or reconstruct the solver to guess them.

## Version behavior

The native path is exercised against installed FreeCAD 1.1.3. In that release,
`SketchObject.cpp` incorrectly serializes dependent end and midpoint entries as
`PointPos::start`. Geometry IDs and the edge-versus-point distinction remain
usable, but exact start/end/midpoint labels are not reliable. The public tool
therefore collapses positions 1, 2, and 3 to `point_parameters` on every version
for a stable cross-version contract. If a supported runtime lacks the native
method or returns inconsistent data, the adapter returns a controlled
inspection failure instead of reconstructing solver logic.

The permanent native smoke covers an unconstrained line, a horizontal
fixed-length line with free translation, a circle with free centre and radius,
a radius-only circle, a partially constrained rectangle whose four edges move
together, a point with one free coordinate, and a fully constrained rectangle.
Every diagnosis is compared against document, history, geometry, constraint,
and solver snapshots to prove read-only behavior. The coupled rectangle case
also locks the explicit `coupled_motion_groups_available: false` boundary.

The call reads cached solver state only. It does not recompute the sketch, enter
edit mode, alter the active object/document, touch GUI selection, open a
transaction, consume history, mark the document dirty, or save.
