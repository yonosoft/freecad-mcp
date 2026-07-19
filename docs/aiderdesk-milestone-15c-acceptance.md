# AiderDesk Milestone 15C Live Acceptance

Use this prompt in a fresh AiderDesk session connected to the running FreeCAD
MCP endpoint. This is an acceptance campaign only: do not edit, stage, commit,
push, clean, or otherwise modify the repository. Keep disposable FreeCAD
documents clearly named and report every raw tool request and response.

```text
Validate FreeCAD MCP Milestone 15C through the live MCP endpoint. Do not edit
the repository and do not invoke arbitrary Python or Sketcher GUI commands.
Use structured MCP inspection as the primary evidence. Capture Report View only
as supporting evidence.

1. Record FreeCAD version/revision, MCP connection details, repository branch,
   HEAD and status. Run raw tools/list. Require exactly these 19 tools in order:
   create_document, list_documents, get_document, save_document, list_objects,
   get_object, recompute_document, create_body, create_sketch, get_sketch,
   add_sketch_geometry, add_sketch_constraints, get_document_history,
   undo_document, redo_document, create_sketch_rectangle,
   create_sketch_centered_rectangle, create_sketch_equilateral_triangle,
   create_sketch_regular_polygon.

2. Retain raw schemas. Prove the first 17 schemas are unchanged and
   add_sketch_constraints still has exactly 17 discriminated variants. Prove
   both new top-level schemas and center objects forbid extra properties.
   Triangle must require document_name, sketch_name, circumradius, center and
   default first_vertex_angle_degrees to 90. Polygon must additionally require
   strict integer side_count 3 through 64 and default its angle to 0.

3. Create an unsaved standalone sketch and issue exactly one
   create_sketch_equilateral_triangle call for an origin-centred 20 mm
   circumradius triangle using the default angle. Recompute and inspect. Require
   three normal edges in counter-clockwise vertex order, then a construction
   centre point and construction circumcircle; first vertex approximately
   (0,20), then (-17.320508,-10), then (17.320508,-10). Require equal sides,
   exact radius, closed/regular/counter_clockwise/fully_constrained true, zero
   DoF, clean diagnostics, no hidden helper, path still null, and exactly one
   Create sketch equilateral triangle history step.

4. In isolated sketches test triangle centre (12,-7), circumradius 15, angle
   30; then -30 and 390 degrees. Verify conceptual coordinates and normalized
   readback 330 and 30. Verify deterministic edge/vertex/reference mappings.

5. Through create_sketch_regular_polygon create isolated profiles for: n=3;
   n=4,r=20,centre=(0,0),angle=45 (axis-aligned square); n=5,r=20,angle=90;
   n=6,r=20,centre=(10,-5),angle=0; n=12; and n=64. Recompute and inspect each.
   Require N normal edges, two explicit construction references, N ordered
   vertices, edge i vertex i→i+1 with final closure, equal sides, exact
   circumradius, positive counter-clockwise area, normalized angle, zero DoF,
   clean diagnostics, and constraint count 3N+3 at origin or 3N+4 elsewhere.

6. Test all centre branches: (0,0), (0,9), (8,0), and (8,-6). Retain
   controlled placement-constraint readback. Confirm centre coordinates and
   both reference geometry states. Test negative and wrapped angles.

7. Reject without mutation: radius zero/negative/boolean/NaN/infinity; missing
   centre; missing or boolean centre coordinate; boolean/non-finite angle;
   triangle side_count and other extra fields; polygon side_count 2, 65, true,
   3.0, and missing required fields. Compare geometry, constraints, history,
   file path, and object inventory before/after. Do not call undo after a failed
   atomic request.

8. Add unrelated normal and construction geometry plus a controlled constraint
   to a sketch. Append a triangle, then a polygon in separate runs. Prove all
   earlier geometry, coordinates, construction flags, constraints and indices
   are unchanged and returned indices start after existing content.

9. Repeat representative triangle and polygon creation in a Body-owned sketch
   and an XY-plane-attached sketch. Across creation, exact-name undo, recompute,
   exact-name redo and recompute, prove sketch identity, Body ownership,
   support, MapMode, attachment offset and placement remain unchanged. Require
   reference construction state restoration and no duplicate sketch.

10. Prove one triangle and one polygon each add one distinct history step.
    First send undo with a deliberately wrong expected name and prove zero
    mutation. Then exact-name undo must remove the complete profile and exact-
    name redo must restore it, including both construction references and clean
    solver state. Undo again, make a new controlled mutation, and prove redo is
    invalidated.

11. Prove unsaved documents stay pathless. In a disposable explicitly saved
    file, record bytes, size and timestamp; without calling save_document,
    create, undo and redo a polygon and prove external file bytes, size and
    timestamp are unchanged.

12. Tool selection fixtures: explicit equilateral triangle must call only
    create_sketch_equilateral_triangle; generic regular three-sided polygon and
    regular hexagon must call only create_sketch_regular_polygon; lower-left
    rectangle must call create_sketch_rectangle; centre-defined rectangle must
    call create_sketch_centered_rectangle; irregular three-vertex triangle must
    use add_sketch_geometry; modifying existing relationships must use
    add_sketch_constraints. Never manually reconstruct a regular semantic
    profile when its dedicated tool is available.

13. Run product regressions. Create one fully constrained upright origin
    equilateral triangle of circumradius 20 through one semantic triangle call.
    Create one fully constrained regular hexagon at (10,-5), circumradius 20,
    first vertex on positive X through one polygon call. Retain full controlled
    profiles, sketch inspections and history evidence. Also run lower-left and
    centred rectangle, tangent, symmetry, point-relationship and history
    regressions and prove their contracts remain unchanged.

14. Same-sketch recovery: create a technically valid triangle at a deliberately
    wrong centre/orientation, inspect and match the top transaction, exact-name
    undo it, then create the correction in the same sketch. Repeat for a polygon
    with a wrong side count/centre/radius/orientation. Require full old-profile
    removal, corrected profile, invalidated redo, one sketch object, and no
    abandoned geometry or replacement document.

15. Finish with raw tools/list and schemas, structured successes and expected
    failures, solver/history snapshots, deterministic mappings, construction
    restoration, Body/attachment and saved/unsaved evidence, product and
    recovery evidence, Report View output, exact repository status, and explicit
    confirmation that no repository edit, commit, or push occurred. Stop MCP
    and identify disposable documents for cleanup.
```
