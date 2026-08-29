# Constraint engineering schema

The earlier agent-facing files `FREECAD_ENGINEER.md` and
`freecad-sketch-constraints.yaml` were deliberately removed from
`.aider-desk/rules/`. Durable repository-wide behavior now belongs in
`AGENTS.md`, while domain contracts and evidence belong under `docs/` and in
tests.

`freecad-sketch-constraints.schema.json` is retained as the historical,
versioned shape of that constraint-planning policy. It is not an active agent
rules file and does not imply that the removed YAML policy must exist.

`tests/constraint_planning/test_policy_files.py` verifies only this retained
schema's core static contract.
