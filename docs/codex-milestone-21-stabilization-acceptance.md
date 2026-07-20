# Milestone 21 Focused Stabilization Acceptance

Run this only as an external client against the local Streamable HTTP MCP
endpoint after the rollback stabilization is loaded. Do not import project
modules, call FreeCAD internals, use GUI commands, edit either repository,
install dependencies, or commit/push. Use unique unsaved document and object
names. Preserve every raw request and response.

Before each expected failure capture `get_document`, `get_sketch`,
`get_document_history`, `list_external_geometry`, and
`get_sketch_dependencies`. After failure repeat all five calls without calling
undo. Require exact semantic equality, including undo/redo counts and names,
modified/saved state, external order, and dependency consumers. No failed call
may leave `Add sketch reference constraints` as an undoable transaction.

Execute these focused scenarios:

1. Create a centred equilateral-triangle source and one-circle target. Add all
   three distinct external-vertex Point-on-Object constraints in one request,
   then repeat on a fresh target one per request. Accept either a healthy
   three-constraint circumcircle or a controlled failure with exact automatic
   rollback; never perform recovery undo.
2. Create an equivalent triangle and one-circle target. Add all three
   circle/external-side tangencies in one request, then sequentially on a fresh
   target. Apply the same success-or-exact-rollback rule.
3. On a fresh line fixture request mixed parallel and perpendicular constraints
   on the same pair in one batch. Require controlled solver failure, exact zero
   model/history change, and no caller undo.
4. Create a healthy mixed parallel or perpendicular relationship, edit the
   source line through `update_sketch_geometry`, recompute, and require target
   propagation with stable mapping and dependency indices.
5. While that external reference is consumed, require
   `remove_external_geometry` refusal with zero mutation.
6. While its internal operand is consumed, require `remove_sketch_geometry`
   refusal with zero mutation.
7. Explicitly remove the mixed constraint. Require preserved external ordering
   and cleared dependency use, then remove the unused external reference.
8. On a successful mixed addition, require wrong-name undo refusal, exact-name
   undo, and exact redo.
9. Undo again, perform a different valid mutation, and require redo
   invalidation.
10. Create same-named target sketches in two documents. Mutate each in forward
    and reverse order by exact document/sketch name and require complete
    cross-document isolation.

Classify the focused rerun as `PASS` only when every constructible scenario
passes and every failed solver operation restores exact state and history
without undo. Use `PASS WITH CAPABILITY GAPS` only for genuine missing public
operations already documented by Milestone 21; omitted work or time limits are
not capability gaps. Any caller-visible rollback history entry is `FAIL`.
