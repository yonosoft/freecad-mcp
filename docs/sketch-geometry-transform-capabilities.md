# Sketch Geometry-Transform Capabilities

Milestone 24 adds six dedicated, bounded, copy-only sketch tools at registry
positions 43–48:

1. `mirror_sketch_geometry`
2. `translate_sketch_geometry`
3. `rotate_sketch_geometry`
4. `scale_sketch_geometry`
5. `rectangular_array_sketch_geometry`
6. `polar_array_sketch_geometry`

The authoritative registry contains 48 tools. The first 42 are unchanged.
These operations do not enter edit mode, call GUI commands, save, move source
geometry, or expose a generic native/Python escape hatch.

## Evidence and contract decision

Isolated FreeCAD 1.1 probes established the native methods
`addCopy(indices, vector, clone=False)`, `addMove(indices, vector)`, and
`addRectangularArray(indices, vector, clone, rows, cols,
constrain_displacement=False, perpendicular_scale=1.0)`. FreeCAD has no
corresponding SketchObject mirror, rotate, uniform-scale, or polar-array method.

The native copy method duplicated attached constraints and could duplicate a
constraint name. Its clone mode could replace a copied dimensional constraint
with `Equal`. Mixed-family native move did not provide exact semantic undo for
all tested bounded-arc cases, and the native rectangular-array method did not
return a complete source-to-created mapping. Those behaviours do not satisfy
the public preservation contract.

Production therefore uses one controlled affine-copy engine. It reconstructs
only proven geometry families through `addGeometry`, retains every original,
copies no constraints, and verifies the complete result before commit. There is
no move mode and no separate generic copy tool. Independent copying is the
fixed semantic of all six tools.

## Supported matrix

| Source geometry | Mirror | Translate | Rotate | Uniform scale | Rectangular array | Polar array |
| --- | --- | --- | --- | --- | --- | --- |
| Internal line segment | Yes | Yes | Yes | Yes | Yes | Yes |
| Internal point | Yes | Yes | Yes | Yes, unless invariant | Yes | Yes |
| Internal circle | Yes | Yes | Yes | Yes | Yes | Yes |
| Internal bounded circular arc | Yes | Yes | Yes | Yes | Yes | Yes |
| Construction form of a supported family | Yes | Yes | Yes | Yes | Yes | Yes |
| External geometry | Read-only, not selectable | Read-only, not selectable | Read-only, not selectable | Read-only, not selectable | Read-only, not selectable | Read-only, not selectable |
| Other internal curve families | Refused | Refused | Refused | Refused | Refused | Refused |

Construction state is copied exactly. A reflection reverses line or arc
orientation where applicable; circle and point orientation is reported as
`not_applicable`. Rotation, translation, positive uniform scaling, and the two
arrays preserve orientation.

## Requests

Every request requires exact internal `document_name` and `sketch_name` values
and a non-empty `geometry_indices` list. Indices are strict integers:
booleans, negatives, fractions, duplicates, and more than 50 entries are
rejected. The validated selection is sorted into canonical ascending order.
All coordinates, vectors, angles, and factors must be finite strict numbers;
extra fields are rejected.

Mirror has one discriminated `reference`:

```json
{"kind": "horizontal_axis"}
{"kind": "vertical_axis"}
{"kind": "origin"}
{"kind": "construction_line", "geometry_index": 5}
{"kind": "internal_point", "geometry_index": 8}
```

An internal reference must be the exact required geometry family, must be
internal, and must not be selected. External references are intentionally
deferred. Geometry invariant under the reference is refused because creating an
overlapping independent copy is ambiguous.

Translation uses a finite sketch-local `displacement: {x, y}`. The zero vector
within the fixed `1e-7` sketch-unit tolerance is refused. Rotation uses a finite
sketch-local `center` and signed `angle_degrees`; angles are normalized for
planning, and zero/full-turn or geometry-invariant results are refused. Scaling
is uniform about a finite `center`; `factor` must be positive and at least
`1e-6`. Factor one and selected items invariant about the scale centre are
refused. Negative, zero, near-zero, and non-uniform scaling are unsupported.

Rectangular arrays use `rows`, `columns`, `row_displacement`, and
`column_displacement`:

- each axis count is a strict integer from 1 through 20;
- `rows * columns` may not exceed 100;
- `(rows * columns - 1) * selection_count` may not exceed 500;
- the source is instance zero and is not recopied;
- generated copies are appended by row-major instance, then canonical source
  index;
- a displacement required by a count greater than one must be non-zero;
- coincident offsets from dependent/collinear vectors are refused;
- exactly 1×1 is a transaction-free no-op.

Polar arrays use `center`, `instance_count`, and signed
`step_angle_degrees`:

- count is a strict integer from 2 through 100;
- `(instance_count - 1) * selection_count` may not exceed 500;
- the source is instance zero and is not recopied;
- generated copies are appended by ascending instance, then canonical source
  index;
- any modulo-360 duplicate, including a generated full turn, is refused;
- an instance that reproduces a selected geometry locus is refused.

## Constraints, names, expressions, and dependencies

Copying a selected source with any dependent constraint is refused before a
transaction opens. Reason precedence is `expression_bound_constraint`, then
`named_constraint`, then `dependent_constraints`. The response provides the
affected current constraint indices, controlled constraint summaries, and
operand-dependency evidence. This prevents silently omitted or duplicated
constraints and prevents duplicate constraint names or broken expression
references.

Unrelated constraints retain exact native order, operands, active/reference/
virtual state, names, expressions, and evaluated values. Existing external
geometry mappings are read-only and must remain byte-for-byte equivalent in the
controlled snapshot. Broken references, cross-document references, and any
downstream consumer of the target sketch cause conservative refusal. Copying
never redirects an existing consumer.

## Results and mappings

Every success result is controlled data. `mode` is always `copy`. It includes:

- `changed`, `no_change`, the exact `transaction_name`, and whether this call
  committed it;
- `selected_geometry_indices` in canonical order;
- one original-order `geometry_mappings` record for every pre-call internal
  geometry item; `resulting_indices` contains the retained original first and
  every copy after it, while `copied_indices` repeats the copy-only subset;
- one original-order identity `constraint_mappings` record for every pre-call
  constraint, including name/expression preservation facts;
- ordered `created_geometry` and `copied_geometry` records with source index,
  instance index, orientation relationship, construction state, and controlled
  geometry readback;
- empty `modified_geometry`, `replaced_geometry`, `removed_geometry`,
  `created_constraints`, and `generated_constraints` collections;
- per-instance source/created index provenance and controlled transform
  parameters;
- before/after profile impact, fresh solver readback, complete sketch readback,
  and document summary.

Indices are current sketch-order identifiers, not persistent topology IDs. No
Python repr, memory address, native pointer, GeoId, or object handle is returned.

## Transactions, rollback, and history

Owned mutations use exactly one of these labels:

- `Mirror sketch geometry`
- `Translate sketch geometry`
- `Rotate sketch geometry`
- `Scale sketch geometry`
- `Rectangular array sketch geometry`
- `Polar array sketch geometry`

The adapter captures the existing complete mutation snapshot and all open
document histories, activates a non-active target before opening its
transaction, appends in deterministic order, recomputes, performs controlled
readback, verifies every original and created entity plus constraint,
construction, expression, external, dependency, solver, GUI/context, document,
and history state, restores the previous active document, then commits. At the
native 20-entry undo capacity a successful commit may evict only the oldest
entry.

Refusals and the rectangular 1×1 no-op open no transaction. An owned partial or
verification failure aborts before commit and proves exact same-object rollback.
Inside a caller-owned transaction, the adapter neither opens, commits, aborts,
undoes, nor closes that transaction; on failure it restores only its partial
work and verifies the caller's prior in-transaction state and history. Target
and non-target histories are isolated. No transform calls `save` or `saveAs`;
only a later explicit save persists a successful result.

## Error taxonomy

Strict input failures return `validation_error`. Missing indices return
`sketch_geometry_not_found`. Evidence-bounded preflight refusals return
`sketch_geometry_transform_unsafe` plus stable `operation`, `reason`, and
controlled details. Expected reasons include unsupported geometry, dependent/
named/expression-bound constraints, invalid or selected mirror references,
overlapping copies, zero/duplicate array offsets, duplicate polar instances,
broken/cross-document dependencies, and downstream-consumer risk.

A native mutation/readback/verification failure returns
`native_sketch_transform_failed`. An inability to prove exact recovery returns
`sketch_mutation_rollback_failed`. Transport dispatch or document-access
failures use the existing controlled errors. Raw exception text, native objects,
and internal identifiers are not exposed.

## Deferred capabilities

Move/replace modes, independent constraint copying, native clone semantics,
non-uniform or negative scaling, external mirror references, arbitrary affine
matrices, and unsupported curve families are outside this milestone.
Whole-sketch mirroring or copying, cross-sketch copying, destination-sketch
creation, and merging remain deferred to Milestone 28.

Native research is reproducible with
`scripts/probe_sketch_geometry_transforms.py`. The permanent real-adapter
campaign is `scripts/smoke_sketch_geometry_transforms.py`.
