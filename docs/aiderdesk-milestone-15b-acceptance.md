# Milestone 15B AiderDesk Live Acceptance Prompt

This prompt is prepared for a separate FreeCAD Engineer AiderDesk campaign. It
is not executed by the Milestone 15B implementation task.

Use a fresh FreeCAD 1.1.1 session connected only to the FreeCAD MCP endpoint.
Every CAD mutation and inspection must use an exposed MCP tool. Do not use the
GUI Rectangle command, Python console, direct FreeCAD API, mouse/selection
simulation, or repository editing tools.

Copy the following prompt into AiderDesk:

```text
Perform the Milestone 15B semantic centred-rectangle acceptance campaign
entirely through the connected FreeCAD MCP endpoint.

Repository preservation is mandatory. Before and after the campaign record the
branch, HEAD, upstream, all remotes, and git status. Make no file edit, stage,
commit, push, pull, checkout, reset, cleanup, generated repository file, or
dependency/environment change.

Start with raw tools/list. Require exactly these seventeen tools in this order:
create_document, list_documents, get_document, save_document, list_objects,
get_object, recompute_document, create_body, create_sketch, get_sketch,
add_sketch_geometry, add_sketch_constraints, get_document_history,
undo_document, redo_document, create_sketch_rectangle,
create_sketch_centered_rectangle. Prove the first sixteen input schemas are
unchanged. Prove add_sketch_constraints still has exactly the established
seventeen discriminator variants.

Capture the raw create_sketch_centered_rectangle schema. Require exactly
document_name, sketch_name, width, height, and center. Require center to contain
exactly x and y, with additionalProperties=false at both levels. Require finite
strict positive width/height and finite strict center coordinates; booleans,
NaN, and infinities must fail. Prove placement, lower_left, corner, centre,
rotation, angle, orientation, construction, fully_constrain, profile_name,
branch controls, geometry/constraint indices, raw native objects, and extra
fields are unavailable. Capture create_sketch_rectangle separately and prove it
still requires exactly lower-left placement and has no center field.

Apply this tool-selection policy throughout:
- centre/center + width + height → create_sketch_centered_rectangle;
- lower-left corner + width + height → create_sketch_rectangle;
- custom, incomplete, or non-rectangular lines → add_sketch_geometry;
- modification of existing relationships → add_sketch_constraints.
Do not calculate a lower-left corner and call tool 16 for centre intent. Do not
manually reconstruct a complete rectangle with primitive tools. Never invoke a
GUI command or call one MCP tool from another. The campaign FAILS if a
centre-defined request is translated to tool 16 unless tool 17 first returns a
documented, independently verified unrecoverable failure.

In isolated unsaved sketches exercise center (0,0), a positive center, a
negative center, mixed signs, cx=0/cy!=0, cx!=0/cy=0, and both coordinates
nonzero. Include width/height integers and finite fractional values. Recompute
and inspect every success.

For each success require exactly four normal profile edges in this order:
bottom lower-left→lower-right, right lower-right→upper-right, top
upper-right→upper-left, left upper-left→lower-left. Require exactly one fifth
geometry element: a construction point at center. Require geometry_indices to
contain only the four edges, reference_geometry_indices to contain only the
point, and the controlled center reference position to be point. Require no
diagonal, center line, helper circle, duplicate corner, extra construction
point, hidden geometry, or incidental helper element. Report exactly 4 profile
edges, 1 semantic construction reference, and 0 incidental helpers.

Require deterministic bottom/right/top/left edge mappings and
lower_left/lower_right/upper_right/upper_left corner mappings even when the
append offset is nonzero. Verify exact requested width/height and these derived
coordinates for every case: cx±width/2 and cy±height/2. Verify closure, bottom
and top horizontal, right and left vertical, center-point coordinates, and the
midpoint of lower-left/upper-right equal to center.

Inspect controlled constraint readback in exact order: four endpoint
coincidences, bottom/right/top/left orientation, bottom width, right height,
lower-left and upper-right symmetric about the construction point, then center
placement. At (0,0) require point-to-origin coincidence and exactly 12 total
constraints. With cx=0 require vertical-axis point_on_object plus Y distance;
with cy=0 require horizontal-axis point_on_object plus X distance; with both
nonzero require X and Y distances; each non-origin branch must have exactly 13
constraints. Prove no lower-left coordinate placement constraints were used.
Require zero degrees of freedom, fully_constrained=true, and empty conflicting,
redundant, partially redundant, and malformed lists.

Product test one: from only this natural-language intent, “Create a 30 mm ×
20 mm axis-aligned rectangle centred on the sketch origin. Fully constrain it
using natural centre-based parametric relationships.” Require one
create_sketch_centered_rectangle call. Require bottom (-15,-10)→(15,-10), right
(15,-10)→(15,10), top (15,10)→(-15,10), left (-15,10)→(-15,-10), center point
(0,0), direct point-centred symmetry, 12 constraints, zero DoF, clean
diagnostics, no diagonal, one Create centered sketch rectangle history step,
and an unsaved document that remains unsaved.

Product test two: create width 30, height 20, center (12,-7). Require bounds
lower-left (-3,-17), lower-right (27,-17), upper-right (27,3), upper-left
(-3,3), point (12,-7), matching midpoint, direct symmetry, 13 constraints,
zero DoF, clean diagnostics, and no lower-left placement semantics.

Create a sketch containing unrelated normal geometry, construction geometry,
existing constraints, and a solved profile. Snapshot all controlled geometry,
coordinates, construction flags, constraints, solver state, indices, ownership,
support, MapMode, placement, document path, and history. Append a centred
rectangle and prove prior content is unchanged, the new edges append in four
contiguous indices, and the point appends next. Undo and redo the exact profile
and prove the complete pre-existing snapshot is preserved.

Create a Body-owned XY-plane-attached sketch and a representative supported
attached sketch. Across create, exact-name undo, recompute, exact-name redo,
and recompute, prove Body ownership, support, MapMode, placement, sketch
identity, and object hierarchy are unchanged. Prove no duplicate or top-level
replacement sketch appears.

For an unsaved document prove file_path remains null and no FCStd file appears
across create/undo/redo. For a disposable explicitly saved document record path,
file size, timestamp, hash, and modified state. Without save_document, create,
undo, and redo; prove path and external bytes/size/timestamp/hash never change.
Report native in-memory modified state without claiming undo is file rollback.

After a successful call inspect history and require one top transaction named
exactly Create centered sketch rectangle. First call undo_document with a wrong
expected name and prove zero mutation. Then undo with the exact name and prove
all four edges, point, and constraints disappear in one step while the sketch
and prior content remain. Recompute and inspect. Redo with the exact name,
recompute, and prove edge/corner order, point coordinates, point construction
state, symmetry, placement, constraint count, zero DoF, and clean diagnostics
are restored. Undo again, perform a new controlled mutation, and prove redo is
invalidated.

Exercise rejected zero/negative dimensions, boolean and nonfinite numbers,
missing center, missing center coordinate, extra center fields, placement,
lower_left, rotation, construction, empty names, and extra top-level fields.
For every structured failure compare the full before/after sketch, document,
solver, and history snapshot and prove zero mutation, no abandoned center point,
no partial rectangle, and no history entry. Do not call undo after an atomic
failure that already rolled back.

Same-sketch recovery test: create correct dimensions at a deliberately wrong
center. Recompute and show it is technically valid but strategically misplaced.
Inspect history, require Create centered sketch rectangle, undo exactly that
step, and prove four edges, point, and constraints are gone while original
content and the same sketch remain. Create the corrected centred rectangle in
that same sketch, recompute, and verify center, bounds, symmetry, counts, zero
DoF, and clean diagnostics. Prove the old redo was invalidated and no
replacement sketch, abandoned rectangle, or abandoned center point exists.

Run separate tool-selection fixtures: “Create a 40 × 20 rectangle centred at
(5,-3)” must choose tool 17; “Create a 40 × 20 rectangle with lower-left corner
at (5,-3)” must choose tool 16; four independent unconstrained lines must use
add_sketch_geometry; modifying an existing relationship must use
add_sketch_constraints.

Finish by reporting raw tools/list and schemas; the unchanged seventeen
constraint variants; every structured success/failure; origin, arbitrary, axis
branch, non-empty, attached, saved/unsaved, rollback, history, construction
restoration, name mismatch, redo invalidation, product, tool-selection, and
same-sketch recovery evidence; Report View output; final repository status; and
confirmation that no repository edit, commit, or push occurred. Stop MCP and
leave all disposable documents clearly identified for cleanup.
```

Retain the transcript, raw schemas, controlled before/after snapshots, solver
and history results, saved-file metadata, Report View output, and unchanged
repository status. The automated suite and embedded 47-scenario smoke are
supporting evidence, not substitutes for this separate live endpoint campaign.
