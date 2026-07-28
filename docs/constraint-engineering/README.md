# Constraint engineering policy

The durable agent-facing constraint-engineering instructions remain in
`.aider-desk/rules/`:

- `FREECAD_ENGINEER.md` defines the operating discipline.
- `freecad-sketch-constraints.yaml` defines the versioned policy.

The policy's JSON Schema is stored in this directory as
`freecad-sketch-constraints.schema.json`. Keeping the schema outside the
automatically loaded rules directory prevents schema implementation detail from
being injected into every agent session while retaining it as a versioned
repository contract.

`tests/constraint_planning/test_policy_files.py` verifies the policy and schema
locations and their core static contracts.
