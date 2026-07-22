# Milestone 24 Public MCP Acceptance

This campaign is for a separate AiderDesk agent after a human has restarted
FreeCAD and the MCP server. It must exercise only the public MCP endpoint. It is
not part of local implementation verification and must not be run by the
implementation agent.

The campaign deliberately has two phases. Phase A creates and explicitly saves
one persistence artifact, then pauses for a human-controlled FreeCAD/MCP
restart. Phase B reconnects, proves persisted geometry through public
inspection, cleans up only open disposable acceptance documents when possible,
and reports the final verdict.

## Exact acceptance prompt

Copy the following prompt verbatim into the separate acceptance agent:

```text
Perform the complete FreeCAD MCP Milestone 24 public acceptance campaign.

Authority and hard boundaries:
- Use only the public FreeCAD MCP tools exposed by the running server.
- Do not import freecad_mcp or any repository module.
- Do not call FreeCAD, FreeCADGui, Part, Sketcher, a console, shell, subprocess, or arbitrary Python.
- Do not use GUI commands, edit mode, screenshots as primary evidence, or hidden/private MCP methods.
- Do not edit C:\Users\Goran\git\freecad-mcp or install anything.
- Do not inspect implementation source or tests. Treat public tool schemas and public responses as the API.
- Do not manually repair a failed atomic call. Reinspect; a failed/refused call must already have preserved exact state and history.
- Work only in disposable acceptance documents with names beginning M24Acceptance. The only filesystem artifact you may create is C:\Users\Goran\git\freecad-test\M24AcceptancePersistence.FCStd through the public save_document tool.
- Never overwrite any other file. Do not commit or push.

Start by listing the public tools and schemas. Require exactly 48 tools in the authoritative order, with positions 43–48 exactly:
43 mirror_sketch_geometry
44 translate_sketch_geometry
45 rotate_sketch_geometry
46 scale_sketch_geometry
47 rectangular_array_sketch_geometry
48 polar_array_sketch_geometry
Confirm each of the six schemas rejects extra fields, uses strict current internal geometry indices, and exposes no generic operation/matrix, move Boolean, native object, or Python escape hatch. Record the documented selection and array bounds.

Maintain an evidence ledger for every call: tool, request, ok/code, key counts, selected/result indices, mappings, transaction name, history before/after, document modified/file state, and whether the state was expected to change. After every mutation or refusal, use public inspection tools rather than assumptions.

Core product document:
1. Create M24AcceptanceTransforms, one body, and one sketch named Sketch.
2. In one public add_sketch_geometry call add, in this exact order:
   - normal line segment from (1,2) to (5,4);
   - construction point at (-2,3);
   - normal circle centered at (4,-2), radius 2;
   - normal bounded arc centered at (-4,-3), radius 3, start 20 degrees, end 140 degrees;
   - construction line from (10,-5) to (13,1);
   - construction point at (7,-4).
3. Inspect and freeze the complete six-item geometry, zero constraints, construction flags, solver, dependency, document modified/file state, and history.

Use only original source indices [0,1,2,3]. Exercise every mirror reference in this order and verify four appended copies each time:
- horizontal_axis -> expected created indices [6,7,8,9]
- vertical_axis -> [10,11,12,13]
- origin -> [14,15,16,17]
- construction_line geometry_index 4 -> [18,19,20,21]
- internal_point geometry_index 5 -> [22,23,24,25]

For each mirror result require:
- mode=copy; originals unchanged at indices 0–5;
- complete original-order geometry_mappings for every pre-call internal item;
- complete identity constraint_mappings (empty here);
- ordered created_geometry and copied_geometry with exact source_geometry_index and instance_index provenance;
- empty modified/replaced/removed geometry and empty created/generated/removed constraints;
- correct construction copy for source point 1;
- line/arc reflection orientation relationship and controlled geometry readback;
- fresh solver, profile impact, exact transaction label Mirror sketch geometry, one new history step, modified document, and no automatic save/path change;
- no Python repr, memory address, native pointer, negative GeoId, or unstable native identifier anywhere in success or inspection data.

Continue in the same sketch, always copying originals [0,1,2,3]:
- translate by displacement (7,-3), expect [26,27,28,29] and Translate sketch geometry;
- rotate about (2,-1) by signed 37 degrees, expect [30,31,32,33] and Rotate sketch geometry;
- uniformly scale about (2,-1) by factor 1.75, expect [34,35,36,37] and Scale sketch geometry.
Verify the same complete mapping/preservation/provenance rules, correct radius scaling, signed-degree geometry, exact labels, and no save.

Exercise arrays from original sources [0,2]:
- rectangular: rows=2, columns=2, row displacement (0,11), column displacement (13,0). It is source-inclusive, so require six copies at [38,39,40,41,42,43], instance indices [1,2,3], and ordering by row-major instance then canonical source order. Require transaction Rectangular array sketch geometry.
- polar: center (0,0), instance_count=3, step_angle_degrees=45. It is source-inclusive, so require four copies at [44,45,46,47], instance indices [1,2], and ordering by ascending instance then canonical source order. Require transaction Polar array sketch geometry.
Verify the final sketch has exactly 48 internal geometry items and still zero constraints.

Undo/redo:
- Inspect history and require Polar array sketch geometry on top.
- Undo exactly that named transaction and verify geometry count 44, all original state/mappings unchanged, and the exact redo entry.
- Redo exactly that named transaction and verify geometry count 48 and the same polar geometry/provenance outcome through inspection.

Strict validation and zero-mutation matrix:
For each invalid request, snapshot complete sketch, dependencies, document modified/file state, and full history before the call; require a controlled validation_error, no mutation, and identical history afterward. Cover extra fields; empty selection; duplicate indices; Boolean, negative, and fractional indices; a selection of 51 indices; non-finite coordinate/vector/angle/factor; string numerics; mirror discriminator/reference extras; scale 0, negative, and below 1e-6; rectangular Boolean/zero/21 axis counts, over 100 instances, and over 500 generated items; polar count 1/101 and over 500 generated items. Never send a request likely to crash the host.

No-op and ambiguity/refusal matrix:
- In a fresh M24AcceptanceNoOp document with a constrained source, call a rectangular 1x1 array with zero vectors. Require changed=false, no_change=true, transaction_committed=false, complete unchanged mappings, no history entry, and exact model/dependency/modified/file state.
- In disposable fresh sketches require sketch_geometry_transform_unsafe and exact zero mutation/history for: zero translation; zero and full-turn rotation; nonzero rotation of a point or circle invariant about its centre; factor-one scale; geometry invariant under a mirror reference; selected construction-line reference; wrong reference family; zero required row/column vector; duplicate rectangular offsets; a polar step/count that generates a full-turn duplicate; and a polar point/circle invariant about its centre.
- Require unsupported operated geometry to refuse if a public supported primitive can create such a family; otherwise record that unsupported families are unconstructible through the public API and do not invent one.

Constraint, name, expression, construction, and dependency policy:
1. Create M24AcceptancePreservation with two independent lines. Add a driving dimensional constraint only to line 1, name it OtherSpan, bind it to the finite expression 5 mm, and snapshot all controlled state.
2. Translate only unconstrained line 0. Require success while line 1, its constraint index/type/operands/state/name/expression/evaluated value, construction, solver, dependency data, and original indices remain exact.
3. Attempt to transform constrained line 1. Require sketch_geometry_transform_unsafe with reason expression_bound_constraint, exact affected constraint evidence, zero mutation, and unchanged history.
4. In separate documents repeat selected-source refusals for a named but unbound constraint (named_constraint) and an unnamed constraint (dependent_constraints).
5. Create a source sketch and a target sketch with one controlled external reference to the source. Transform an unconstrained internal item in the target and prove its external mapping remains exact and read-only.
6. Then attempt to transform the externally consumed source item. Require downstream_consumer_topology_unproven, exact public consumer evidence, zero mutation, and unchanged source/consumer histories. Do not try to select external geometry or use it as a mirror reference.

Atomic failure and history-capacity campaign:
- Build M24AcceptanceCapacity with one unconstrained point source. Use successful non-overlapping transforms of that original until public history reaches the native 20-entry capacity. Record the complete ordered history.
- Perform one more successful transform. Require count remains 20, the new exact transform label is first, entries 2–20 equal the prior entries 1–19, and only the oldest was evicted.
- At capacity, issue a preflight refusal using the constrained/ambiguous policy. Require the entire 20-entry history and model remain exact.
- At capacity, issue a request whose selection contains one valid source and one nonexistent index. Require controlled failure before mutation and exact model/history preservation.
- These public cases establish atomic preflight/refusal behavior. If no safe public input can deterministically inject a post-mutation native failure, state that exact partial-failure rollback is native-smoke evidence and do not use GUI/native/Python techniques to manufacture one.

Cross-document isolation:
- Keep M24AcceptanceOther open with its own known successful history and complete state.
- Mutate a different non-active M24AcceptanceTarget sketch through one transform.
- Verify only target model/history changed; Other model, history, modified/file state, and dependencies stayed exact. Verify no document was automatically saved.

Persistence phase A:
- Create M24AcceptancePersistence with one body, Sketch, and one original line.
- Save only through save_document to C:\Users\Goran\git\freecad-test\M24AcceptancePersistence.FCStd with overwrite=false. Require a clean saved document state and exact path.
- Translate the line by (9,4). Verify two geometry items, original unchanged, complete copy mapping, modified=true, same path, and that the file was not automatically saved.
- Explicitly save through save_document. Reinspect the exact two-item geometry and clean saved state.
- Stop and report the phase-A ledger plus exactly: PAUSED FOR HUMAN-CONTROLLED FREECAD AND MCP SERVER RESTART FOR PERSISTENCE CHECK
- Do not stop/start the server or close/reopen FreeCAD yourself.

Persistence phase B, only after the human says restart is complete:
- Reconnect using only public MCP tools.
- Locate the reopened M24AcceptancePersistence document by exact internal identity. If the normal human restart did not reopen the saved document, ask the human to open the exact FCStd file in FreeCAD; do not use GUI, native APIs, shell, or arbitrary Python yourself.
- Inspect Sketch and require the saved two-item original/copy geometry, construction, zero constraints, solver, file path, and clean modified state. This proves explicit-save/restart persistence and no pre-save auto-save.
- Reconfirm exactly 48 tools and the six-tool tail after restart.

Final report:
- Give PASS/FAIL per section and an overall PASS only if every applicable assertion passed.
- Include exact tool inventory/tail, success/error codes, transaction labels, geometry and constraint mappings, instance ordering, history transitions, capacity evidence, state-preservation evidence, isolation evidence, save/restart evidence, and leakage audit.
- Distinguish public preflight atomicity from native-smoke-only injected rollback evidence.
- List any untestable public-only case explicitly; do not silently mark it passed.
- Do not modify implementation files, install, manually repair, commit, or push.
- Do not claim Milestone 24 closed; report only public MCP acceptance.
```
