# Codex Milestone 16 Live Acceptance Campaign

Status: prepared, not executed by the implementation task.

This is an operator-run acceptance campaign for a real FreeCAD 1.1.1 session
and live MCP endpoint. It must inspect and exercise the built revision without
editing repository files, installing packages, committing, or pushing.

## Preconditions and evidence capture

1. Record `git status --short --branch`, `git rev-parse HEAD`, both configured
   remote URLs, and both remote default-branch revisions.
2. Record the hosted GitHub and Codeberg CI result for that exact revision.
3. Record FreeCAD `App.Version()`, full revision, `sys.version`, MCP SDK version,
   FreeCAD user-data directory, and addon link target.
4. Start FreeCAD with the MCP workbench installed from this repository. Open
   Report View and preserve all `[MCP]` output.
5. Start MCP once. Preserve raw `tools/list`, not a paraphrase.
6. Require exactly 21 tools in registry order. Require tool 20
   `create_sketch_slot` and tool 21 `create_sketch_rounded_rectangle`. Diff the
   first 19 names and raw schemas against the pinned Milestone 15C evidence.
7. Preserve raw `add_sketch_constraints` schema and require exactly the existing
   17 discriminated variants. Require no endpoint-tangent public variant and no
   slot or rounded-rectangle primitive geometry discriminator.

## Raw schema acceptance

Preserve the complete raw input schema for both new tools.

For `create_sketch_slot`, require exactly:

```text
document_name
sketch_name
overall_length
overall_width
center {x,y}
angle_degrees = 0.0 (optional)
```

Require `additionalProperties: false` at the request and centre levels,
strict finite numbers, positive dimensions, and no `radius`, `diameter`,
`centre_distance`, `straight_length`, `placement`, `rotation`, construction,
or index fields.

For `create_sketch_rounded_rectangle`, require exactly:

```text
document_name
sketch_name
width
height
corner_radius
placement = lower_left {type,x,y} | center {type,x,y}
```

Require a discriminator on `type`, `additionalProperties: false` at every
level, and no angle, rotation, per-corner radius, construction, constraint, or
index fields.

## Slot product fixture

Use this intent verbatim:

> Create a fully constrained horizontal slot centred on the sketch origin,
> with an overall length of 40 mm and an overall width of 12 mm.

Require one `create_sketch_slot` call. Reject a primitive recipe, full circles,
rounded-rectangle substitution, replacement sketch, or GUI command. Preserve
the raw request and result.

After recompute and `get_sketch`, require:

- exactly 2 normal lines and 2 bounded normal arcs at the returned profile
  indices, with no reference/helper geometry;
- semantic append mapping top, right arc, bottom, left arc;
- two 180° counter-clockwise visible arc sweeps, intended outward sides, and
  exact bounded endpoints;
- four closed bounded joins with tangent flags and exact endpoint references;
- centre `(0,0)`, overall length 40, overall width 12, radius 6, straight
  centre distance 28, angle 0;
- closed, tangent, counter-clockwise, fully constrained;
- zero DoF and empty redundant, partially redundant, conflicting, and malformed
  diagnostics;
- exactly 9 new constraints and one top history step `Create sketch slot`;
- document remains unsaved.

## Slot transformed and boundary fixtures

In isolated sketches, run:

1. length 50, width 10, centre `(12,-7)`, angle 30;
2. angle -30;
3. angle 390;
4. length 12.001, width 12.

Require rotated coordinates and arc centres, equivalent -30/330 and 390/30
readback, stable 0 DoF near the strict boundary, exactly 10 constraints for
non-origin placement, and no hidden helper geometry.

Reject with zero mutation and zero history:

- length equal to or below width;
- zero/negative dimensions;
- Boolean, NaN, or infinite numeric values;
- missing/extra centre fields and forbidden request fields.

## Rounded-rectangle product fixtures

First use lower-left placement `(-20,-12)`, width 40, height 24, radius 4.
Then use this intent verbatim in a separate sketch:

> Create a fully constrained axis-aligned rounded rectangle centred on the
> sketch origin, 40 mm wide and 24 mm high, with a 4 mm corner radius.

Require one `create_sketch_rounded_rectangle` call for each. The centred intent
must remain a direct `center` placement request; reject translation to a
lower-left MCP call, sharp rectangle plus fillet, primitive reconstruction,
replacement sketch, or GUI command.

After recompute and inspection, require:

- external bounds `(-20,-12)` to `(20,12)` for both placement variants;
- exactly four normal lines and four bounded normal quarter arcs, alternating
  bottom, lower-right arc, right, upper-right arc, top, upper-left arc, left,
  lower-left arc;
- all radii 4, all visible sweeps 90° counter-clockwise, correct corner centres,
  exact line endpoints, eight closed bounded tangent joins, and no helpers;
- axis-aligned, counter-clockwise, fully constrained, zero DoF, and clean
  diagnostics;
- 20 constraints for lower-left placement and 19 for centre-at-origin;
- one `Create sketch rounded rectangle` history step and unchanged unsaved
  state.

Also test centre `(12,-7)`, width 30, height 18, radius 3 and radius 11.999 for
40×24. Reject radius 0, radius 12, and radius above 12 with zero mutation.

## Existing-state and attachment preservation

For each tool:

1. Start with unrelated fully constrained normal geometry, construction
   geometry, and at least one existing bounded arc.
2. Snapshot controlled geometry including arc parameters, construction flags,
   constraints, solver state, Body ownership, support, MapMode, placement,
   history, document identity, path, and modified state.
3. Create the profile at non-zero geometry and constraint offsets.
4. Require the returned mappings contain only appended normal profile geometry,
   `reference_geometry_indices` is empty, and all earlier state is exact.
5. Repeat in a Body-owned unattached sketch and a Body-owned XY-plane-attached
   sketch. Require object identity, parent, support, MapMode, and placement to
   remain exact.
6. Create in document A while document B is open and active; require B geometry,
   constraints, history, path, and modified state unchanged.

## History, recovery, and persistence

For each tool:

1. Require exactly one named history step.
2. Attempt undo with a wrong expected name and prove no state change.
3. Undo with the exact name and require the complete profile disappears while
   the sketch and earlier content remain.
4. Redo with the exact name and require geometry, bounded sweeps, tangent
   relations, mappings, and 0 DoF return.
5. Undo again, make a new controlled mutation, and require redo invalidation.
6. Create a technically valid but deliberately wrong profile, inspect the
   strategic error, undo it by exact name, and create the correction in the
   same sketch. Require no replacement sketch and no abandoned geometry.
7. In an explicitly saved disposable FCStd, snapshot path, bytes, size,
   timestamp, and controlled modified state. Create, undo, and redo without any
   save tool. Require external bytes, size, and timestamp unchanged. Repeat in
   an unsaved document and require no file path appears.

## Failure and rollback campaign

Use a disposable test harness or approved failure-injection build, never a
production document. Inject each geometry position, first/middle/last
constraint, tangent join classes, equality, radius, size, placement,
orientation, recompute, solver inspection, semantic readback, and commit
failure. Corrupt open topology, arc side/sweep, major arcs, radii, dimensions,
centre/bounds, tangent endpoint, orientation, helper count, DoF, conflict,
partial redundancy, redundancy, and malformed diagnostics.

For every failure require a controlled code, no traceback/native text, complete
snapshot restoration, no partial line/arc/helper, no history entry, and correct
caller-owned transaction preservation. Do not call undo after rollback.

## Regression and selection acceptance

Run the complete quality gate and all native smokes, including
`smoke_sketch_curved_profiles.py` at 78/78. Require earlier rectangle, centred
rectangle, triangle, polygon, tangent, symmetric, point-relationship, native
reference, and history smokes to remain green.

Protect these selections in raw descriptions and natural-language trials:

```text
slot / straight slot / obround / capsule / pill-shaped → create_sketch_slot
rounded / filleted axis-aligned rectangle → create_sketch_rounded_rectangle
sharp lower-left rectangle → create_sketch_rectangle
sharp centred rectangle → create_sketch_centered_rectangle
regular polygon → create_sketch_regular_polygon
custom line-and-arc path → add_sketch_geometry
modify existing relationships → add_sketch_constraints
```

## Final evidence bundle

Preserve raw tools and schemas, every structured success/failure envelope,
profile and sketch readbacks, solver diagnostics, history snapshots, Report
View output, saved-file metadata, smoke reports, quality-gate output,
`git diff --check`, and final repository status. Confirm the live campaign did
not edit, commit, or push. Stop MCP and close disposable documents without
saving unless a save-preservation fixture explicitly requires a temporary file.
