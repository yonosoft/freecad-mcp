# Milestone 23 Public MCP Acceptance Runbook

Status: prepared, not executed. Run only after the human restarts FreeCAD and
the MCP server from the reviewed Milestone 23 worktree.

## Agent prompt

You are the public MCP acceptance agent for FreeCAD MCP Milestone 23. Test only
the MCP endpoint exposed by the running FreeCAD process. Do not inspect or edit
`freecad-mcp`; do not import project modules; do not call FreeCAD, Sketcher, Qt,
or native Python APIs; do not run arbitrary Python; do not use GUI commands; do
not install dependencies; and do not manually repair failed operations.

You may use only discovered public MCP tools and ordinary read-only filesystem
hash/list operations for a disposable saved acceptance artifact under
`C:\Users\Goran\git\freecad-test`. Do not treat `freecad-test` as implementation
source. Use a fresh unique suffix on every internal document and sketch name.
Never reuse a document from an earlier run.

Record every public request and complete structured response. For each mutation,
capture `get_sketch`, `get_sketch_dependencies`, and `get_document_history`
before and after where applicable. A refusal passes only when the complete
controlled public state and history are unchanged.

## 1. Discovery and schemas

1. Discover the complete tool inventory.
2. Require exactly 42 unique names in authoritative order. Positions 40–42 must
   be `trim_sketch_geometry`, `split_sketch_geometry`, and
   `extend_sketch_geometry`; positions 1–39 must retain their established order.
3. Inspect all three schemas. Require closed top-level request objects, strict
   non-negative integer `geometry_index`, exact two-number point objects with no
   extra fields, and `endpoint` enum `start | end` only.
4. Submit controlled invalid requests: boolean, negative, string, and fractional
   indices; missing point coordinate; non-finite coordinate if the client can
   encode it; extra point/top-level fields; and invalid endpoint. Require
   validation failure before any document access or mutation.

## 2. Supported trim product story

Create `M23ATrim_<suffix>` with sketch `Sketch`. Add, in one ordered request:

```text
0: line (0,0) -> (10,0)
1: line (3,-2) -> (3,2)
2: line (7,-2) -> (7,2)
3: line (20,5) -> (25,5)
```

Add a line-length distance constraint of 5 mm to geometry 3, name it
`OtherSpan`, and bind it to the controlled constant expression `5 mm`. Clear
history if a public tool supports that exact action; otherwise record the full
existing history and reason about one appended topology entry.

Call trim on geometry 0 with pick `(5,0)`. Require:

- success code `sketch_geometry_trimmed` and operation `trim`;
- original geometry 0 maps to ordered results `[0,4]` with outcome `split`;
- original geometries 1–3 map identically in original order;
- geometry 0 is `(0,0)->(3,0)` and geometry 4 is `(7,0)->(10,0)`;
- exactly geometry 4 is created, geometry 0 is modified, and no whole geometry
  is reported removed;
- exactly two Point-on-Object constraints are generated after the existing
  constraint and reported as `native_generation`;
- the pre-existing constraint mapping is unchanged with name/expression/state
  preserved and the readback still reports `OtherSpan` / `5 mm`;
- solver readback is fresh and has no conflict, redundancy, partial redundancy,
  or malformed indices;
- exactly one newest `Trim sketch geometry` history entry;
- no native GeoId, object repr, memory address, filesystem path, or exception
  string in the result.

Undo by exact expected name and require exact pre-trim sketch readback. Redo by
the same name and require exact post-trim readback.

## 3. Supported split product story

Create `M23ASplit_<suffix>` / `Sketch` with line 0 `(0,0)->(10,0)` and unrelated
line 1 `(20,5)->(25,5)`. Add and name a 5 mm line-length constraint on geometry
1. Split geometry 0 at `(4,0)`. Require:

- code `sketch_geometry_split` and operation `split`;
- original geometry 0 maps to ordered `[0,2]` with outcome `split`;
- geometry 0 is `(0,0)->(4,0)` and geometry 2 is `(4,0)->(10,0)`;
- one appended geometry and one generated Coincident joining constraint;
- joining constraint reported under `generated_joining_constraints`, never as a
  transferred old constraint;
- the unrelated named constraint remains identical at its original index;
- exactly one newest `Split sketch geometry` history entry, fresh healthy
  solver, and no automatic save.

Undo and redo with exact names and compare complete readbacks.

## 4. Supported extend product stories

Use two fresh documents. In each, add source line 0 `(0,0)->(10,0)`, make it
construction geometry with `set_sketch_geometry_construction`, and add a second
unrelated constrained line.

1. Extend `start` to `(-3,0)`.
2. Extend `end` to `(15,0)`.

For each require one modified source at index 0, no created/removed geometry or
constraints, preserved orientation/construction/unrelated constraint, complete
identity mappings for all other entities, exact old/new endpoint details, one
newest `Extend sketch geometry` history entry, and successful exact undo/redo.

## 5. No-op and selector refusals

On a fresh `(0,0)->(10,0)` line:

- split at `(0,0)` and `(10,0)`;
- extend end to `(10,0)`.

Require successful `*_unchanged` codes, `changed: false`, identity mappings,
`transaction_committed: false`, and no history/state/modified-file change.

Then require atomic refusals for split at `(5,1)`, split outside at `(11,0)`,
extend end to `(8,0)` (shortening), and extend end to `(12,1)` (non-collinear).
Verify exact safe codes/reasons and unchanged complete state/history.

## 6. Ambiguity, degeneracy, and unsupported geometry

1. Add source `(0,0)->(10,0)` plus two different boundary lines crossing it at
   `(5,0)`. Trim with pick `(2,0)`. Require `ambiguous_intersection` /
   `multiple_boundaries_share_intersection` and two deterministically ordered
   public candidate records.
2. In a separate sketch, add one boundary crossing at `(5,0)` and trim with the
   pick exactly `(5,0)`. Require `degenerate_topology_result` /
   `pick_point_at_intersection`.
3. Attempt all applicable operations on an internal circle. Require
   `unsupported_geometry_type` / `line_segment_required`.
4. Attempt trim with no intersection, an endpoint intersection, and an
   overlapping boundary. Require deterministic refusal and exact atomic state.

## 7. Constraint, name, expression, and dependency policy

Use separate fresh sketches whose source line has:

1. an ordinary source-referencing constraint;
2. a named source-referencing dimension;
3. an expression-bound named source-referencing dimension.

Attempt extend. Require code `constraint_preservation_impossible`, exact affected
index and public summary, and reasons `dependent_constraints`,
`named_constraint`, and `expression_bound_constraint` respectively. Names,
expressions, values, state flags, solver, and history must remain exact.

Create a source sketch and consumer sketch in one document. Add the source line
as consumer external geometry, then attempt to split the source. Require
`external_dependency_would_break` /
`downstream_consumer_topology_unproven`, exact downstream details, and unchanged
source/consumer state. In another target sketch with any external geometry,
attempt trim and require `external_geometry_not_supported` /
`external_trim_boundary_unproven`.

## 8. Capacity 20

Create a fresh split-ready sketch. Produce exactly 20 committed public history
entries using ordinary explicit geometry additions and record the complete
ordered history.

1. Perform a supported split. Require count 20, newest name `Split sketch
   geometry`, the prior newest 19 names in exact order, and only the oldest
   prior entry evicted.
2. In a separate at-capacity document, perform an ambiguity refusal or
   constrained-source refusal. Require the complete 20-entry history and all
   controlled state byte-for-byte equal to the pre-call public readbacks.

## 9. Cross-document isolation

Open two fresh documents with same-named `Sketch` objects. Give the non-target
document at least one committed history entry and record its complete document,
sketch, dependency, and history readbacks. Target the other document with a
supported extend. Require the non-target readbacks and history to remain exact,
the target to receive only one correct entry, and subsequent undo/redo to affect
only the target.

## 10. No-save and explicit persistence boundary

For every unsaved product story, require a null/empty file path after mutation.
For a saved-file case, use only a disposable path beneath
`C:\Users\Goran\git\freecad-test`. Record a SHA-256 hash before a split and
after the split but before explicit `save_document`; require identical bytes.
Then explicitly save and record the complete expected mapping/readback and new
hash.

Stop here and report:

`READY FOR HUMAN-CONTROLLED FREECAD AND MCP SERVER RESTART`

The human may close/restart FreeCAD, open the disposable FCStd, restart the MCP
server, and tell you to continue. Do not perform those GUI actions yourself.
After continuation, rediscover exactly 42 tools and use public inspection only
to require the persisted two split pieces, generated joining constraint, name
and expression policy, healthy solver, and no unrelated entity changes. Delete
or archive disposable acceptance artifacts only if the human explicitly asks.

## 11. Report format

Return a structured report with:

- exact inventory and schema findings;
- every fresh document name;
- product-story request/response summaries;
- complete geometry and constraint mapping verdicts;
- created/removed/modified entity verdicts;
- refusal codes/reasons and atomic-state comparisons;
- undo/redo, capacity-20, cross-document, and no-save results;
- pre/post-restart persistence evidence if that phase was authorized;
- any native-identifier leakage search result;
- exact pass/fail counts and unresolved evidence only.

Do not call Milestone 23 complete, commit, push, or edit either repository.
