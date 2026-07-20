# Sketch Reference-Constraint Capabilities

This document is the tested FreeCAD 1.1.1 policy for tool 35,
`add_sketch_reference_constraints`. It is a public allowlist, not a claim about
every native `Sketcher.Constraint` signature.

## Evidence and status vocabulary

The isolated campaign in
`scripts/probe_sketch_reference_constraint_capabilities.py` ran one case per
FreeCAD subprocess. The 126 primary cases plus 18 supplements covered all 17
discriminators, every existing distance/distance-x/distance-y/angle mode,
operand positions and orders, point selectors, representative geometry pairs,
source sketch geometry, object edges and object vertices, undo/redo,
save/reopen, source preservation, and source-change behavior.

The 144 cases produced 122 accepted native constructions, 22 controlled
exceptions, and zero process failures or crashes. The 22 exceptions were the
stale-reference form of every mode and were all `IndexError: Constraint has
invalid indexes`. Native acceptance alone was not treated as support: several
external-only or unary-external constraints did not move target internal
geometry, and several mixed symmetry arrangements produced unstable solver
states.

Statuses used below are:

- `SUPPORTED`: production may construct the exact tested class after complete
  static and semantic preflight.
- `UNSUPPORTED_SAFE`: production refuses before a transaction or native
  constraint call.
- `NATIVE_UNSAFE`: reserved for an isolated case that crashes or corrupts the
  worker process. No such case was observed in this FreeCAD 1.1.1 campaign.
- `NOT_APPLICABLE`: the operand arrangement does not exist for that mode.

Broken, missing, stale, out-of-range, type-incompatible, and invalid-point
references are always `UNSUPPORTED_SAFE` in production. Their isolated native
behavior is not retried in a user's document.

## Public operands

Whole internal geometry:

```json
{"kind": "internal", "geometry_index": 3}
```

Whole external geometry:

```json
{"kind": "external", "external_reference_number": 1}
```

A selected point wraps either geometry reference:

```json
{
  "geometry": {"kind": "external", "external_reference_number": 1},
  "position": "start"
}
```

`kind` is a strict discriminator. Both identities are strict non-negative
integers; Boolean, float, string, negative, missing, and unknown values are
rejected. Every object is closed with `additionalProperties: false`. External
reference numbers are target-sketch-local identities in current list order.
They can change when an earlier external reference is removed and are not
persistent topological names.

Point selector compatibility is:

| Resolved geometry | Supported positions |
| --- | --- |
| line segment | `start`, `end` |
| bounded circular arc | `start`, `end`, `center` |
| circle | `center` |
| point geometry or projected object vertex | `point` |
| whole line/arc/circle target | no point selector; use the geometry operand |

An object edge is governed by its resolved projection. For example, a box edge
normal to the sketch plane can project to a point, while an in-plane edge
projects to a line. Source category does not override the resolved type.

## Complete variant and mode matrix

`I/I` means all geometry operands are internal. `I/E or E/I` means at least one
internal and one external geometry operand; operand order was separately
probed. `E/E` means all geometry operands are external. All `SUPPORTED` entries
remain subject to the point and geometry compatibility tables below.

| Discriminator | Mode | I/I | I/E or E/I | E/E | Public finding |
| --- | --- | --- | --- | --- | --- |
| `horizontal` | whole geometry | SUPPORTED | NOT_APPLICABLE | UNSUPPORTED_SAFE | unary external is read-only/driving |
| `vertical` | whole geometry | SUPPORTED | NOT_APPLICABLE | UNSUPPORTED_SAFE | unary external is read-only/driving |
| `horizontal_points` | point/point | SUPPORTED | SUPPORTED | UNSUPPORTED_SAFE | both mixed orders supported |
| `vertical_points` | point/point | SUPPORTED | SUPPORTED | UNSUPPORTED_SAFE | both mixed orders supported |
| `parallel` | geometry/geometry | SUPPORTED | SUPPORTED | UNSUPPORTED_SAFE | line/line only; both orders supported |
| `perpendicular` | geometry/geometry | SUPPORTED | SUPPORTED | UNSUPPORTED_SAFE | line/line only; both orders supported |
| `equal` | geometry/geometry | SUPPORTED | SUPPORTED | UNSUPPORTED_SAFE | tested compatible pairs only |
| `coincident` | point/point | SUPPORTED | SUPPORTED | UNSUPPORTED_SAFE | actual point identities only |
| `point_on_object` | point/object | SUPPORTED | SUPPORTED | UNSUPPORTED_SAFE | external point/internal target and reverse both supported |
| `symmetric` | points/about | SUPPORTED | CONDITIONAL | UNSUPPORTED_SAFE | see symmetry table |
| `tangent` | geometry/geometry | SUPPORTED | SUPPORTED | UNSUPPORTED_SAFE | tested whole-geometry pairs only |
| `distance` | `line_length` | SUPPORTED | NOT_APPLICABLE | UNSUPPORTED_SAFE | unary external is refused |
| `distance` | `point_to_origin` | SUPPORTED | NOT_APPLICABLE | UNSUPPORTED_SAFE | unary external point is refused |
| `distance` | `between_points` | SUPPORTED | SUPPORTED | UNSUPPORTED_SAFE | positive unsigned value |
| `distance_x` | `point_to_origin` | SUPPORTED | NOT_APPLICABLE | UNSUPPORTED_SAFE | unary external point is refused |
| `distance_x` | `between_points` | SUPPORTED | SUPPORTED | UNSUPPORTED_SAFE | signed value; order retained |
| `distance_y` | `point_to_origin` | SUPPORTED | NOT_APPLICABLE | UNSUPPORTED_SAFE | unary external point is refused |
| `distance_y` | `between_points` | SUPPORTED | SUPPORTED | UNSUPPORTED_SAFE | signed value; order retained |
| `radius` | whole geometry | SUPPORTED | NOT_APPLICABLE | UNSUPPORTED_SAFE | unary external is refused |
| `diameter` | whole geometry | SUPPORTED | NOT_APPLICABLE | UNSUPPORTED_SAFE | unary external is refused |
| `angle` | `line_angle` | SUPPORTED | NOT_APPLICABLE | UNSUPPORTED_SAFE | unary external is refused |
| `angle` | `between_lines` | SUPPORTED | SUPPORTED | UNSUPPORTED_SAFE | both operand orders were probed |

Internal-only use through tool 35 is semantically equivalent to the existing
tool, but `add_sketch_constraints` remains the preferred interface. Its schema,
17 discriminator names, modes, behavior, and result remain unchanged.

## Geometry-pair allowlists

Mixed `parallel`, `perpendicular`, and `angle/between_lines` require two line
segments.

Mixed `equal` supports these ordered resolved-type pairs:

| First | Second | Status |
| --- | --- | --- |
| line segment | line segment | SUPPORTED |
| circle | circle | SUPPORTED |
| circle | circular arc | SUPPORTED |
| circular arc | circle | SUPPORTED |
| circular arc | circular arc | SUPPORTED |
| any other pair | any other pair | UNSUPPORTED_SAFE |

Mixed whole-geometry `tangent` supports every ordered pair formed from line
segment, circle, and circular arc except line/line. Thus line/circle and
circle/line, line/arc and arc/line, circle/circle, circle/arc and arc/circle,
and arc/arc are supported. Line/line and any pair involving a point or an
unsupported projection are `UNSUPPORTED_SAFE`.

For `point_on_object`, the selected point can be internal or external and the
whole target can be an internal or external line segment, circle, or circular
arc. Exactly one operand must provide the point role. A native sketch axis is
also a controlled target for internal-only parity. An object vertex is a point,
not a whole-object target.

## Symmetry policy

Symmetry has three geometry roles and is intentionally conservative:

| First/second points | About reference | Status |
| --- | --- | --- |
| all internal | origin, axis, internal point, or internal line | SUPPORTED internal parity |
| at least one internal point operand | origin | SUPPORTED |
| any mixed set containing internal geometry | internal or external point | SUPPORTED |
| both point operands internal | external line | SUPPORTED |
| mixed point operands | internal or external line | UNSUPPORTED_SAFE: unstable solver status |
| any mixed point operands | horizontal or vertical axis | UNSUPPORTED_SAFE: unstable solver status |
| all geometry operands external | any reference | UNSUPPORTED_SAFE: external-only |

Operand exchange is not assumed. The campaign probed both orders for
non-unary mixed relationships, all heterogeneous tangent orders, and asymmetric
point/object roles. Commutative relationships use a canonical semantic key only
for duplicate detection; their native construction still retains the request's
tested order.

## Coincident and Point-on-Object

Coincident is point-to-point. Both operands must select actual point identities
such as line endpoints, arc endpoints/centres, circle centres, point geometry,
or the controlled sketch origin where that existing mode permits it. A circle
does not expose a circumference endpoint.

Point-on-Object places one selected point on a whole line, arc, or circle. The
canonical circumcircle form is therefore:

```json
{
  "type": "point_on_object",
  "first": {
    "geometry": {"kind": "external", "external_reference_number": 0},
    "position": "start"
  },
  "second": {"kind": "internal", "geometry_index": 0}
}
```

Three external triangle vertices constrained this way solved one internal
circumcircle. Editing a source side endpoint through the Milestone 20 geometry
tool changed the circle centre/radius while retaining one circle, three
constraints, and both external mappings.

The canonical incircle form uses whole-geometry tangent constraints between one
internal circle and each external triangle edge. Three tangencies solved one
internal incircle. Editing a source edge changed the circle while preserving
three constraints, one internal geometry item, and all mappings. A separate
parallel case proved orientation propagation after a controlled source-line
edit. No manual target recalculation or new target geometry/constraint was
needed in any of these scenarios.

## Static preflight, batch, and result behavior

The adapter resolves and validates all 1–100 items before opening a transaction:

- internal and external identities exist in current order;
- the external mapping is resolved, normal, controlled, and not stale;
- point selectors match resolved geometry;
- operand roles and geometry pairs match this allowlist;
- semantic operands are distinct;
- duplicates within the batch and deterministic duplicates against existing
  native fingerprints are absent;
- structurally redundant parallel/perpendicular pairs are absent when both line
  orientations are already fixed by active horizontal/vertical constraints;
- for a freshly fully constrained target, already-satisfied Coincident,
  Point-on-Object on axes/lines/circles, Equal line/radius, and supported
  line/circle or circle/circle tangency relationships are absent.

Coincidental geometry alone is not treated as redundant while the target still
has relevant freedom. For example, two visually parallel unconstrained lines
may validly receive a Parallel constraint. Arc-domain tangency and other cases
without a deterministic structural proof remain solver-verified in the owned
transaction.

No safe subset is applied. Success preserves request order and creates one
`Add sketch reference constraints` transaction. It recomputes and verifies
assigned indices, exact native type/operands/value, external source identity and
ordering, dependency usage, fresh non-conflicting/non-redundant solver state,
sketch context, document identity, and observable GUI state. Caller-owned
transactions remain open. No call saves automatically.

The result contains document/sketch names, exact added indices, normalized
reference-constraint summaries, internal geometry indices, external reference
numbers, final constraint count and solver, dependency summary, complete
controlled sketch summary, and controlled document summary. It contains no raw
constraint objects, LinkSub arrays, transaction internals, memory addresses, or
native negative GeoIds.

### Solver-failure rollback stabilization

The owned-transaction rollback order is significant. The original Milestone
21 implementation deleted appended constraints before calling
`abortTransaction()`. In a live FreeCAD solver-convergence failure that restored
the visible sketch but left a zero-effect `Add sketch reference constraints`
entry on the undo stack. The transaction had not been deliberately committed;
the premature inverse mutations made native abort preserve the named history
record.

Owned addition, recompute, native/dependency/solver verification, and context
verification all occur while the transaction remains open. Only a completely
verified result is committed. On failure, rollback aborts the native transaction
before any inverse mutation. Caller-owned transactions are never committed,
aborted, or internally undone by this tool and continue to receive an exact
inverse inside the caller's still-open transaction.

The focused FreeCAD 1.1.1 capacity probe establishes a committed undo limit of
20. At the limit, the open reference transaction is visible as a temporary 21st
entry; recompute leaves it open, and ordinary abort restores all 20 prior ordered
names. Commit trims back to 20 and evicts the oldest entry. Once such a failed
record has survived into committed/capped history, undo plus redo cleanup cannot
recover the evicted oldest entry. The defensive cleanup therefore handles only
the exact uncapped count-plus-one leak after all non-history checks pass. An
unchanged count with a changed top name remains a hard
`rollback_history_state_mismatch`; the adapter never claims that lost history was
restored. Deterministic redundancy preflight keeps the known parallel case out of
transaction history at empty, 1, 19, and 20-entry depths.

FreeCAD also associates transaction history with the document active when the
transaction opens. An owned call therefore temporarily activates its exact
target document before `openTransaction()` and restores the previous active
document before semantic verification, return, or rollback verification. This
prevents a non-target active document from gaining a linked, zero-effect undo
entry. Caller-owned calls retain the caller's active-document state and do not
perform this switch. Permanent native coverage compares complete forward and
reverse same-named document state, including both history stacks.

The focused reproduction also corrected an acceptance-report claim: a
single-item request is not an unconditional workaround. In the recorded live
fixture the circumcircle failed on the third sequential Point-on-Object request
and the incircle failed on the second sequential tangent request, as well as in
their multi-entry forms. The same exact equilateral fixtures solve successfully
in a fresh headless FreeCAD 1.1.1 process, so this is a process/solver-state
dependent post-native failure rather than a deterministic unsupported operand
class. The static capability allowlist is therefore unchanged. Permanent smoke
coverage injects the observed failure at both sequential boundaries and both
batch boundaries, and a separate naturally conflicting mixed batch proves
zero-history rollback without injection.

`get_sketch` additively represents a supported external operand as:

```json
{
  "kind": "external_geometry",
  "position": "edge",
  "external_reference_number": 0
}
```

Internal-only output is unchanged. Unsupported external projections still use
the established unsupported constraint summary rather than guessing.

## Interaction with Milestones 18–20

- `list_external_geometry` and `get_sketch_dependencies` report exact consuming
  constraint indices.
- `remove_external_geometry` refuses a used reference with those exact indices.
- `remove_sketch_geometry` refuses internal geometry used by a mixed constraint.
- `remove_sketch_constraints` can explicitly remove a supported mixed
  constraint; external identity/order remains unchanged while its expected
  usage entry disappears. The external reference can then be removed.
- `update_sketch_geometry` retains the existing dependency policy for target
  internal geometry. A source sketch can be edited independently and normal
  external propagation updates the constrained target.
- `replace_sketch_constraint` and `update_sketch_constraint_value` retain their
  Milestone 20 schemas and return the existing controlled unsupported refusal
  for mixed constraints.

## Known limits and deferred gaps

- No `NATIVE_UNSAFE` case was observed in the 144 isolated FreeCAD 1.1.1
  workers. This does not authorize unlisted signatures; all unlisted cases are
  refused statically.
- Broken-source reporting remains unverified live because public MCP cannot
  delete or invalidate a source object. Stale native-index forms were verified
  only in isolated workers.
- Public save/reopen acceptance remains incomplete because open/close document
  tools do not exist; native save/reopen is covered by the permanent smoke.
- Active-document identity is not publicly observable.
- Milestone 19 expression-sensitive removal remains deferred.
- Milestone 20 replacement conflict/redundancy remains a live construction gap.
- Constraint names and expressions remain planned for Milestone 22.
- There is no object deletion, document open/close, active-document mutation,
  arbitrary Python, unrestricted generic mutation, GUI simulation, or
  automatic topological repair in this milestone.
