# Sketch DoF Diagnostics

## Native interface

The implementation uses the Python-visible
`Sketcher::SketchObject.getGeometryWithDependentParameters()` binding together
with the cached `DoF` and `FullyConstrained` properties. The binding returns
`(GeoId, PointPos)` pairs for internal geometry whose solver parameters remain
dependent. The public adapter deduplicates the non-negative current-state
`GeoId` values and adds only a compact geometry type.

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
    {"geometry_index": 0, "type": "line_segment"}
  ]
}
```

`geometry_index` is explicitly a current-state index, not persistent identity.
Repeated native entries for multiple dependent parameters on one element are
collapsed so the response remains small.

FreeCAD's internal solver also maintains parameter-to-geometry mappings,
dependent parameter sets, and dependency groups. Those structures are C++
solver details and are not exposed through the supported `SketchObject` Python
API. The tool therefore does not return coordinate labels, solver parameter
indices, dependency groups, or inferred motion names. It does not perturb
geometry to guess them.

## Version behavior

The native path is exercised against installed FreeCAD 1.1.3. In that release,
`SketchObject.cpp` incorrectly serializes dependent end and midpoint entries as
`PointPos::start`; current FreeCAD source corrects that mapping. Geometry IDs
remain valid, but point labels from the 1.1.3 binding are not reliable, so the
public tool intentionally ignores `PointPos` on every version. If a supported
runtime lacks the native method or returns inconsistent data, the adapter
returns a controlled inspection failure instead of reconstructing solver logic.

The call reads cached solver state only. It does not recompute the sketch, enter
edit mode, alter the active object/document, touch GUI selection, open a
transaction, consume history, mark the document dirty, or save.
