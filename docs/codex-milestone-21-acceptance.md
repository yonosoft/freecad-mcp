# Codex Milestone 21 Live Acceptance Campaign

Status: prepared, not executed.

This is an autonomous external MCP-client campaign for tool 35,
`add_sketch_reference_constraints`. Execute only through the running Streamable
HTTP MCP endpoint. Never import project modules, call FreeCAD internals, invoke
GUI commands, or edit implementation source. Create every constructible fixture
through public MCP tools, including source changes through Milestone 20
`update_sketch_geometry`.

## Outcome rules

Use exactly one final classification:

- **PASS**: every required scenario is publicly constructible and passes with
  no capability gap.
- **PASS WITH CAPABILITY GAPS**: every constructible scenario passes and every
  unavailable observation or fixture is recorded under the explicit gaps.
- **FAIL**: any constructible requirement fails, a refusal mutates state, an
  atomic failure leaks state/history, native identity leaks, repository state
  changes, or the campaign uses a forbidden workaround.

Do not use **INCONCLUSIVE** merely because public lifecycle, transaction, or
observation tools are missing. Record the gap and continue autonomously.

## Safety boundary

- Implementation repository: `C:\Users\Goran\git\freecad-mcp`.
- Disposable fixture holder: `C:\Users\Goran\git\freecad-test`.
- Never edit, install into, clean, reset, stage, commit, or push
  `freecad-mcp`.
- `freecad-test` is a separate local-only workspace. It may already be dirty
  and need not have a remote. It may receive only disposable `.FCStd` files
  created by `save_document`; never clean, reset, commit, or push it.
- Do not install dependencies or change FreeCAD configuration.
- Do not use arbitrary Python, a native console, GUI commands, selection/mouse
  simulation, edit mode, object deletion, document open/close workarounds,
  active-document mutation, expressions, constraint naming, or unrestricted
  mutation.
- Preserve every raw request and complete raw response.
- After a failed atomic call, inspect state and do not call undo.
- Correct a wrong success only through exact-name undo and retry in the same
  sketch.

Read-only shell commands may capture repository status and saved-file
size/timestamp/hash. They must not mutate either workspace.

## Explicit capability gaps

Record these without workaround:

1. Public object deletion cannot create a broken-source mapping. Broken-source
   reporting and stale native-index behavior remain native-smoke/probe evidence.
2. Public `open_document` and `close_document` do not exist. Live saved-byte
   no-auto-save behavior is testable; save/reopen is permanent-native-smoke
   evidence.
3. Active-document identity is not publicly observable. Exact-name
   cross-document isolation is testable; active identity preservation is
   native-smoke evidence.
4. No public operation deliberately opens a caller-owned transaction around
   another MCP call. Caller-owned success/failure preservation is native-smoke
   evidence.
5. Constraint names and expressions remain unavailable until Milestone 22.
   Expression-sensitive interaction stays deferred.
6. Post-native injected rollback cannot be forced through public MCP. Use a
   naturally constructible solver failure if one is available; otherwise cite
   permanent-smoke rollback evidence.

These yield **PASS WITH CAPABILITY GAPS**, not a pause or failure, when all
publicly constructible scenarios pass.

## 1. Repository and endpoint baseline

From `freecad-mcp`, capture without modification:

```powershell
git status --short --branch
git branch --show-current
git rev-parse HEAD
git rev-parse "@{upstream}"
git diff --check
```

Capture a recursive path/size/SHA-256 manifest under `freecad-mcp`, excluding
`.git` object contents. Capture `freecad-test` status only as fixture context;
do not require it to be clean.

Connect as an external MCP client and preserve raw `tools/list`. Require exactly
this 35-tool order:

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
add_sketch_reference_constraints
```

Canonicalize the first 34 raw schemas and require exact equality with the
accepted Milestone 20 baseline. Require `add_sketch_constraints` to retain its
same 17 discriminator names and existing modes.

## 2. Tool 35 schema audit

Require top-level `additionalProperties: false`, required non-empty internal
`document_name` and `sketch_name`, and a required `constraints` array with
`minItems: 1`, `maxItems: 100`.

Require exactly the original 17 discriminator names:

```text
horizontal, vertical, horizontal_points, vertical_points,
parallel, perpendicular, equal, coincident, point_on_object,
symmetric, tangent, distance, distance_x, distance_y,
radius, diameter, angle
```

Require the exact existing nested modes:

- `distance`: `line_length`, `point_to_origin`, `between_points`;
- `distance_x`: `point_to_origin`, `between_points`;
- `distance_y`: `point_to_origin`, `between_points`;
- `angle`: `line_angle`, `between_lines`.

Require a strict `kind` discriminator with only:

```json
{"kind":"internal","geometry_index":0}
{"kind":"external","external_reference_number":0}
```

Require point operands to wrap one such object in `geometry` and reuse only
`start`, `end`, `center`, or `point` as `position`. Require
`additionalProperties: false` at every nested object. No request schema may
accept `native_id`, `GeoId`, a raw negative geometry index, LinkSub data, a
source-object pointer, or an arbitrary native signature.

## 3. Strict rejection matrix

Before each case capture `get_sketch`, `list_external_geometry`,
`get_sketch_dependencies`, `get_document`, and `get_document_history`. Send:

- missing/empty/whitespace/label-substituted/nonexistent document and sketch
  names;
- non-array, empty, and 101-item constraint batches;
- missing, unknown, and eighteenth discriminator values;
- missing/unknown `kind`;
- `true`, `1.0`, `"1"`, `-1`, and `null` for each geometry identity;
- nonexistent non-negative internal and external identities;
- unknown top-level and nested properties, including `native_id: -3`;
- Boolean, string, null, NaN, and infinities for numeric values where the
  transport can encode them;
- invalid and type-incompatible point positions;
- identical operands, Point-on-Object without exactly one point role,
  degenerate symmetry references, and exact duplicate batch entries.

Require deterministic controlled validation/preflight errors, no traceback,
and byte-equivalent controlled state/history before and after. Search responses
for memory addresses, native reprs, transaction IDs, raw exceptions, `GeoId`,
and negative native geometry IDs; require none.

## 4. Public fixture construction

Create unsaved documents `M21Primary` and `M21Isolation`, both with a Body and
same-named target sketch `Target`. In `M21Primary`, create source sketches with
independent lines, circles/arcs where needed, and two triangle source sketches.
Create target sketches with independent internal lines, endpoints, circles,
arcs, and points. Add external geometry only with `add_external_geometry` and
record each returned current-order-local `external_reference_number`.

For an object-edge/object-vertex representative, create a public solid through
available MCP creation tools only if a suitable edge and vertex can be exposed.
If current public tools cannot construct such a solid, record object-edge and
object-vertex use as permanent-smoke evidence; do not invoke native APIs.

Before every mutation preserve raw snapshots from:

- `get_sketch`;
- `analyze_sketch` and `validate_sketch_profile` when topology matters;
- `list_external_geometry` and `get_sketch_dependencies`;
- `get_document` and `get_document_history`;
- `list_documents` and `M21Isolation/Target`.

Always use current readback indices. Never treat geometry, constraint, or
external-reference numbers as persistent identity.

## 5. Internal-only parity for all variants and modes

On independent compatible geometry, call tool 35 with internal-only operands
for every one of the 17 discriminators and all nine nested mode entries listed
above. Compare each successful semantic result with an equivalent fixture made
through unchanged `add_sketch_constraints`.

Require equivalent native-facing controlled type, point positions, values and
units, solver intent, geometry movement, result ordering, undo/redo behavior,
and no native identity leakage. Tool 35 must return its dedicated normalized
reference-aware result; do not require its additive fields to appear in the old
tool's result. Confirm documentation continues to prefer
`add_sketch_constraints` for internal-only work.

## 6. Supported mixed capability matrix

Using separate healthy fixtures, cover every supported mixed class and both
operand orders where meaningful:

1. `horizontal_points` with internal/external and external/internal points.
2. `vertical_points` in both orders.
3. `parallel` and `perpendicular` line pairs in both orders.
4. `equal` for line/line, circle/circle, circle/arc, arc/circle, and arc/arc.
5. `coincident` for an external line endpoint and internal endpoint in both
   orders.
6. `point_on_object` with external point/internal line, arc, or circle, then
   internal point/external target.
7. `tangent` for every supported heterogeneous order and circular pair:
   line/circle, circle/line, line/arc, arc/line, circle/circle, circle/arc,
   arc/circle, and arc/arc.
8. `distance/between_points` in both orders.
9. `distance_x/between_points` and `distance_y/between_points`, preserving
   request order and signed semantics.
10. `angle/between_lines` in both orders where compatible values can be
    constructed.
11. Supported symmetry arrangements: mixed point operands about origin;
    internal points about an external point; external points about an internal
    point; and two internal points about an external line.

For each success require exact added index/order, normalized public operands,
external and internal identity summaries, unchanged source geometry, preserved
external mapping/order, exact dependency usage, fresh healthy solver,
unchanged unrelated target state, one top `Add sketch reference constraints`
history entry, and no automatic save.

## 7. Unsupported capability classes

On healthy resolved references, require pre-transaction refusal and exact zero
mutation for:

- unary external `horizontal`, `vertical`, line length, point-to-origin
  distance/x/y, radius, diameter, and line angle;
- every representative external-only relationship;
- line/line tangent and point-involving tangent;
- incompatible equal pairs;
- invalid Point-on-Object target type or operand role;
- mixed symmetry about a native axis;
- mixed symmetry about an internal line;
- mixed point operands about an external line;
- a batch with one supported and one unsupported item;
- duplicate against an existing constraint;
- missing/out-of-range external reference and incompatible point selector.

There was no observed `NATIVE_UNSAFE` status in the isolated 144-worker
campaign. Record that truthfully; do not invent a crash case. The stale/broken
fixture is an explicit public capability gap when it cannot be created without
object deletion.

After a refused request, send a corrected supported request to the same sketch
and require success without a replacement sketch or document.

## 8. Circumcircle Point-on-Object workflow

Create a source triangle through MCP and add its three vertex identities as
external line endpoints in a target sketch containing one internal circle.
Add three `point_on_object` constraints placing those external endpoints on the
internal circle. Do not use Coincident for a circle circumference.

Require one internal circle, exactly three added constraints, exact dependency
indices, healthy solver, and unchanged source. Record the circle state. Use
`update_sketch_geometry` on the source to change one side endpoint/side length,
then recompute and inspect. Require:

- source edit succeeds independently;
- external mapping stays resolved and ordered;
- circle centre and/or radius changes;
- exactly one circle and three constraints remain;
- no manual target value calculation and no new target item;
- document remains unsaved unless explicitly saved.

## 9. Incircle tangent workflow

Create a source triangle and project all three edges into a target sketch with
one internal circle. Add three whole-geometry tangent constraints between the
circle and external edges. Require one circle, three constraints, healthy
solver, exact dependencies, and unchanged source.

Change one source side through `update_sketch_geometry`, recompute, and require
the circle centre/radius to update while one circle, three constraints, and all
mappings remain. Repeat the same propagation protocol for at least one
parallel or perpendicular internal-line/external-line relationship.

## 10. Dependency, removal, and editing interaction

For a supported mixed constraint:

1. Require `list_external_geometry` and `get_sketch_dependencies` to report the
   exact consuming constraint index.
2. Call `remove_external_geometry`; require dependent-constraint refusal,
   exact index, zero mutation, and no history.
3. Call `remove_sketch_geometry` on the internal operand; require exact
   dependency refusal and zero mutation.
4. Attempt an actual `update_sketch_geometry` on the controlled internal
   target; require the existing dependency-policy refusal.
5. Attempt `replace_sketch_constraint`; require its existing controlled
   unsupported refusal with unchanged schema/state.
6. For a supported mixed dimensional constraint, attempt
   `update_sketch_constraint_value`; require its existing controlled
   unsupported refusal.
7. Explicitly call `remove_sketch_constraints` for the exact mixed constraint.
   Require ordered survivor mapping, preserved external identity/order, and
   dependency usage removal.
8. Remove the now-unused external reference and require success.
9. Undo/redo the explicit constraint removal and require mappings and usage to
   restore/remap exactly.

## 11. Batch, history, recovery, and redo

For a successful multi-constraint request require request-order result indices
and exactly one history step. Then:

1. Call `undo_document` with a deliberately wrong expected name. Require
   controlled mismatch and zero state change.
2. Undo with exact `Add sketch reference constraints`. Require complete
   restoration and one matching redo entry.
3. Redo and require the full constrained/dependency state.
4. Undo, perform a different valid mutation, and require redo invalidation.
5. Correct wrong successful intent only through exact-name undo and same-sketch
   retry.

Construct a natural solver-invalid batch using only public operations if
possible. Require exact rollback, zero history, and no caller undo. If no such
healthy public fixture can be built, record the injected owned/caller-owned
permanent-smoke rollback evidence as the explicit gap. Never use native code to
manufacture the failure.

## 12. Saved and unsaved behavior

Save a dedicated document through `save_document` to a new `.FCStd` path under
`freecad-test`. Capture file hash, size, timestamp, and public path. Add a
representative mixed constraint without saving again. Require unchanged bytes
and metadata, retained path, correct open controlled state, and one history
step. Save explicitly and require bytes to change.

Public close/reopen is unavailable; record save/reopen as a gap covered by the
permanent native smoke. For unsaved documents require null/empty public file
path before and after every success and refusal.

## 13. Cross-document isolation and leakage audit

Mutate `M21Primary/Target` by exact names while preserving the complete
`M21Isolation/Target` state; repeat with roles reversed. Require no label/name
confusion. Active-document identity is a declared observation gap.

Repeat all read-only sketch/profile/dependency/external/document/history calls
and require no state or history mutation. Search every captured request and
response for:

- negative native geometry IDs or `GeoId`;
- raw FreeCAD objects or constraints;
- LinkSub arrays or source object pointers;
- `0x` addresses or transaction IDs;
- tracebacks, raw exceptions, arbitrary Python, or GUI commands.

Require none. `get_sketch` may additively return
`kind: external_geometry` with a non-negative
`external_reference_number`; internal-only summaries must remain canonical and
unchanged.

## 14. Final repository preservation and report

Repeat baseline Git status, branch, HEAD/upstream, `git diff --check`, and the
implementation manifest. Require exact equality. Report `freecad-test` only as
disposable fixture state and do not clean it.

The final report must include:

1. raw 35-tool order and canonical equality of the first 34 schemas;
2. unchanged old and exact new 17-way unions and every mode;
3. strict operand/point/additional-properties rejection evidence;
4. every supported mixed class, geometry pair, and operand order;
5. every unsupported status class and zero-mutation proof;
6. explicit statement that no `NATIVE_UNSAFE` case was observed;
7. circumcircle, incircle, and linear source-propagation results;
8. dependency/removal/editing interaction;
9. batch order/atomicity, duplicate refusal, history, undo/redo, redo
   invalidation, and same-sketch correction;
10. saved/unsaved and cross-document isolation evidence;
11. native-leakage audit;
12. every capability gap and corresponding permanent-smoke/probe evidence;
13. exact ending repository state and confirmation of no install, commit, or
    push.

Classify **PASS WITH CAPABILITY GAPS** when the listed unavailable public areas
remain unavailable and all constructible cases pass. Classify **FAIL** for any
constructible failure or safety-boundary violation.
