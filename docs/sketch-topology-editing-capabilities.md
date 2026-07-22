# Sketch Topology-Editing Capability Contract

This document freezes the Milestone 23 public contract proven against headless
FreeCAD 1.1.1. It does not claim general Sketcher trim, split, or extend parity.

## Public tools and schemas

The authoritative registry appends these exact tools at positions 40–42:

1. `trim_sketch_geometry`
2. `split_sketch_geometry`
3. `extend_sketch_geometry`

All request objects are closed: unknown fields are rejected. Names are exact
internal document and sketch names, `geometry_index` is a strict non-negative
integer, and every point contains exactly finite numeric `x` and `y` fields.

```json
{
  "document_name": "Model",
  "sketch_name": "Sketch",
  "geometry_index": 0,
  "pick_point": {"x": 5.0, "y": 0.0}
}
```

```json
{
  "document_name": "Model",
  "sketch_name": "Sketch",
  "geometry_index": 0,
  "point": {"x": 4.0, "y": 0.0}
}
```

```json
{
  "document_name": "Model",
  "sketch_name": "Sketch",
  "geometry_index": 0,
  "endpoint": "end",
  "target_point": {"x": 15.0, "y": 0.0}
}
```

`endpoint` is exactly `start` or `end`. There is no implicit intersection,
nearest-object, external-target, axis-target, parameter, or selector mode.

## Supported geometry matrix

| Operated geometry | Trim | Split | Extend | Policy |
| --- | --- | --- | --- | --- |
| Internal line segment | Supported | Supported | Supported | Must have no referencing constraint |
| Construction line segment | Supported | Supported | Supported | Construction state is preserved |
| Arc of circle | Refused | Refused | Refused | Native behavior is not exposed initially |
| Circle | Refused | Refused | Refused | Closed/wrap-around semantics are excluded |
| Point | Refused | Refused | Refused | Not a supported topology source |
| Ellipse, arc of ellipse, B-spline, other | Refused | Refused | Refused | No public mapping guarantee |
| External geometry as operated item | Refused | Refused | Refused | Public indices address internal geometry only |

The fixed geometry tolerance is `1e-7` in sketch coordinates. It is used for
on-line projection, endpoint no-op classification, collinearity, coincident
candidate detection, and near-zero result protection.

## Trim contract

The request identifies the portion to remove with one on-source Cartesian pick.
Production computes all finite-segment intersections before opening a
transaction.

Supported boundaries are internal normal or construction line segments. Every
other internal geometry item makes boundary interpretation unsupported, even if
that item is far from the source. The sketch must contain no external geometry;
external trim boundaries are excluded.

One unique interior intersection removes the selected outer portion and leaves
one result at the original index. Two or more ordered intersections remove the
interval surrounding the pick: the original index keeps the lower
source-parameter piece and one appended index receives the upper piece. Only
the nearest strict intersection on each side is used. Orientation is source
parameter order.

Trim refuses before mutation when any of these applies:

- the pick is off the finite source;
- there is no supported intersection;
- a source or boundary endpoint is the intersection;
- the pick is at an intersection;
- two boundaries share one source intersection;
- a boundary is coincident or overlaps the source;
- a removed or resulting piece is at or below tolerance;
- external geometry or an unsupported internal boundary is present;
- the operated source has a constraint or unsafe dependency.

FreeCAD generates one Point-on-Object constraint per retained cut endpoint.
Those constraints are verified from exact native operands and returned as
`native_generation`. Existing constraints are never transferred or removed by
this contract.

## Split contract

The split point must project onto the finite source within tolerance. A strict
interior point produces exactly two ordered results:

- the original index contains source parameter `[0, t]`;
- one appended index contains source parameter `[t, 1]`;
- FreeCAD creates one Coincident constraint joining original end to appended
  start.

The generated constraint is verified and returned as `joining_constraint`.
Points at or within tolerance of either existing endpoint are successful
transaction-free no-ops. Off-line and outside-segment points are refused. The
operation has no implicit projection to another geometry and does not accept a
parameter directly.

## Extend contract

The request chooses the existing `start` or `end` and supplies the complete
desired endpoint. The target must lie on the ray from the opposite endpoint
through the selected endpoint. Production converts the target to FreeCAD's
native positive scalar increment and point-position selector.

The operation modifies the selected endpoint in place, preserves source index
and orientation, and creates no geometry or constraint. A target equal within
tolerance is a successful transaction-free no-op. A target behind the selected
endpoint would shorten the line and is refused. Any perpendicular distance
above tolerance is refused as non-collinear.

## Constraint and dependency policy

Any constraint whose native operands reference the operated source line blocks
all three operations. This is intentionally stricter than FreeCAD's native
behavior because native trim can silently remove dimensions, split can detach
expressions, and extend can make the solver move the unselected endpoint.

Refusal reason precedence is:

1. `expression_bound_constraint` when an affected constraint has an expression;
2. `named_constraint` when an affected constraint has a public name;
3. `dependent_constraints` for every other operated-source constraint.

The refusal returns exact current affected constraint indices, public
constraint summaries, and dependency records. Unrelated constraints—including
names, expressions, values, operands, active/reference/virtual state—must remain
byte-for-byte equivalent at the controlled model boundary.

Broken and cross-document references refuse. A same-document downstream
consumer of the source topology refuses because its post-edit subelement
meaning cannot be proved. Trim additionally refuses any external geometry in
the target sketch. Split and extend preserve unchanged external mappings but do
not use them as selectors or targets.

The solver must provide fresh diagnostics before mutation. Conflicting,
redundant, partially redundant, or malformed pre-call state refuses. Success
must return a fresh healthy readback; a semantic verification failure rolls
back.

## Mapping and result contract

Every success, including no-op, returns one geometry mapping for every pre-call
internal geometry item in original index order and one constraint mapping for
every pre-call constraint in original index order.

Geometry mapping fields are:

- `original_index`;
- `outcome`: `unchanged`, `modified`, or `split` in the current supported domain;
- complete ordered `resulting_indices`;
- `semantic_relationship`;
- `orientation_relationship`.

Constraint mappings contain the resulting indices plus explicit name,
expression, operand-remap, and state-preservation facts. Because operated-source
constraints refuse, every pre-existing constraint in a successful initial
contract is unchanged at the same index. Generated trim/split constraints are
reported separately and never masquerade as transferred pre-existing items.

The result also reports exact created, removed, and modified index lists and
entity summaries; transferred, automatically generated, and joining constraint
views; operation-specific selector details; solver data; profile impact; and
complete current sketch and document readback. Empty removed lists are
meaningful: supported native line stories do not delete a whole pre-call
geometry entity or pre-existing constraint. Native objects, memory addresses,
negative GeoIds, arbitrary exception text, and filesystem internals never cross
the public boundary.

## Transactions, history, and persistence

Owned changes use one exact history label:

| Operation | History name |
| --- | --- |
| Trim | `Trim sketch geometry` |
| Split | `Split sketch geometry` |
| Extend | `Extend sketch geometry` |

All semantic verification and non-target-history isolation complete before
commit. At FreeCAD's observed 20-entry undo capacity, success keeps 20 entries,
places the operation at the newest position, and evicts only the oldest. A
refusal, no-op, native failure, or injected verification failure creates no
entry and preserves the complete prior capacity-20 history.

When a caller transaction is already open, production does not nest, commit,
abort, undo, close, or rename it. Success leaves it open and reports
`transaction_committed: false`. Failure restores the exact operated sketch
state inside the caller transaction while preserving unrelated caller edits and
leaving the transaction open.

Owned calls may temporarily activate a non-active target document before
opening the transaction, then restore the previously active document before
semantic verification. Same-named objects and complete histories in every
other open document remain unchanged.

No topology-editing operation calls save. Unsaved documents remain unsaved and
bytes of an existing FCStd remain unchanged until an explicit `save_document`.
An explicit save persists the verified topology and generated constraints.

## Error taxonomy

Stable public refusal/error codes include:

- `unsupported_geometry_type`;
- `unsupported_trim_boundary`;
- `external_geometry_not_supported`;
- `invalid_point`;
- `no_valid_intersection`;
- `ambiguous_intersection`;
- `degenerate_topology_result`;
- `operation_would_shorten_geometry`;
- `constraint_preservation_impossible`;
- `external_dependency_would_break`;
- `solver_state_unavailable` and `solver_failure`;
- `sketch_geometry_not_found`;
- controlled document/sketch/type/dispatch/rollback failures.

The `reason` and safe details distinguish exact cases. Refusal is not an
invitation for the client to delete constraints or repair native state
implicitly; the caller must explicitly choose a supported model change.

## Verification evidence

- Native discovery: `scripts/probe_sketch_topology_editing.py`
- Permanent production smoke: `scripts/smoke_sketch_topology_editing.py`
- Adapter/domain tests: `tests/test_freecad_sketch_topology_editing.py`
- Handler validation tests: `tests/test_sketch_topology_editing_commands.py`
- MCP schema/delegation tests: `tests/test_mcp_sketch_topology_editing_tools.py`

The public endpoint campaign is prepared in
`docs/codex-milestone-23-acceptance.md`; it is intentionally separate from
direct-adapter verification.
