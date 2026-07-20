# AGENTS.md

## Scope

These instructions apply to all coding agents working in this repository. The
repository is a Python-based external FreeCAD workbench and will later host a
local MCP server inside FreeCAD.

## Naming Conventions

- Visible workbench name: `MCP`.
- Workbench class: `MCPWorkbench`.
- FreeCAD command IDs use the uppercase `MCP_` prefix, such as
  `MCP_ReportStatus`, `MCP_StopServer`, and `MCP_StartServer`.
- Python package: `freecad_mcp`.
- Do not rename the Python package to `mcp`; the MCP SDK may use the `mcp`
  namespace.
- Installed FreeCAD addon folder: lowercase `mcp`.
- Repository name: `freecad-mcp`.
- FreeCAD addon root: `src`, containing `Init.py`, `InitGui.py`, `package.xml`,
  `Resources`, and `freecad_mcp`.

## Architecture

- Keep FreeCAD startup modules small. Perform substantial initialization lazily
  when the workbench or a command is activated.
- Where an operation has both MCP and GUI adapters, they must call the same
  underlying command handlers. Do not duplicate CAD behavior in adapters.
- Keep pure-Python validation, schemas, dispatch, and result construction
  separate from FreeCAD imports so they can be tested with ordinary CPython.
- Treat `FreeCAD`, `FreeCADGui`, `Part`, `Sketcher`, and PySide as runtime
  adapter dependencies supplied by FreeCAD, not ordinary project dependencies.
- All GUI operations and FreeCAD document modifications must run on FreeCAD's
  main Qt thread. Do not mutate documents from an MCP transport thread.
- Wrap document changes in FreeCAD transactions. Recompute after modifications.
  Abort or roll back transactions on failure where the API permits it.
- Prefer structured inspection results over screenshots. Screenshots are
  checkpoints or diagnostic aids when structured state is insufficient; they are
  not the primary state mechanism.
- Use the project logging layer rather than scattered ad hoc logging calls.
  User-visible FreeCAD messages should go through the GUI/report adapter.

## MCP Tool Philosophy

- Expose explicit, typed tools. Never add an arbitrary Python execution tool
  such as `execute_python`.
- Define schemas, validation rules, structured success results, and actionable
  error results for every public tool.
- Prefer high-level workflow tools for common operations while retaining focused
  mid-level tools for flexibility.
- Use `create_sketch_rectangle` for a complete axis-aligned normal rectangle
  defined by width, height, and lower-left placement. Use
  `create_sketch_centered_rectangle` when the same complete profile is defined
  by centre, width, and height. Do not translate centre intent to lower-left
  placement when the dedicated semantic tool is available, reconstruct either
  standard profile through repeated primitive MCP calls, call one MCP tool from
  another, or invoke/simulate the Sketcher GUI Rectangle command.
- Use `add_sketch_geometry` for individual lines or incomplete/custom
  arrangements, and `add_sketch_constraints` to modify relationships on
  existing geometry. Tool 16 remains lower-left-only and tool 17 remains
  centre-only. Rotated, rounded, three-point, construction-edge, and partially
  constrained rectangles are not variants of either semantic rectangle tool.
- A centred rectangle has exactly four normal profile edges and one explicit
  construction point returned as semantic reference geometry. Preserve its
  direct corner symmetry, deterministic order, 12/13-constraint branches, and
  zero incidental helper geometry; do not replace the point with diagonals.
- Use `create_sketch_equilateral_triangle` for explicit equilateral-triangle
  intent and `create_sketch_regular_polygon` for generic regular-polygon intent,
  including a regular polygon with three sides. Both use the shared semantic
  polygon adapter; never route one through the other MCP tool or through a
  rectangle tool.
- Polygon size is circumradius (centre-to-vertex distance), not apothem or side
  length. Preserve counter-clockwise vertex/edge order, modulo-360 angle
  readback, the 3–64 side-count range, the construction centre and explicit
  construction circumcircle, and the `3N+3` origin / `3N+4` non-origin natural
  constraint formulas. Do not hide or remove either semantic reference.
- Use `create_sketch_slot` for straight-slot, obround, capsule, or pill-profile
  intent. Overall length is total end-to-end length, not arc-centre distance.
  Preserve two lines, two bounded semicircular arcs, true counter-clockwise
  traversal, modulo-360 angle readback, no helpers, and the 9/10 origin/non-origin
  natural constraint counts.
- Use `create_sketch_rounded_rectangle` for an axis-aligned rounded rectangle
  with one common positive radius and explicit lower-left or direct-centre
  placement. Preserve four lines, four bounded quarter arcs, external width and
  height, strict radius less than half the smaller dimension, no helpers, and
  the 19/20 centre-origin/other-placement natural constraint counts. Sharp
  rectangles remain tools 16/17; rotated and per-corner-radius profiles are not
  accepted.
- The two curved tools share internal bounded-arc, topology, tangency,
  orientation, and rollback infrastructure but retain distinct public schemas,
  handlers, verification, errors, and history labels. Never route one through
  the other, primitive MCP tools, rectangle MCP tools, or GUI commands.
- Provide inspection, validation, and recovery tools alongside mutating tools.
- Use `analyze_sketch` for a broad read-only topology and solver summary,
  `validate_sketch_profile` to decide whether all or selected geometry forms
  usable closed profiles, `list_sketch_open_vertices` to locate openings, and
  `get_sketch` for detailed controlled geometry and constraints. Choose the one
  primary inspection tool that answers the question; zero solver conflicts
  alone do not prove a valid profile.
- The three analysis tools share the pure sketch-topology engine. Construction
  and external geometry are excluded from profile topology unless explicitly
  requested. Preserve the fixed controlled tolerance, result-local vertex and
  profile identifiers, structured findings, and controlled external indices;
  never expose them as persistent or native identity.
- Sketch analysis is strictly read-only: do not recompute or solve, open a
  transaction, move history, save, activate a document, enter edit mode,
  change selection, repair geometry, or route one analysis MCP tool through
  another. Use existing mutation tools for creation or repair.
- Use `add_external_geometry` only for one proven same-document source object
  `EdgeN`/`VertexN` or another sketch's supported line, circle, or circular arc.
  Keep the public identity as the current non-negative sketch-local
  `external_reference_number`; never expose FreeCAD's negative native geometry
  index as API identity or claim that the controlled number is persistent.
- Use `list_external_geometry` for controlled mapping/projection readback and
  `get_sketch_dependencies` for attachment, expression, constraint, consumer,
  broken, and cross-document relationship inspection. Both operations are
  strictly read-only: no recompute, solve, transaction, history movement, save,
  activation, edit mode, selection change, repair, or MCP-to-MCP routing.
- `remove_external_geometry` must inspect impact and prefer refusal. Never
  cascade native constraint deletion; refuse used, unresolved, unsupported,
  non-normal, or cross-document references. Re-list after removal because
  surviving sketch-local reference numbers can change.
- A successful external add or removal is one verified `Add sketch external
  geometry` or `Remove sketch external geometry` history step. Failed atomic
  calls own rollback and must not be followed by undo. Correct wrong successful
  intent through exact-name undo and retry in the same sketch. Do not claim
  topological-name repair, healing, general cross-document support, or automatic
  saving.
- Use `remove_sketch_constraints` for explicit current constraint removal. Its
  indices describe the pre-call order and surviving constraints are remapped;
  refuse unsupported or expression-dependent selections rather than guessing
  cleanup. Never delete geometry or external references as a side effect.
- Use `remove_sketch_geometry` only for supported internal geometry with no
  dependent constraints. FreeCAD's native deletion cascades constraints, so
  report exact impact and require `remove_sketch_constraints` first. External
  references remain the responsibility of `remove_external_geometry`; never
  pass native negative geometry IDs through either internal-geometry tool.
- `set_sketch_geometry_construction` takes a desired final Boolean, not toggle
  intent. Change only mismatched selected geometry, report already-correct
  members, and create no transaction for an all-correct retry. Preserve counts,
  constraints, attachment, Body ownership, placement, and external references.
- Geometry and constraint indices are current-order-local. Removal requests use
  pre-call indices and results return ordered old-to-new survivor mappings;
  never describe those mappings as persistent identity. Successful owned
  mutations are one exact `Remove sketch constraints`, `Remove sketch geometry`,
  or `Set sketch geometry construction` history step and never save.
- Failed sketch removal/construction calls own exact rollback, including ordered
  geometry and constraints, construction flags, expressions, external mappings,
  solver/context/history state, and caller-owned transaction preservation. Do
  not undo after verified internal rollback; correct a wrong success with the
  exact transaction name and retry in the same sketch.
- Use `update_sketch_geometry` only for a complete same-type final state of one
  supported internal line, point, circle, or bounded arc. Preserve construction
  state and indices. A semantic no-op may report dependencies, but an actual
  edit with any dependent constraint is refused; use
  `update_sketch_constraint_value` for dimensional intent.
- `replace_sketch_constraint` reuses the unchanged 17-way controlled union.
  FreeCAD appends after deleting, so report the replacement index and complete
  survivor remapping; never imply slot preservation. Refuse duplicates,
  unsupported state, names, expressions, and solver conflicts rather than
  rebuilding unrelated constraints.
- Use `update_sketch_constraint_value` only for active driving distance,
  distance-x/y, radius, diameter, or angle constraints. Requests are absolute
  millimetre/degree values, not deltas. Never clear expressions or convert a
  reference constraint. All three editing tools are transaction-free on
  semantic no-op and use their exact `Update sketch geometry`, `Replace sketch
  constraint`, or `Update sketch constraint value` history name on owned
  success.
- Use `add_sketch_reference_constraints` only with the strict public
  `kind=internal`/`geometry_index` or
  `kind=external`/`external_reference_number` operands. Wrap point operands in
  `geometry` and use the established start/end/center/point `position` values.
  Never accept, log as public identity, or return FreeCAD's negative GeoIds.
- Prefer `add_sketch_constraints` for internal-only relationships. Reference
  constraint production behavior must use the static tested FreeCAD 1.1.1
  capability allowlist; never trial native combinations against a user's
  document. External geometry remains read-only, so unary external and
  external-only driving relationships are refused before transaction opening.
- Coincident is point-to-point. Use Point-on-Object to place an external or
  internal selected point on a line, arc, or circle. Tangency is a
  whole-geometry relationship. Verify source propagation and external mapping,
  not merely native construction success.
- A successful owned reference-aware batch is one exact `Add sketch reference
  constraints` history step. Preflight all 1–100 items, reject the whole batch
  on stale identity, unsupported capability, or semantic duplicate, and
  preserve request order. Caller-owned transactions remain open; failed calls
  restore exact internal/external/dependency/solver/context/history state.
  Abort an owned transaction before any compensating constraint or geometry
  mutation; inverse-only rollback is reserved for a caller-owned transaction or
  a native abort that genuinely remains pending. For an owned call, activate
  the exact target before opening the transaction and restore the previous
  active document before verification or rollback verification; otherwise
  FreeCAD can link the history step into the wrong document. Caller-owned calls
  must not switch the active document. Do not claim single-item
  requests are a solver-failure workaround: the recorded live equilateral
  circumcircle failed on its third sequential Point-on-Object and the incircle
  on its second sequential tangent.
- Mixed constraints block their internal geometry and external reference from
  removal until `remove_sketch_constraints` explicitly removes them. Do not
  broaden Milestone 20 replacement or datum schemas: both continue to refuse
  mixed constraints. External reference numbers are current-order-local and
  must be relisted after removal. Constraint names and expressions remain
  Milestone 22 work.
- After a successful modelling mutation, recompute and inspect the result. If
  it is technically valid but expresses the wrong design intent, inspect the
  named document's history and undo the known top transaction before retrying
  in the same sketch or model. Supply the expected transaction name when known.
- Prefer controlled in-place recovery over abandoning a recoverable sketch,
  duplicating geometry, or creating replacement sketches or documents.
- Direct tangency is a whole-geometry relationship. Place supported geometry
  near the intended branch, recompute and inspect the actual result, and verify
  that arc contact lies on the intended visible bounded arc. Do not use
  tangency as endpoint coincidence, point-on-object, parallel, perpendicular,
  or collinearity, and do not synthesize hidden helper geometry for it.
  The public primitive constraint remains whole-geometry-only. Semantic curved
  profile adapters may use their separately verified native endpoint-tangent
  form internally because the bounded joins and arc domains are fixed and
  returned explicitly; do not add that form to the public 17-way union.
- Do not undo after a failed atomic MCP operation whose rollback restored zero
  mutation. Do not undo an unexpected GUI or user transaction; reinspect and
  ask for direction. Redo only to restore the most recently undone step, before
  an intervening mutation invalidates it.
- Use semantic names instead of exposing FreeCAD numeric enum conventions
  directly.
- Avoid fragile face and edge indices where stable semantic references or
  geometric selection criteria are possible.
- Keep tool contracts versioned and documented. Do not silently change request
  or response fields.
- The first explicit MCP tool is `create_document`. It is MCP-only and must use
  the shared application handler rather than a visible workbench command.
- Document-history tools are one-step-only, must run through the Qt dispatcher,
  and must not expose native transaction IDs or objects, save implicitly, or
  wrap native undo/redo in another transaction.
- A successful lower-left rectangle is one verified `Create sketch rectangle`
  history step; a successful centre-defined rectangle is one verified `Create
  centered sketch rectangle` step. If its intent is wrong, recompute, inspect,
  match and undo that exact step, then retry in the same sketch. A failed
  rectangle call owns its rollback and must not be followed by undo.
- A successful triangle or polygon is one verified `Create sketch equilateral
  triangle` or `Create sketch regular polygon` history step. Correct a wrong
  success through exact-name undo and retry in the same sketch; failed atomic
  polygon calls own their rollback and must not be followed by undo.
- A successful slot or rounded rectangle is one verified `Create sketch slot`
  or `Create sketch rounded rectangle` history step. Correct a wrong success by
  exact-name undo in the same sketch; failed atomic curved-profile calls own
  their rollback and must not be followed by undo.

## Python Standards

- Add type hints to public functions, methods, classes, and data structures.
- Prefer small modules with one clear responsibility.
- Use dataclasses or typed result objects where they improve clarity.
- Establish clear exception boundaries between pure command logic, FreeCAD
  adapters, GUI adapters, and MCP transport code.
- Isolate FreeCAD imports to adapter modules or narrow function scope.
- Avoid hidden mutable global state unless the FreeCAD lifecycle requires it;
  document lifecycle-owned state explicitly.
- Add no dependency unless the standard library or FreeCAD runtime cannot
  reasonably provide the capability.
- Development-only tools belong in the `dev` optional dependency group and must
  not be assumed available inside FreeCAD.
- Add tests for schemas, validation, dispatch, protocol behavior, and pure
  command logic.

## Compatibility

- Target FreeCAD 1.1 and later initially.
- Core Python code must remain portable across Windows, Linux, and macOS.
- Avoid platform-specific assumptions in core logic. Keep junction, symlink,
  and platform-specific FreeCAD user-directory handling in scripts or platform
  adapters.
- Document FreeCAD API behavior that must be verified against the installed
  FreeCAD build.
- Use Python 3.11-compatible syntax while FreeCAD 1.1.x ships Python 3.11
  builds. Re-check this constraint when the supported FreeCAD range changes.

## Development Workflow

1. Inspect the repository and relevant documentation before editing.
2. Make the smallest coherent change that satisfies the task.
3. Run the narrowest relevant tests first, then `scripts/test.ps1` or
   equivalent checks before completion.
4. Test inside FreeCAD after changes to `Init.py`, `InitGui.py`, GUI code,
   FreeCAD adapters, resources, or package metadata.
5. Record exact manual test steps when FreeCAD runtime automation is not
   available.
6. Keep README and architecture/development documents synchronized with
   architectural changes.
7. Review `git diff` and `git status` before committing or reporting
   completion.

## Safety and Change Control

- Do not perform destructive file operations without explicit approval.
- Do not install packages or alter machine-wide configuration without explicit
  approval.
- Do not modify the user's ESP32 Eclipse workspace or compiler configuration.
- Do not replace targeted code with broad rewrites when a focused patch is
  sufficient.
- If a command fails, report the command, exit status, relevant output, and the
  next safe diagnostic step. Do not conceal failures.
- Do not commit secrets, local paths, generated caches, virtual environments, or
  FreeCAD user data.
