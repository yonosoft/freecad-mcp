# Codex Milestone 19 Live Acceptance Campaign

Status: prepared, not executed.

This is an operator-run external MCP-client campaign for tools 29–31. It must
not import project Python modules, call FreeCAD internals, invoke GUI commands,
or edit the implementation repository. Native rollback injection and
caller-owned transaction mechanics are covered by the permanent runtime smoke;
this campaign verifies only behavior available through the public MCP endpoint.

## Safety Boundary

- Implementation repository: `C:\Users\Goran\git\freecad-mcp`.
- Disposable fixture holder: `C:\Users\Goran\git\freecad-test`.
- Do not edit the implementation repository during this campaign.
- `freecad-test` is local-only, may be dirty, has no required remote, and must
  not be treated as implementation source. It may receive only the explicit
  disposable saved fixtures required below; do not clean, reset, commit, or
  push it.
- Do not install dependencies or change FreeCAD configuration.
- Do not use arbitrary Python, GUI selection, mouse simulation, edit mode,
  document-object deletion, or unsupported native manipulation.
- Do not manufacture the deferred Milestone 18 broken-source case.
- Use only the running MCP server, structured MCP results, ordinary read-only
  shell status/hash commands, and explicit saved fixtures under `freecad-test`.

Record every request and raw response. On any failed atomic mutation, inspect
state directly and do not call undo. On a wrong successful mutation, require the
exact expected history name before undoing once and retrying in the same sketch.

## 1. Repository and Endpoint Baseline

From `freecad-mcp`, capture without modifying:

```powershell
git status --short --branch
git branch --show-current
git rev-parse HEAD
git rev-parse "@{upstream}"
git diff --check
```

Record a recursive file-name/size/hash manifest of tracked and untracked files
in `freecad-mcp` for final comparison. Do not include `.git` object contents in
the byte manifest. Record `freecad-test` status only as fixture context; do not
require it to be clean.

Connect as an external Streamable HTTP MCP client and preserve raw `tools/list`.
Require exactly this order:

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
```

Require the first 28 raw schemas to match the accepted Milestone 18 baseline
byte-for-byte after canonical JSON serialization. Require
`add_sketch_constraints` to retain exactly its 17 discriminated variants.

For each new schema require `additionalProperties: false`, required non-empty
internal `document_name` and `sketch_name`, and a required array with
`minItems: 1`, `maxItems: 100`, `uniqueItems: true`, strict integer items, and
minimum zero. The construction tool must additionally require a Boolean
`construction` property with no default.

## 2. Strict Input Rejection

Against a disposable document/sketch, call each relevant tool with:

- missing index array;
- empty array;
- duplicate indices;
- `true`, `1.0`, and `"1"` as an index;
- a negative index;
- a nonexistent non-negative index;
- whitespace or invalid internal names;
- one unknown property such as `cascade`, `delete_constraints`, or `toggle`.

For construction also send `0`, `1`, `1.0`, `"true"`, and `null` instead of a
Boolean. Require controlled validation errors, deterministic field ordering,
zero history change, and exact before/after `get_sketch`, external-reference,
document, and history equality. No native traceback, object representation,
memory address, transaction ID, or negative native geometry ID may appear.

## 3. Disposable Fixture Layout

Create two unsaved documents, `M19Primary` and `M19Isolation`, each with a Body
and an internal sketch named `Sketch`. In `M19Primary`, also create a source
sketch named `SourceSketch`. Use `add_sketch_geometry` to add controlled lines,
one circle, one bounded arc, and one point in deliberate order. Use
`add_sketch_constraints` to add at least one dimensional constraint, one
geometric constraint, and one geometry-to-geometry constraint. Add a supported
external reference from `SourceSketch` to `Sketch`.

Before every mutation preserve:

- `get_sketch`;
- `analyze_sketch` and `validate_sketch_profile` where topology is relevant;
- `list_external_geometry` and `get_sketch_dependencies`;
- `get_document` and `get_document_history`;
- all open documents and active-document identity;
- the corresponding `M19Isolation/Sketch` state.

## 4. Constraint Removal

1. Remove one dimensional constraint. Require its pre-call index and controlled
   type in `removed_constraints`, the exact remaining count, an old-index-ordered
   survivor mapping, fresh solver readback, unchanged geometry/external state,
   and top history name `Remove sketch constraints`.
2. Undo once with that exact expected name. Require complete restoration and one
   matching redo step. Redo once and require the removal again.
3. Restore the fixture, remove one geometric constraint, and perform the same
   checks.
4. Restore again and remove multiple nonadjacent constraints in an unsorted
   request. Require the response selection and mappings to be canonical and the
   request to create one history step, not one per item.
5. Send a missing index mixed with a valid one. Require complete preflight
   failure and no safe-subset removal.
6. If a named/expression-backed constraint is constructible through existing
   public APIs, require controlled `sketch_constraint_removal_unsafe` with
   `expression_dependency`. If it is not constructible publicly, record this as
   covered by permanent native smoke rather than manufacturing it.

## 5. Construction Desired-State Semantics

Create or restore a closed four-edge profile. Validate it before mutation.

1. Set one normal line to construction. Require exactly that changed index,
   zero unchanged indices, unchanged geometry/constraint counts and constraint
   content, updated construction/normal counts, profile-impact before/after,
   and one `Set sketch geometry construction` history step.
2. Undo and redo once with the exact transaction name and require construction
   and profile participation to follow history.
3. Create a mixed selection containing one already-construction and two normal
   elements, request `true`, and require only the mismatched elements in
   `changed_geometry_indices` and the existing construction member in
   `unchanged_geometry_indices`.
4. Repeat the identical request. Require
   `sketch_geometry_construction_unchanged`, `no_change: true`, identical
   before/after selected summaries, and byte-for-byte unchanged history.
5. Set one construction element back to normal and require the desired final
   state, updated profile participation, and one transaction.
6. Undo a construction change, perform a different successful construction
   mutation, and require redo invalidation.
7. Attempt a number derived from `list_external_geometry` as a geometry index
   only if it is a non-negative collision-free invalid internal index. Require
   rejection. Never send a native negative ID.

## 6. Safe Geometry Removal and Correction Workflow

1. Remove one unused line. Require a controlled removed summary, exact remaining
   count, ordered geometry survivor mapping, constraint survivor mapping, fresh
   solver state, profile impact, preserved external reference, and one `Remove
   sketch geometry` history step.
2. Undo and redo once using the exact transaction name.
3. Restore and remove one unused circle.
4. Restore and remove multiple unused nonadjacent geometry elements from an
   unsorted request. Require descending-safe pre-call semantics and one history
   step.
5. Select geometry used by one constraint. Require
   `sketch_geometry_removal_unsafe`, reason `dependent_constraints`, and exact
   `geometry_index` to `dependent_constraint_indices` impact. Require complete
   batch refusal, no history, and no external or topology mutation.
6. Remove the reported constraint explicitly with
   `remove_sketch_constraints`, then remove the same geometry with
   `remove_sketch_geometry`. Require both corrections to occur in the original
   sketch as two exact history steps, without replacement sketches/documents.
7. Require attachment, Body ownership, placement, source-sketch external
   mapping, saved/unsaved state, and the isolation document to remain unchanged.

## 7. History Mismatch and Same-Sketch Recovery

After each successful operation, call `undo_document` once with a deliberately
wrong expected transaction name. Require a controlled history-mismatch failure
and zero state change. Then call it with the exact top name, inspect the restored
same sketch, and redo where required. After an undo, perform a different
successful mutation and require redo invalidation. Do not create replacement
sketches or documents to correct recoverable intent.

## 8. Saved and Unsaved Documents

Save a separate fixture to a new path under `freecad-test`; record file bytes,
size, timestamp, and document path. Perform each new mutation class without
calling `save_document`. Require the on-disk file metadata and bytes to remain
unchanged while the open document retains its path. Save explicitly, close and
reopen through the supported client workflow if available, and require the
mutation to persist.

For an unsaved document, perform representative successful constraint removal,
geometry removal, and construction change. Require `file_path: null` and
`saved: false` throughout.

## 9. Non-Active Targeting and Cross-Document Isolation

Make `M19Isolation` active by creating or otherwise targeting it through
supported public workflow, then mutate `M19Primary/Sketch` by exact names.
Require the active document to remain `M19Isolation`, and require exact equality
of the same-named isolation sketch before and after every operation. Repeat one
mutation with roles reversed. No result may confuse labels with internal names.

## 10. Read-Only and Leakage Audit

Repeat `get_sketch`, profile validation, external listing, dependency
inspection, document inspection, and history inspection without mutations.
Require zero changes to geometry, constraints, construction, solver freshness,
attachment, Body ownership, placement, external mappings, history, saved state,
active document, selection, or edit mode where observable.

Search every captured result for native object reprs, `0x` memory addresses,
`GeoId`, negative external geometry indices, raw link arrays, arbitrary Python,
or GUI command references. Require none.

## 11. Final Preservation and Report

Repeat the implementation repository status, revisions, `git diff --check`, and
file manifest. Require exact equality with the baseline. Report `freecad-test`
only as disposable fixture state and do not clean it.

The report must include:

1. raw 31-tool order and all three new schemas;
2. canonical comparison proving the first 28 unchanged;
3. the unchanged 17-variant constraint union;
4. strict rejection matrix;
5. constraint removal and remapping evidence;
6. construction mixed/no-op/profile evidence;
7. geometry removal, dependency refusal, and correction workflow;
8. history mismatch, undo/redo, redo invalidation, and same-sketch recovery;
9. saved/unsaved, non-active, and cross-document evidence;
10. external-reference and implementation-repository preservation;
11. no-native-leakage audit;
12. exact ending repository status and confirmation of no install, commit, or
    push.

Retain this deferred non-blocking note: Milestone 18 live broken-source mapping
reporting remains unverified because the public MCP API cannot delete or
invalidate source objects. Revisit it only with a safe disposable fixture or a
later controlled object-deletion capability.
