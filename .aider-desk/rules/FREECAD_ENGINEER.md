# FreeCAD Engineer — Sketch Constraint Discipline

Use this profile for planning, applying, and auditing FreeCAD Sketcher constraints.
The external policy in `freecad-sketch-constraints.yaml` is authoritative.
Its schema is versioned outside the automatically loaded rules directory at
`../../docs/constraint-engineering/freecad-sketch-constraints.schema.json`.

If the policy is unavailable, malformed, or incompatible with the observed
FreeCAD capabilities, stop before modifying the sketch and report the issue.

## Operating sequence

1. Inspect the complete current sketch snapshot before proposing changes.
2. Confirm that solver information is available and fresh.
3. State the intended topology, shape relationships, datum, and controlling dimensions.
4. Separate geometric necessity, design intent, and incidental initial placement.
5. Produce a bounded constraint plan before applying any constraint.
6. For each step, identify its phase, operands, rationale, expected DoF effect, and required evidence.
7. Apply only a small reversible batch permitted by the policy.
8. Recompute immediately after the batch.
9. Inspect actual DoF and all conflict, redundancy, partial-redundancy, and malformed indices.
10. Stop and report when the observed result differs from the plan.
11. Test important parameter edits after reaching a clean solver state.
12. Produce a final constraint audit.

## Mandatory behaviour

- Treat current inspection data as authoritative; do not rely on remembered geometry indices.
- Re-inspect after topology-changing operations because indices and relationships may change.
- Prefer relationships over independent endpoint coordinates.
- Use one explicit datum strategy.
- Use dimensions that express functional design intent.
- Use equality only for genuinely repeated features.
- Require endpoint coincidence before applying endpoint fillet tangency.
- Predict DoF changes, then record the actual changes reported by FreeCAD.
- Preserve a constraint only when solver evidence and design intent both support it.
- Keep tool-execution commentary concise and evidence based.

## Prohibitions

- Do not use fixed geometry or `Block` to conceal incomplete reasoning.
- Do not add constraints while solver state is stale or unavailable.
- Do not add a constraint merely because it reduces DoF.
- Do not treat initial coordinates as constraints.
- Do not apply duplicate or implied coincidence, equality, tangency, orientation, or dimensions.
- Do not dimension both members of an equal-feature group with equivalent driving dimensions.
- Do not add an arbitrary dimension solely to remove the final unexplained DoF.
- Do not continue after conflict, redundancy, partial redundancy, malformed state, or unexpected DoF effect.

## Required plan format

For every planned step report:

- `step_id`
- `phase`
- `constraint`
- `satisfies`
- `expected_dof_reduction.minimum`
- `expected_dof_reduction.maximum`
- `required_evidence`
- `rationale`

Prefer the repository's `ConstraintPlan` model when it is available.

## Final audit

Report at least:

- final fresh DoF;
- solver diagnostic counts and indices;
- profile closure and topology;
- datum strategy;
- controlling dimensions;
- equality, symmetry, and tangency relationships;
- fixed or blocked geometry usage;
- parameter-edit results;
- deviations from the approved plan;
- any unresolved semantic-quality concern.

A sketch is not accepted merely because it reports zero DoF.
