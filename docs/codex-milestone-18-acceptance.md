# Codex Milestone 18 Live Acceptance Campaign

Status: focused stabilization rerun prepared; Milestone 18 is not accepted.

The initial live campaign found two blockers: SG-03 left a partial second
`sketch_geometry` reference after `rollback_external_state_mismatch`, and
EX-02/FixtureA rejected valid adds with `gui_state_unreadable`. That evidence
must be retained. This document now defines a focused rerun of those failures
and any scenarios that the initial campaign marked inconclusive; passing the
implementation gate alone is not live acceptance.

This is an operator-run campaign against a real FreeCAD 1.1.1 session and live
MCP endpoint. Codex acts as an external MCP client. It must not edit the
repository, addon files, or fixtures; install packages; execute arbitrary
Python; commit; or push. Preserve raw requests, responses, schemas, Report View
output, and controlled before/after snapshots.

## Preconditions and fixture boundary

1. Record `git status --short --branch`, `git rev-parse HEAD`, the configured
   upstream, and its revision. Require the expected clean built revision.
2. Record `App.Version()`, full FreeCAD revision, `sys.version`, MCP SDK version,
   FreeCAD user-data directory, and installed addon target.
3. Before starting the MCP transcript, open operator-provided disposable
   FreeCAD fixtures containing:
   - one ordinary object with stable test edges and vertices plus an empty
     top-level target sketch that satisfies FreeCAD's container rules;
   - one target sketch with an external reference used by a constraint;
   - one deliberately broken external mapping whose source has already been
     deleted;
   - one saved disposable document and one unsaved document.
4. Fixtures must live outside the repository. Record their paths and hashes.
   Fixture preparation is not part of this campaign because the public API has
   no arbitrary object creation or deletion tool. Once the transcript starts,
   inspect and mutate them only through exposed MCP tools.
5. Open Report View, start the MCP server once, and preserve every `[MCP]`
   record produced by the campaign.

## Inventory and compatibility gate

Preserve raw `tools/list`. Require exactly 28 names in authoritative order:

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
```

Diff the first 24 raw names and complete schemas against pinned Milestone 17
evidence and require no change. Preserve `add_sketch_constraints` and require
exactly its existing 17 discriminated variants.

## Raw schema acceptance

Preserve all four new schemas. Require `additionalProperties: false` at every
new top-level argument object. `source` must be a discriminated `oneOf` with
exactly these shapes:

```json
{
  "document_name": "Model",
  "sketch_name": "TargetSketch",
  "source": {
    "type": "object_subelement",
    "object_name": "Pad",
    "subelement": "Edge3"
  }
}
```

```json
{
  "document_name": "Model",
  "sketch_name": "TargetSketch",
  "source": {
    "type": "sketch_geometry",
    "sketch_name": "SourceSketch",
    "geometry_index": 4
  }
}
```

Require exact non-empty internal names. Require canonical positive `EdgeN` or
`VertexN`; reject lowercase, zero, signed, path-chain, and whole-object forms.
Require `geometry_index` and `external_reference_number` to be non-negative
strict integers; reject Boolean, float, string, and negative values. Reject the
target sketch as its own source. Reject extra source fields, extra top-level
fields, unknown discriminator values, raw objects, native geometry IDs,
document-qualified source strings, cascade flags, repair flags, GUI flags, and
save flags.

`list_external_geometry` and `get_sketch_dependencies` accept exactly
`document_name` and `sketch_name`. `remove_external_geometry` additionally
requires exactly one `external_reference_number`.

## Preservation snapshot protocol

Before and after every success and expected failure, preserve:

- full `list_external_geometry` and `get_sketch_dependencies` results;
- full `get_sketch`, including internal geometry, construction flags,
  constraints, cached solver state/freshness, Body ownership, attachment,
  MapMode, attachment offset, and placement;
- `get_document`, active document, visibility, selection, and edit mode;
- full `get_document_history`, undo/redo counts and names, and pending status;
- file path and modified state; for saved fixtures, external bytes, size, hash,
  and timestamp.

Read-only calls must preserve every field and must not recompute, solve,
transact, create history, save, activate, enter edit mode, or change selection.
Expected preflight failures must also produce zero mutation and no history.
Successful mutation may change only the documented external-reference state,
fresh recomputed sketch facts, modified state, and one controlled history entry.

## Edge, vertex, and source-sketch creation

On the prepared ordinary-object fixture:

1. Add one known edge. Require `external_geometry_added`, reference number zero,
   category `object_edge`, normal mode, resolved controlled source identity,
   sanitized geometry, and no negative native value.
2. Add one known vertex. Require reference number one, category
   `object_vertex`, controlled point readback, and deterministic ordering.
3. Repeat the exact edge request. Require `external_geometry_already_exists`,
   its current controlled reference number, byte-for-byte controlled state
   equality, and no new history.

In a clean document, create `SourceSketch` and `TargetSketch` through MCP, add a
supported line to the source, and add source geometry index zero to the target.
Require category `sketch_geometry`, source document/sketch internal name and
label, zero-based source geometry index, and projection update after changing
the source through a controlled mutation and recomputing.

Attempt unsupported source categories and missing edges/vertices/indices.
Require controlled source errors and zero mutation. Do not claim point,
B-spline, intersection, carbon-copy, or whole-object support.

## Controlled listing and dependencies

Repeat `list_external_geometry` and require stable order and complete equality.
Every public number must be non-negative and contiguous in current order.
Require source labels, categories, modes, resolved states, controlled geometry,
and constraint-use arrays. Verify that later numbers are treated as current
order, not persistent IDs.

Exercise `get_sketch_dependencies` on prepared fixtures with each reliably
supported category. Require controlled arrays for:

- external geometry sources;
- attachment sources;
- expression sources and their parsed simple object sources;
- constraints using external references;
- downstream consumers;
- broken or unresolved references;
- observed cross-document relationships.

Require deterministic ordering and no native objects, raw link arrays, memory
addresses, arbitrary properties, tracebacks, exception text, or negative native
indices. On the pre-broken fixture, require an unresolved entry and a controlled
reason. If native mapping loss makes attribution ambiguous, require source
`null` and `source_mapping_incomplete`; do not accept guessed source identity.

## Safe removal and refusal

On an unused-reference fixture, call `get_sketch_dependencies`, then remove the
selected number. Require `external_geometry_removed`, the removed controlled
identity, explicit impact with no dependent constraints and no cascade, exact
remaining mappings, and one `Remove sketch external geometry` history step.
Re-list and use only the newly returned numbers afterward.

On the prepared constraint-used reference, request removal. Require
`external_geometry_removal_unsafe`, reason `dependent_constraints`, exact
controlled constraint indices, unchanged reference and constraint state, and no
history entry. Repeat refusal for broken/unresolved and otherwise unsupported
references where fixtures permit. There is no cascade option; dependent
constraints must remain present.

## History, mismatch, recovery, and redo invalidation

For a successful add, require exactly one top `Add sketch external geometry`
transaction. Call `undo_document` first with a deliberately wrong expected
name; require a controlled mismatch and zero mutation. Then undo with the exact
name, proving the reference disappears, and redo with the exact name, proving
the same controlled mapping returns.

Perform the corresponding exact-name undo/redo cycle for one successful remove
using `Remove sketch external geometry`.

For same-sketch correction:

1. add a deliberately wrong but valid reference;
2. inspect it;
3. undo with exact expected name;
4. add the intended reference to the same sketch;
5. require the target sketch identity unchanged and redo count zero.

Do not create a replacement sketch. Do not call undo after an atomic expected
failure whose own operation produced zero mutation.

## Documents, saved state, and cross-document policy

Make document B active and target a named sketch in document A. Require B to
remain active and unchanged. Repeat with same-named sketches and source objects
in A and B; require exact named-document isolation.

Attempt to add in B using a source name that exists only in A. Require
`external_geometry_source_invalid` with same-document source-not-found policy
and zero change in both documents. If a prepared document already contains an
observed cross-document reference, require dependency inspection to report it
as outside the supported boundary; do not mutate it or claim stability.

On an unsaved document, perform representative add/list/remove operations and
require the file path to remain null. On the saved fixture, hash the file before
an add and require bytes, size, hash, timestamp, and path unchanged afterward.
Only an explicit `save_document` may write the mutation. Reopen the disposable
file outside the transcript after that explicit save and require valid mapping
persistence.

## Tool-selection product prompts

Submit these natural-language intents and preserve the chosen primary tool:

```text
Show me every projected reference in this sketch and what it came from.
-> list_external_geometry

What depends on this sketch, and is reference 1 safe to remove?
-> get_sketch_dependencies before any remove

Project Edge3 from Pad into TargetSketch.
-> add_external_geometry

Remove the unused projected reference numbered 0.
-> get_sketch_dependencies, then remove_external_geometry

Show the complete internal sketch geometry and constraints.
-> get_sketch

Check whether the sketch is a closed profile.
-> validate_sketch_profile
```

Require no MCP-to-MCP delegation inside one public operation and no GUI command
simulation. Tool selection may use more than one explicit client call where the
intent genuinely requires inspection before mutation.

## Failure and final audit

Exercise nonexistent document, nonexistent sketch, wrong object type, strict
schema failures, duplicate add, missing source, missing reference number,
unsafe removal, expected history-name mismatch, and cross-document source
isolation. Preserve stable machine codes and controlled context without raw
exceptions.

Finish by preserving:

1. raw 28-tool inventory, all four new schemas, unchanged first-24 diff, and
   unchanged 17-variant constraint evidence;
2. all raw requests and structured success/expected-failure responses;
3. mapping, dependency, history, recovery, saved/unsaved, non-active,
   cross-document, GUI preservation, and Report View evidence;
4. starting and ending fixture hashes where applicable;
5. ending `git status --short --branch` and `git rev-parse HEAD` exactly equal
   to the starting repository evidence.

Stop MCP cleanly and identify disposable documents/files for operator cleanup.
Report explicitly that this prepared campaign did not edit the repository,
install dependencies, execute arbitrary Python, commit, or push.

## Focused stabilization rerun

Run this section first against the stabilized build. Preserve the same raw MCP,
Report View, repository, fixture, and before/after evidence required above.

1. Recreate SG-03 with one source sketch containing a supported line at geometry
   index 0 and a supported circle at geometry index 1, plus one empty target
   sketch. Add index 0 and require controlled reference 0 with exact source
   index 0 and line readback. Add index 1 and require controlled reference 1
   with exact source index 1 and circle readback. Require no negative native IDs.
2. Repeat each exact add independently and require
   `external_geometry_already_exists`, the correct current reference number,
   byte-for-byte controlled state equality, and no history entry.
3. For every failed add available through the public campaign, compare the full
   preservation snapshot. Require no added reference, no partial mapping, no
   history entry, and no caller undo. The injected postcondition-failure branch
   is covered by the permanent native smoke and is not fabricated through the
   live MCP endpoint.
4. Recreate EX-02 with FixtureA or an equivalent nontrivial tree containing
   multiple sketches in one Body and a constrained rectangle. Test while a
   target is in an otherwise preserved GUI edit context. Require valid adds to
   succeed, selection and edit identity to remain unchanged when readable, and
   no document activation or GUI command invocation.
5. Repeat the complex-document add in a runtime/context where an optional
   selection or edit-state observation is unavailable, if the original
   environment can reproduce that condition. Require the safe model operation
   not to fail solely because that optional field is unreadable. Preserve the
   field-level controlled diagnostics; do not accept the former aggregate
   `gui_state_unreadable` blocker.
6. Rerun every scenario explicitly marked inconclusive in the initial campaign,
   using its original fixture and request. Record each as pass, controlled
   expected refusal, or still inconclusive with the exact reason; do not infer a
   pass from the two blocker fixes.
7. Only after these focused checks pass, complete the remaining applicable
   sections of this campaign and issue a new acceptance decision. Until that
   external rerun is recorded, report Milestone 18 as prepared, not accepted.
