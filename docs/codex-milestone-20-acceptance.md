# Codex Milestone 20 Live Acceptance Campaign

Status: prepared, not executed.

This is an autonomous external MCP-client campaign for tools 32–34. It tests
only behavior available through the running Streamable HTTP MCP endpoint. It
must not import project modules, call FreeCAD internals, invoke GUI commands, or
edit implementation source. Permanent native smoke owns injected rollback,
caller-owned transactions, expressions/names, save/reopen, and GUI-state facts
that the public endpoint cannot construct or observe.

## Outcome Rules

Use exactly one final classification:

- **PASS**: every scenario is publicly constructible and passes, with no
  capability gap.
- **PASS WITH CAPABILITY GAPS**: every publicly constructible scenario passes
  and each unavailable scenario is recorded under the explicit gaps below.
- **FAIL**: any constructible requirement fails, state leaks after refusal or
  rollback, the implementation repository changes, a native value leaks, or the
  campaign uses a forbidden workaround.

Never report **INCONCLUSIVE** merely because a public capability is missing.
Do not pause for an operator. Record the gap and continue autonomously.

## Safety Boundary

- Implementation repository: `C:\Users\Goran\git\freecad-mcp`.
- Disposable fixture holder: `C:\Users\Goran\git\freecad-test`.
- Never edit, install into, clean, reset, stage, commit, or push
  `freecad-mcp` during this campaign.
- `freecad-test` is a separate local-only workspace. It may be dirty and has no
  required remote. It may receive only disposable `.FCStd` fixtures explicitly
  created by `save_document`; never clean, reset, commit, or push it.
- Do not install dependencies or change FreeCAD configuration.
- Do not use arbitrary Python, native consoles, GUI selection/mouse simulation,
  edit mode, object deletion, expressions, naming, or unsupported native
  manipulation.
- Create every constructible CAD fixture through MCP.
- Record every request and complete raw response.
- After a failed atomic call, inspect state directly and do not call undo.
- Correct a wrong successful edit only by exact-name undo and retry in the same
  sketch.

Ordinary read-only shell commands may capture Git status and saved-file
size/timestamp/hash. They must not mutate either repository.

## Explicit Capability Gaps

Classify these without attempting workarounds:

1. Constraint expressions and names cannot be created by the current public
   tools. Expression/name refusal is permanent-smoke/unit evidence only.
2. Public `open_document` and `close_document` do not exist. Saved-byte
   no-auto-save behavior is live-testable; save/reopen persistence is native
   smoke evidence only.
3. Active-document identity is not publicly observable. Cross-document exact
   targeting/isolation is live-testable; active-document preservation is native
   smoke evidence only.
4. The deferred Milestone 18 broken-source case cannot be created because the
   API cannot delete or invalidate the source object.

These produce **PASS WITH CAPABILITY GAPS**, not a pause or failure, when every
available scenario passes.

## 1. Repository and Endpoint Baseline

From `freecad-mcp`, capture without modification:

```powershell
git status --short --branch
git branch --show-current
git rev-parse HEAD
git rev-parse "@{upstream}"
git diff --check
```

Capture a recursive path/size/SHA-256 manifest of every file under
`freecad-mcp` except `.git` object contents. Capture `freecad-test` status only
as fixture context; do not require it to be clean.

Connect as an external MCP client and preserve raw `tools/list`. Require exactly
this 34-tool order:

```text
create_document
list_documents
get_document
save_document
list_objects
get_object
recompute_document
create_body
create_sketch
get_sketch
add_sketch_geometry
add_sketch_constraints
get_document_history
undo_document
redo_document
create_sketch_rectangle
create_sketch_centered_rectangle
create_sketch_equilateral_triangle
create_sketch_regular_polygon
create_sketch_slot
create_sketch_rounded_rectangle
analyze_sketch
validate_sketch_profile
list_sketch_open_vertices
add_external_geometry
list_external_geometry
remove_external_geometry
get_sketch_dependencies
remove_sketch_constraints
remove_sketch_geometry
set_sketch_geometry_construction
update_sketch_geometry
replace_sketch_constraint
update_sketch_constraint_value
```

Canonicalize the first 31 raw schemas and require exact equality with the
accepted Milestone 19 baseline. Require `add_sketch_constraints` to retain
exactly its same 17 discriminated variants.

Require the new schemas to have `additionalProperties: false` at every
controlled object and required non-empty internal `document_name` and
`sketch_name`:

- `update_sketch_geometry`: strict non-negative integer `geometry_index` and a
  four-way discriminated `geometry` union containing only `line_segment`,
  `point`, `circle`, and `arc_of_circle`; no variant accepts `construction`.
- `replace_sketch_constraint`: strict non-negative integer `constraint_index`
  and `replacement` equal to the existing 17-variant constraint union, not a
  copy with an eighteenth discriminator.
- `update_sketch_constraint_value`: strict non-negative integer
  `constraint_index` and required numeric `value`.

## 2. Strict Rejection Matrix

For each tool send:

- missing document/sketch/index/payload properties;
- empty, whitespace, label-substituted, and nonexistent internal names;
- `true`, `1.0`, `"1"`, `-1`, and `null` as the index;
- a nonexistent non-negative index;
- one unknown top-level property.

For geometry send unknown discriminator, unknown nested fields, a
`construction` field, NaN/infinity if the client can encode them, zero/negative
radius, equal line endpoints, and equal-normalized arc endpoints. For
replacement send an unknown eighteenth discriminator, native negative geometry
references, unavailable geometry, malformed point positions, invalid values,
and unknown nested fields. For value send Boolean, string, null, NaN, and both
infinities.

Require controlled deterministic validation errors, no history change, and
exact before/after sketch/document/external/profile equality. No traceback,
native repr, memory address, transaction ID, `GeoId`, or negative native
geometry ID may appear.

## 3. Public Fixture Construction

Create unsaved documents `M20Primary` and `M20Isolation`, each with one Body and
one internal sketch named `Sketch`. In `M20Primary`, create a second internal
source sketch named `SourceSketch`.

Through `add_sketch_geometry`, add to `M20Primary/Sketch` in known order:

1. an unconstrained line;
2. an unconstrained point;
3. an unconstrained circle;
4. an unconstrained bounded circular arc;
5. a line for a geometric constraint;
6. independent lines/circles/points for dimensional constraints;
7. a closed profile for profile-impact checks where useful.

Create at least one `distance`, one `distance_x` or `distance_y`, one `radius`,
one `diameter`, one `angle`, and one `horizontal`/`vertical` constraint on
independent geometry. Add a supported `SourceSketch` projection through
`add_external_geometry`.

Before each mutation preserve raw results from:

- `get_sketch`;
- `analyze_sketch` and `validate_sketch_profile` when topology is relevant;
- `list_external_geometry` and `get_sketch_dependencies`;
- `get_document` and `get_document_history`;
- `list_documents` and the same-named `M20Isolation/Sketch`.

Use current readback indices. Never treat them as persistent IDs.

## 4. Constraint Value Updates

On independent fixtures prove:

1. Update `distance` to a different positive millimetre value.
2. Update `distance_x` or `distance_y` to a signed value permitted by the
   existing add-constraint contract.
3. Update `radius`, `diameter`, and `angle` to distinct valid values.
4. For every success require preserved constraint index/type, before/after
   controlled values and units, unchanged geometry/constraint counts, affected
   geometry indices, fresh healthy solver, profile impact, and exactly one top
   history name `Update sketch constraint value`.
5. Repeat the current controlled value. Require
   `sketch_constraint_value_unchanged`, `no_change: true`, identical state, and
   byte-for-byte unchanged history.
6. Target a geometric constraint. Require controlled
   `sketch_constraint_value_update_unsafe` with unsupported type and zero
   mutation.
7. Send zero/negative generic distance, radius, and diameter values. Require
   validation or controlled preflight refusal consistent with add semantics.
8. Construct a solver-unsatisfiable value case using only public constraints if
   possible. Require failure, exact state/history restoration, and no caller
   undo. If the public constraint creator itself refuses or cannot produce the
   necessary healthy starting fixture, record the native conflict-rollback
   smoke evidence as a bounded capability gap and continue.
9. Expression-backed/reference cases that cannot be publicly constructed are
   explicit capability gaps; do not manufacture them.

## 5. Constraint Replacement

1. Replace one geometric constraint with another solver-compatible supported
   geometric constraint, changing its geometry reference. Require the requested
   pre-call index, removed/replacement summaries, unchanged geometry count,
   preserved external reference, fresh solver/profile report, and one `Replace
   sketch constraint` history step.
2. Require `replacement_constraint_index` to equal the post-delete tail and
   require the complete survivor mapping ordered by old index. Never accept a
   claim that the original slot persisted unless it truly was a no-op.
3. Replace one dimensional constraint with a different supported dimensional
   form/value on compatible geometry and make the same checks.
4. Submit a semantically identical replacement. Require
   `sketch_constraint_unchanged`, `no_change: true`, identity mapping, and no
   history mutation.
5. Replace with an exact semantic duplicate of another surviving constraint.
   Require preflight `duplicate_constraint` refusal and exact state equality.
6. Use an invalid geometry reference. Require controlled refusal before
   mutation.
7. Replace a constraint with a supported but conflicting/redundant constraint.
   Require post-solver failure, exact rollback, no history entry, and no undo.
8. After that failure send a valid corrected replacement to the same sketch.
   Require success without replacement documents or sketches.
9. Preserve external mapping, construction flags, Body/attachment/placement,
   and the isolation document throughout.
10. Named/expression-sensitive replacement is an explicit capability gap when
    those fixtures cannot be created publicly.

## 6. Geometry Updates

On unconstrained supported elements, separately set complete desired final
states for:

1. one line (`start` and `end`);
2. one point (`position`);
3. one circle (`center` and `radius`);
4. one bounded arc (`center`, `radius`, and normalized counter-clockwise start
   and end angles).

For each require:

- exact target `geometry_index` retained;
- requested, before, and actual after controlled geometry;
- only that index in `affected_geometry_indices`;
- correct unchanged geometry and constraint counts;
- unchanged construction state, constraint identities, and external mappings;
- fresh healthy solver and explicit before/after profile impact;
- one top history name `Update sketch geometry`;
- no automatic save.

Then prove:

- repeat the exact current state and require `sketch_geometry_unchanged`, no
  recompute-visible drift, and no history;
- request line-to-circle or another type conversion and require
  `geometry_type_mismatch` with zero mutation;
- if public creation exposes only the four supported types, record unsupported
  conic/B-spline refusal as native/unit evidence rather than inventing one;
- target geometry controlled by a dimensional constraint with an actual change
  and require `dimensionally_controlled` plus dependency indices and guidance to
  use `update_sketch_constraint_value`;
- target geometry with a geometric dependency and require
  `dependent_constraints` plus exact impact;
- submit an already-correct state for constrained geometry and require the
  semantic no-op to precede dependency refusal;
- verify construction and normal profile participation is unchanged.

## 7. History, Recovery, and Redo Invalidation

For one success of each tool:

1. Call `undo_document` with a deliberately wrong expected transaction name.
   Require controlled history mismatch and zero state change.
2. Undo once with the exact expected name. Require complete restoration and one
   corresponding redo entry.
3. Redo and require the edited state and index/remapping contract again.
4. Undo, perform a different valid edit in the same sketch, and require redo
   invalidation.
5. Correct wrong successful intent only through exact-name undo and same-sketch
   retry. Never create replacement documents or sketches.

Failed atomic calls must leave no history and require no undo.

## 8. Saved and Unsaved State

Create a separate document and save it through `save_document` to a new
`.FCStd` path under `freecad-test`. Capture file bytes, size, timestamp, and open
document path. Perform representative successful geometry, replacement, and
value edits without another save. Require unchanged on-disk hash/metadata and
the retained document path. Save explicitly and require bytes to change.

Public close/reopen is unavailable; record persistence-after-reopen as a
capability gap covered by permanent native smoke. Do not close/open through GUI
or Python.

For unsaved fixtures require `file_path: null`/unsaved state before and after
every edit.

## 9. Cross-Document Isolation and Active-Document Gap

Mutate `M20Primary/Sketch` by exact names while preserving complete
`M20Isolation/Sketch` and document snapshots. Repeat with roles reversed.
Require no label/internal-name confusion and exact isolation.

Because active-document identity is not publicly observable, record active
identity preservation as a capability gap covered by native smoke. Do not use
GUI or native introspection to fill it.

## 10. Read-Only and Leakage Audit

Repeat all read-only sketch, profile, dependency, external, document, history,
and inventory calls. Require no geometry/constraint/construction/solver,
attachment/Body/placement, external, history, saved-state, selection, or edit
mode mutation where publicly observable.

Search all captured requests/results for native object representations, `0x`
addresses, `GeoId`, negative native geometry IDs, raw link arrays, arbitrary
Python, GUI commands, or transaction IDs. Require none.

## 11. Final Preservation and Report

Repeat baseline Git status, branch, HEAD/upstream, `git diff --check`, and the
implementation repository manifest. Require exact equality. Report
`freecad-test` only as disposable fixture state and do not clean it.

The final report must include:

1. raw 34-tool order and three new raw schemas;
2. canonical proof that the first 31 schemas are unchanged;
3. proof that replacement and add share exactly the unchanged 17 variants;
4. strict rejection matrix;
5. all supported geometry/value updates and units;
6. same-type and dependency policy evidence;
7. replacement append index and complete survivor mapping;
8. no-op, duplicate, conflict, rollback, and same-sketch correction evidence;
9. profile, solver, construction, external, Body, and attachment preservation;
10. history mismatch, undo/redo, and redo invalidation;
11. saved/unsaved and cross-document isolation evidence;
12. no-native-leakage audit;
13. each explicit capability gap and its permanent-smoke/unit evidence;
14. exact ending repository status and confirmation of no install, commit, or
    push.

Classify as **PASS WITH CAPABILITY GAPS** when the four listed unavailable areas
remain unavailable and all constructible scenarios pass. Classify **FAIL** for
any constructible failure or safety-boundary violation.
