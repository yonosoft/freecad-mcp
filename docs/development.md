# Development Setup

## Workspaces and Repositories

Use a generic Eclipse Python workspace:

```text
C:\Users\Goran\python-workspace
```

Keep Git repositories under:

```text
C:\Users\Goran\git
```

The Eclipse workspace must not contain copied repositories. Import or create the
PyDev project from the existing repository path:

```text
C:\Users\Goran\git\freecad-mcp
```

Keep FreeCAD/Python work separate from any ESP32 workspace or toolchain setup.

## Python Tooling

Use standalone CPython 3.11 for PyDev, linting, type checking, and tests.
FreeCAD 1.1.x release builds also use Python 3.11, but FreeCAD runtime modules
are supplied by FreeCAD itself.

The `freecad-mcp` project uses its own `.venv` for local tooling where
practical:

```powershell
cd C:\Users\Goran\git\freecad-mcp
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\scripts\test.ps1
```

The repository scripts never install packages automatically.

The MCP server uses the official MCP SDK. The development venv receives it from
the project's normal dependency declaration. The FreeCAD runtime is separate;
for the current FreeCAD 1.1 Windows build, install the dependency once into its
per-user package target:

```powershell
& "C:\Program Files\FreeCAD 1.1\bin\python.exe" -m pip install `
  --target "$env:APPDATA\FreeCAD\v1-1\AdditionalPythonPackages\py311" `
  "mcp>=1.27.2,<2"
```

This target is the location used by FreeCAD's Addon Manager. It is not the
project `.venv` and does not modify `Program Files`.

## Eclipse/PyDev

Configure PyDev with standalone Python 3.11, preferably the project venv:

```text
C:\Users\Goran\git\freecad-mcp\.venv\Scripts\python.exe
```

Create the PyDev project from existing sources:

1. Choose **File -> New -> Project -> PyDev -> PyDev Project**.
2. Project name: `freecad-mcp`.
3. Clear **Use default** and point **Project contents** to
   `C:\Users\Goran\git\freecad-mcp`.
4. Choose Python grammar 3.11 and the configured interpreter.
5. Set the PyDev source root to `/freecad-mcp/src`.
6. Optionally add `/freecad-mcp/tests` for test navigation.

Recommended excluded/generated folders:

```text
.venv
.git
__pycache__
.pytest_cache
.mypy_cache
.ruff_cache
build
dist
*.egg-info
```

Eclipse `.project`, `.pydevproject`, `.settings`, and workspace `.metadata` are
local IDE configuration and should not become repository policy.

## FreeCAD Runtime Imports

Modules such as `FreeCAD`, `FreeCADGui`, `Part`, and `Sketcher` execute inside
FreeCAD. They generally cannot be imported safely by unrelated standalone
Python because compiled modules and DLL/search paths are tied to the FreeCAD
installation.

Use these practices:

- keep FreeCAD imports inside adapter modules or function bodies;
- keep schemas, validation, dispatch, and result objects in pure-Python modules;
- use narrow `# type: ignore[import-not-found]` comments where an adapter must
  import a FreeCAD module;
- do not add FreeCAD as a pip dependency;
- do not add the whole FreeCAD installation to the standalone interpreter unless
  a tested local setup proves compatible.

## Development Install

Current Windows development uses a PowerShell script and a directory junction:

```text
%APPDATA%\FreeCAD\v1-1\Mod\mcp -> <repository>\src
```

Run from the repository root:

```powershell
.\scripts\install-dev.ps1
```

The installed addon folder is lowercase `mcp`; the visible FreeCAD workbench
name is `MCP`. If multiple FreeCAD user directories exist and the script cannot
select one safely, pass `-FreeCADModRoot` explicitly.

Linux and macOS support is intended to use symbolic links and the
platform-appropriate FreeCAD user `Mod` directories later. That support is not
implemented yet, and Windows junction mechanics are not architectural
requirements.

## Run and Test

Pure Python checks run under the project venv:

```powershell
.\scripts\test.ps1
```

The portable CI entry point runs the same checks on every host and can be run
with the active Python 3.11 interpreter:

```powershell
.\.venv\Scripts\python.exe scripts\ci.py
```

It runs Ruff lint, Ruff formatting check, Mypy, and Pytest, in that order. It
does not install FreeCAD or run live GUI acceptance. GitHub Actions and Forgejo
Actions invoke this same script after `pip install -e ".[dev]"`, so the hosted
checks remain equivalent.

GitHub uses an Ubuntu hosted runner. Codeberg uses Forgejo Actions: enable the
repository's **Actions** unit and provide a repository or organization runner
with the `docker` label before its workflow can run. Codeberg's hosted Actions
availability is limited; no credentials or publishing configuration are needed
for this workflow.

Workbench startup, FreeCAD API behavior, Qt behavior, and document mutation
must be tested inside FreeCAD.

Typical loop:

```text
Edit in Eclipse
run scripts/test.ps1
restart FreeCAD
select MCP workbench
inspect Report View
start or stop the MCP server
```

### Test Suite Organization

Add tests beside the responsibility they exercise:

- command-handler behavior belongs in the existing operation-focused modules,
  such as `test_create_document.py`, `test_save_document.py`,
  `test_get_object.py`, `test_get_sketch.py`, `test_create_body.py`, and
  `test_create_sketch.py`; `test_add_sketch_geometry.py` owns the geometry
  input contract, while `test_add_sketch_constraints.py` owns constraint input
  models, validation, result serialization, and handler behavior;
- FreeCAD document lifecycle and persistence belong in
  `test_freecad_document_operations.py`;
- object hierarchy, visibility, lookup, and placement extraction belong in
  `test_freecad_object_inspection.py`;
- transactional body and sketch creation belong in
  `test_freecad_body_creation.py` and `test_freecad_sketch_creation.py`;
- origin-plane resolution, support parsing and fallback, MapMode, attachment
  results, and attachment rollback belong in `test_freecad_sketch_attachment.py`;
- read-only sketch geometry, constraints, cached solver facts, malformed data,
  and non-mutation safeguards belong in `test_freecad_sketch_inspection.py`;
- atomic insertion, ordered indices, construction state, transaction ownership,
  injected failures, and verified rollback belong in
  `test_freecad_sketch_geometry_creation.py`;
- atomic constraint construction, compatibility validation, ordered indices,
  transaction ownership, geometry/flag preservation, and rollback belong in
  `test_freecad_sketch_constraint_creation.py`;
- history models, validation, handlers, and application delegation belong in
  `test_document_history.py`; native stack transitions, preconditions,
  verification, file state, and isolation belong in
  `test_freecad_document_history.py`;
- semantic rectangle models, validation, serialization, handler behavior, and
  focused error mapping belong in `test_create_sketch_rectangle.py`; native
  construction order, all placement branches, caller-owned transactions,
  verification injection, and exact rollback belong in
  `test_freecad_sketch_rectangle_creation.py`; centred request/result and
  handler coverage belongs in `test_create_sketch_centered_rectangle.py`, with
  exact point/edge/constraint order, all centre branches, transaction ownership,
  corruption injection, and rollback in
  `test_freecad_sketch_centered_rectangle_creation.py`;
- MCP schemas, descriptions, and delegation belong in
  `test_mcp_document_tools.py`, `test_mcp_object_tools.py`, or
  `test_mcp_creation_tools.py`; the exact geometry union and tool-eleven
  contract belong in `test_mcp_sketch_geometry_tools.py`, while the strict
  nested constraint union and tool-twelve contract belong in
  `test_mcp_sketch_constraint_tools.py`; strict tool 13–15 schemas,
  descriptions, recovery guidance, and MCP errors belong in
  `test_mcp_document_history_tools.py`; tool-sixteen discovery, strict schema,
  structured result, and selection/recovery guidance belong in
  `test_mcp_sketch_rectangle_tools.py`; tool-seventeen discovery, strict centre
  schema, semantic reference result, and tool-selection guidance belong in
  `test_mcp_sketch_centered_rectangle_tools.py`; server composition,
  inventory agreement, lifecycle reporting, and HTTP transport belong in
  `test_mcp_server.py`;
- compatibility identity belongs in `test_module_compatibility.py`, and stable
  dependency-direction safeguards belong in `test_architecture.py`.

The non-collectable `freecad_adapter_stubs.py` and `mcp_server_stubs.py` modules
contain only test fakes shared across several responsibility files. Keep small
dispatchers, builders, and mutable state local when only one test module needs
them; do not grow a global `conftest.py` for convenience.

Both `scripts/ci.py` and `scripts/test.ps1` run the ordinary pure-Python suite.
That suite uses stubs and clean subprocess imports and never requires a running
FreeCAD process. Changes limited to tests and documentation therefore do not
require live acceptance. Changes to FreeCAD adapters, runtime composition, Qt
dispatch, bootstrap modules, GUI code, resources, or package metadata still
require the relevant live checks below.

### get_sketch Automated Coverage

The completed `get_sketch` milestone covers the exact tenth-tool inventory and
MCP schema, application and runtime wiring, explicit registration, architecture
boundaries, and adapter inspection. Focused tests cover supported and
construction geometry, supported constraints, controlled unsupported geometry
and constraints, standalone sketches, exact internal-name lookup, attachment
and second-body isolation, stale and fresh cached solver facts, malformed data,
controlled errors, and non-mutation safeguards. This coverage is deliberately
limited to the implemented types and does not imply support for every FreeCAD
geometry or constraint.

### add_sketch_geometry Automated Coverage

The `add_sketch_geometry` milestone covers exact tool-eleven ordering without
changing the first ten tools, the strict discriminated MCP schema, application
and runtime wiring, focused adapter delegation, and architecture boundaries.
Pure-Python tests exercise all four supported types in mixed request order,
standalone and attached sketches, existing-index continuation, construction
state, exact success serialization, the 1-to-100 batch limit, malformed and
unsupported input, finite numeric rules, positive radius, zero-length lines,
arc normalization, exact assigned indices, no recompute/save/solve, and
transaction ownership.

Failure injection covers the first, middle, and final item; constructor,
insertion, index, construction, and commit failures; appended geometry that
appears before an exception; pre-existing construction restoration; explicit
tail deletion when abort cannot undo geometry; abort failure; rollback
verification failure; closed transaction state; and absence of partial success
or partial index results.

Point geometry has a public two-direction regression rule: do not rename
`PointGeometryInput.position` or `SketchPointGeometry.point` without treating
the change as an explicit public schema change. Schema tests and live MCP
acceptance must verify mutation input and controlled inspection output
independently rather than assuming their field names are symmetrical.

### add_sketch_constraints Automated Coverage

The `add_sketch_constraints` milestone preserves the first eleven tool names,
schemas, and order and registers the new operation explicitly as tool twelve.
Focused tests cover the strict outer type and nested mode discriminators, every
supported type and overload, semantic point tokens, exact required/additional
fields, the 1-to-100 limit, direct angle policy, signed X/Y distances, positive
Euclidean dimensions, controlled result serialization, handler dispatch and
error translation, application/runtime wiring, public adapter delegation, and
architecture boundaries. Native-reference coverage locks the exact one-field
`origin`, `horizontal_axis`, and `vertical_axis` models, both public orderings,
origin-to-origin and invalid-scope rejection, raw-negative-ID rejection, and
the original axis-target request order. Milestone 14B coverage locks its
established constraint members and strict ordinary whole-geometry targets,
`horizontal_points`, and `vertical_points`. Symmetric coverage locks all
five `about` forms, every supported point token, strict whole-line references,
degenerate-reference rejection, and preservation of every preceding union
member. Milestone 14C coverage locks the resulting exact 17-member top-level
schema and the strict two-whole-geometry `tangent` member without changing any
of the preceding variants.

Adapter stubs exercise all verified `Sketcher.Constraint` constructors in one
mixed ordered batch, construction geometry, standalone and attached sketches,
existing-index continuation, exact returned indices and final counts, exact
internal-name lookup, pre-transaction range/type/position compatibility,
first/middle/final failures, commit failure, caller-owned and owned
transactions, reverse tail deletion, pre-existing dimensional values and
driving/active/virtual flags, geometry restoration after internal solver
movement, rollback verification failure, and absence of explicit solve,
recompute, or save calls. `get_sketch` coverage also locks controlled readback
of point geometry and the private root-point encoding used by Euclidean
point-to-origin distance. Focused native-reference tests cover circle and arc
centres, both line endpoints, arc endpoints, `Part.Point`, construction
geometry, origin coincidence, horizontal/vertical `PointOnObject`, controlled
inspection, axis/origin disambiguation, later-item atomic rejection, and
rollback after FreeCAD-like immediate geometry movement.

General point-relationship adapter tests cover ordinary line, circle, and arc
targets; point geometry, both line endpoints, circle centres, and all three arc
point kinds; normal and construction target lines; mixed point kinds; same-line
endpoint alignment; exact three- and five-argument native constructors;
pre-transaction unsupported/self/identity/range/position failures; later-item
prevalidation; injected native failure rollback; and controlled malformed-record
isolation. Schema and MCP tests protect the unchanged whole-line variants,
ordinary target `edge` readback, preservation of the first twelve tools, and modelling-policy
description.

Controlled symmetry adapter tests lock both verified native constructor forms,
origin and both axes, geometry-point and line-segment centres, complete-batch
validation before a transaction, native failure rollback, and controlled
readback without raw IDs. The centred-rectangle regression uses four lines,
four endpoint coincidences, two horizontal and two vertical constraints, 30 mm
and 20 mm whole-line dimensions, and one origin symmetry. The direct FreeCAD
run proves zero DoF and clean conflict/redundancy/malformed diagnostics.

Controlled direct-tangency tests lock the exact native two-index constructor,
all five supported pair classes, both heterogeneous orders, normal and
construction geometry, exact request-order fields, and one native constraint
per public item. Negative coverage proves same-geometry, line-line, point,
unsupported, out-of-range, position-qualified, axis/origin, and branch-field
requests fail before mutation. Batch tests cover later invalid items, injected
native failure, reverse rollback, mixed valid batches, and exact counts.
Inspection tests cover controlled order-preserving readback and isolation of
point-specific, line-line, degenerate, and malformed native tangent records.

The reusable direct runtime check is
`scripts/smoke_sketch_native_references.py`. Run it with FreeCAD 1.1's Python
and the development environment's site-packages on `PYTHONPATH`. It creates
only unsaved disposable documents, exercises native origin and axis references
through `FreeCADDocumentAdapter`, verifies immediate movement and controlled
readback, and checks the two-circle/four-constraint/zero-construction/zero-DoF
regression plus one-step undo and redo. It does not connect to or exercise the
live MCP endpoint.

Milestone 14A's focused direct runtime check is
`scripts/smoke_sketch_symmetric.py`. It uses one disposable sketch per semantic
case and covers origin, both axes, another geometry point, a line segment,
line endpoints, point geometry, circle centres, arc centres, mixed batches,
invalid-reference prevalidation, injected native failure rollback, saved and
unsaved state, controlled readback, one-step undo/redo, and the fully
constrained centred rectangle. Only its saved-state case writes a temporary
fixture, and that case verifies the mutation does not update the file.

Milestone 14B's focused direct runtime check is
`scripts/smoke_sketch_point_relationships.py`. Run it with FreeCAD 1.1's
embedded Python. It executes 24 clean-sketch scenarios: all ordinary target
classes, both point-pair alignments with line and mixed point kinds, existing
axis and whole-line regressions, controlled readback, invalid/self/later-item
zero mutation, injected failure rollback, saved and unsaved state, one-step
undo/redo, a body-owned origin-plane-attached sketch, and the circle
cardinal-point product regression. Only the explicit saved-file case writes a
temporary file. The product regression verifies a 10 mm origin-centred circle,
two on-circle aligned points, zero DoF, clean solver diagnostics, no helper
geometry, controlled references, one-step undo/redo, and unsaved state.

Milestone 14C's focused direct runtime campaign is
`scripts/smoke_sketch_tangent.py`. Run it with FreeCAD 1.1's embedded Python
and the development environment's site-packages on `PYTHONPATH`. It executes
32 scenarios covering the full compatibility matrix and reverse orders,
construction geometry, strict rejections, later-item and injected-failure
atomic rollback, mixed batches, controlled and malformed-native readback,
standalone/attached and saved/unsaved states, single/batch undo and redo, redo
invalidation, solver freshness, same-sketch wrong-branch recovery, the natural
fully constrained upper-tangent product, and symmetry plus Milestone 14B point
relationships. It also proves that direct arc tangency can be valid on the
underlying support circle while the contact lies outside the visible arc. The
installed campaign passes 32/32 on FreeCAD 1.1.1 revision
`0108fd4b4850cc46e625b60e53cea7a7bbe69f8d` with embedded Python 3.11.14.

### Controlled Document History Automated Coverage

Milestone 14B-2 preserves the first twelve schemas, descriptions, behavior, and
order, then registers `get_document_history`, `undo_document`, and
`redo_document` as tools 13–15. Focused pure-Python tests cover exact strict
schemas, rejected extra fields and wrong types, typed result serialization,
handler delegation and error translation, runtime composition, explicit
registration, and architecture boundaries.

The FreeCAD adapter tests use realistic top-first stack transitions and cover
empty, undo-only, redo-only, and two-sided history; one-step undo and redo;
exact expected-name match and mismatch; disabled history; active transaction;
re-entrant undo, redo, and rollback; native `False` and exceptions;
post-operation transition mismatches; document closure; cross-document
isolation; and saved/unsaved state without a save call. Existing transaction
tests lock the public labels `Create body`, `Create sketch`, `Add sketch
geometry`, and `Add sketch constraints`.

Run the direct campaign with FreeCAD 1.1's embedded Python and the development
environment's site-packages on `PYTHONPATH`:

```powershell
& "C:\Program Files\FreeCAD 1.1\bin\python.exe" scripts\smoke_document_history.py
```

The script runs 27 isolated scenarios. It covers empty stacks; single and batch
geometry/constraint undo/redo; symmetry and all Milestone 14B point
relationships; mixed batches; body, sketch, and attached-sketch creation;
expected-name mismatches; redo invalidation; cross-document isolation;
saved-file timestamp and byte preservation; unsaved state; controlled readback;
repeated inspection; active-transaction rejection; injected native false
return; and solver freshness. Its product regression applies a valid but wrong
symmetry to a four-edge rectangle, detects it, matches and undoes the controlled
constraint transaction, proves exact geometry restoration in the same sketch,
applies the corrected symmetry, creates no replacement sketch or helper, and
proves the corrected mutation invalidates the prior redo entry.

The installed-runtime probes use FreeCAD `1.1.1`, revision
`0108fd4b4850cc46e625b60e53cea7a7bbe69f8d`, and embedded Python `3.11.14`.
Headless probes establish the exact bound properties, top-first names, native
`None` return, redo invalidation, and stale solver cache. A separate isolated
full-GUI probe establishes that `FreeCADGui.Document.Modified` becomes true
after a committed transaction and remains true after its undo and redo.

### Semantic Rectangle Automated and Runtime Coverage

Milestone 15A preserves the first fifteen tools and all 17 sketch-constraint
variants, then explicitly registers `create_sketch_rectangle` as tool sixteen.
Focused pure-Python coverage locks the strict lower-left schema, finite numeric
policy, validation and error envelopes, explicit registration, handler and
runtime delegation, exact edge/corner serialization, architecture boundaries,
and unchanged primitive schemas. Native adapter fakes exercise exact four-line
and constraint construction order, non-zero geometry/constraint offsets, all
four zero/non-zero placement branches, caller-owned and owned transactions,
wrong indices and counts, native exceptions, recompute and semantic readback
failures, solver diagnostics, reverse cleanup, solver-moved geometry, and exact
pre-existing geometry/constraint/construction/context restoration.

FreeCAD 1.1.1 primary-source review used:

- `src/Mod/Sketcher/Gui/DrawSketchHandlerRectangle.h` at the official FreeCAD
  `1.1.1` tag for the GUI command's perimeter ordering, endpoint directions,
  constraint choices, and transaction reference behavior;
- `src/Mod/Sketcher/App/SketchObjectPyImp.cpp` for single and batch
  `addGeometry`, `addConstraint`, index returns, and immediate solver behavior;
- `src/App/Document.cpp` for transaction open/commit/abort behavior, pending
  transaction state, active-document propagation, and undo/redo grouping;
- the official FreeCAD Sketcher Workbench documentation for closed-profile,
  constraint, rectangle, and recompute concepts.

The production adapter does not call the GUI command. Installed-runtime probes
on FreeCAD `1.1.1`, revision
`0108fd4b4850cc46e625b60e53cea7a7bbe69f8d`, embedded Python `3.11.14`, verified
single geometry and constraint index returns, endpoint order, all placement
branches, `PointOnObject` axis placement, origin coincidence, signed X/Y
dimensions, immediate solver movement during `addConstraint`, clean zero-DoF
recompute, one-step undo/redo, and modified/saved behavior. The origin branch
uses 11 constraints and every non-origin branch uses 12.

Run the focused adapter smoke with the FreeCAD embedded interpreter and the
development dependencies on `PYTHONPATH`:

```powershell
& "C:\Program Files\FreeCAD 1.1\bin\python.exe" scripts\smoke_sketch_rectangle.py
```

It runs 35 isolated scenarios: origin, translated, positive, negative and
mixed-sign placements; deterministic mappings and dimensions; closure,
zero-DoF and clean diagnostics; no helpers/construction; non-empty and
construction-containing sketches; Body ownership and XY attachment; unsaved
and saved-file preservation; one-step undo/redo, name mismatch, redo
invalidation; validation, geometry, constraint and verification failure
rollback; cross-document isolation; Milestone 14A/14B/14B-2/14C regressions;
and same-sketch recovery. The centred product request is expressed once as a
30 × 20 rectangle with lower-left `(-15, -10)` and verifies the expected four
edges without adding a `center` schema variant. The installed campaign passes
35/35 and records version, revision, interpreter, scenario count, pass count,
and exit status in JSON.

Saved-file coverage records path, bytes, timestamp, and dirty state, then
creates, undoes, and redoes without saving; disk bytes and timestamp stay
unchanged. Unsaved documents remain pathless. Body ownership, XY-plane support,
MapMode and placement survive creation and history movement. Recovery proves a
misplaced but valid semantic rectangle can be matched and undone as one
`Create sketch rectangle` transaction, then corrected in the same sketch with
no abandoned geometry or replacement sketch and with the old redo invalidated.

### Semantic Centred Rectangle Automated and Runtime Coverage

Milestone 15B preserves the first sixteen tools, the lower-left-only tool 16
schema, and all 17 sketch-constraint variants, then registers
`create_sketch_centered_rectangle` as tool 17. Its strict request is
`document_name`, `sketch_name`, finite positive `width` and `height`, and a
`center` object containing exactly finite strict numeric `x` and `y`. All
levels forbid additional properties and reject booleans, NaN, and infinity.

Tool selection is intentional: lower-left-defined complete rectangles use tool
16; centre-defined complete rectangles use tool 17; custom/incomplete geometry
uses `add_sketch_geometry`; relationships on existing geometry use
`add_sketch_constraints`. Centre intent is never translated into a calculated
lower-left tool-16 request. Neither semantic adapter calls another MCP tool or
activates the Sketcher GUI command.

Shared `sketch_rectangle_profile` helpers own four-edge bounds, bottom/right/
top/left generation, the common four closure plus four orientation plus two
dimension constraints, point references, and semantic edge verification. The
centred adapter adds one construction `Part.Point` fifth, one lower-left ↔
upper-right symmetry about that point, and natural point placement. Origin
uses one coincidence; only-X-zero uses vertical-axis membership and Y distance;
only-Y-zero uses horizontal-axis membership and X distance; otherwise it uses
X and Y distances. FreeCAD 1.1.1 confirms 12 constraints at origin and 13 on
all other branches, zero DoF, full constraint, and clean diagnostics.

The result keeps four profile edges in `geometry_indices` and returns the
construction point separately in `reference_geometry_indices` and the
controlled centre mapping. There are four normal edges, one explicit semantic
construction reference, and zero incidental helper elements. Exact geometry,
corner/midpoint, symmetry, placement, construction, solver, context, and
document readback is required before committing one `Create centered sketch
rectangle` transaction.

Focused tests cover strict models/schema/validation, typed command and runtime
delegation, all error mappings, exact MCP tool order, unchanged first-sixteen
schemas and 17-variant union, non-empty offsets, exact native constructors,
all four placement branches, caller-owned and owned transactions, wrong
indices/counts/construction, edge/point/constraint/recompute/verification
failures, corrupted centre/symmetry/solver readback, and exact restoration of
pre-existing geometry, construction, constraints, context, history, and solver
state. Architecture tests reject FreeCAD imports outside adapters, MCP-to-MCP
calls, GUI activation, and lower-left entry-point delegation.

Primary-source research for the installed `1.1.1` tag used:

- `DrawSketchHandlerRectangle.h` for the built-in centre-and-corner perimeter,
  construction point, direct opposite-corner symmetry, and attachment pattern;
- `ConstraintPyImp.cpp` for the six-reference geometry-point `Symmetric`
  constructor and native `PointOnObject`/`DistanceX`/`DistanceY` forms;
- `SketchObjectPyImp.cpp`, `Sketch.cpp`, and `SketchObject.cpp` for point and
  constraint insertion, construction state, immediate solver effects, DoF,
  and diagnostics;
- `Document.cpp` for open/commit/abort and undo/redo behavior;
- `src/Mod/Sketcher/App/planegcs/GCS.cpp` for conflict and redundancy behavior;
- the official Sketcher Workbench documentation for semantic rectangle and
  constraint concepts.

The installed probe used FreeCAD `1.1.1`, revision
`0108fd4b4850cc46e625b60e53cea7a7bbe69f8d`, embedded Python `3.11.14`. It
proved point geometry at append index five, construction state, exact symmetry
references `(bottom,start)`, `(right,end)`, `(centre,point)`, each centre branch,
12/13 constraints, zero DoF, clean diagnostics, one-step undo/redo, restored
construction state, and arbitrary centre `(12,-7)`.

Run the 47-scenario direct campaign with the embedded interpreter:

```powershell
& "C:\Program Files\FreeCAD 1.1\bin\python.exe" `
  scripts\smoke_sketch_centered_rectangle.py
```

It covers the origin and arbitrary-centre product cases, all axis branches,
negative/mixed signs, deterministic indices/corners, fifth construction point,
no diagonals, exact geometry and midpoint/symmetry, 12/13 counts, zero DoF and
clean diagnostics, non-empty and construction-containing sketches, Body/XY
attachment, unsaved and saved-file byte/timestamp preservation, exact-name
undo/redo and construction restoration, name mismatch, redo invalidation,
validation and injected edge/point/symmetry/verification rollback,
cross-document isolation, Milestone 15A/tangent/symmetry/point/history
regressions, same-sketch recovery, and the tool-selection distinction. The
installed campaign passes 47/47 and emits version, revision, interpreter,
scenario count, pass count, and zero incidental helpers as JSON.

The separate live endpoint campaign is prepared in
[`aiderdesk-milestone-15b-acceptance.md`](aiderdesk-milestone-15b-acceptance.md)
and is intentionally not executed by the implementation task.

### Native Sketch Reference Live Acceptance Plan (Not Executed Here)

Use a focused AiderDesk MCP profile only after automated checks and the direct
adapter smoke pass:

1. Record `git status --short --branch` and preserve the repository without
   edits, commits, pulls, pushes, or generated files.
2. Discover all seventeen tools and verify the first twelve remain unchanged,
   with `add_sketch_constraints` still tool twelve and
   `create_sketch_rectangle` tool sixteen and
   `create_sketch_centered_rectangle` tool seventeen.
3. Capture the exact updated schema: 17 constraint mappings; strict geometry
   point references; exact one-field `origin`, `horizontal_axis`, and
   `vertical_axis` references; and forbidden additional fields.
4. In separate unsaved sketches, add circle-centre, arc-centre, line-start,
   line-end, and `Part.Point` coincidences to `origin`; repeat one with origin
   first in the request.
5. Add line and representative curved/point geometry references to both native
   axes with `point_on_object`; verify the resulting FreeCAD type is
   `PointOnObject`, never `Coincident`.
6. Verify each successful item adds exactly one constraint, adds no geometry,
   creates no zero-valued `DistanceX`/`DistanceY`, and returns one index.
7. Use `get_sketch` to verify controlled `origin` and axis references and that
   no private negative native ID appears.
8. Create two initially off-origin circles of radii 10 mm and 15 mm. Submit
   exactly two origin coincidences and two radius constraints.
9. Verify exactly two geometries, zero construction geometries, exactly four
   constraints in request order, both centres at origin, and radii 10 and 15.
10. Record stale solver state immediately after mutation; explicitly recompute,
    then verify fresh state, zero degrees of freedom, and fully constrained.
11. Verify `origin` to `origin`, origin under `point_on_object`, axes under
    `coincident`, unknown literals, extra reference fields, raw negative IDs,
    incompatible positions, and out-of-range geometry all fail controllably.
12. Submit a valid origin coincidence followed by a later invalid item and
    compare a full before/after snapshot to confirm zero mutation and no partial
    indices.
13. With undo enabled, verify one undo removes the complete successful batch
    and one redo restores its exact order, types, values, and references.
14. Repeat representative checks on standalone and body-attached sketches and
    with construction geometry where the point selector is valid.
15. Confirm an unsaved document remains unsaved. In a separately saved
    disposable document, verify path, timestamp, and bytes remain unchanged.
16. Close disposable documents without saving, stop MCP, retain the AiderDesk
    transcript/schema/state snapshots, and confirm final repository status
    exactly matches step 1.

## Report View Verification

In FreeCAD, enable **View -> Panels -> Report View**. Also enable redirection of
Python output/errors in FreeCAD preferences when diagnosing startup failures.

## Server and Client Verification

Manual runtime check:

1. Exit every FreeCAD process.
2. Confirm or create the development junction with `.\scripts\install-dev.ps1`.
3. Start FreeCAD.
4. Open Report View.
5. Select the **MCP** workbench.
6. Confirm only **Start Server**, **Stop Server**, and **Report Status** are
   present in the toolbar and MCP menu. Confirm there is no **Create Document**
   command or icon.
7. Click **Report Status** and confirm the state is `stopped`.
8. Click **Start Server** and confirm FreeCAD remains responsive.
9. Click **Report Status** and confirm the state is `running` and URL is:

```text
http://127.0.0.1:8765/mcp
```

Use a dedicated MCP client test profile containing only:

```json
{
  "mcpServers": {
    "freecad": {
      "type": "http",
      "url": "http://127.0.0.1:8765/mcp"
    }
  }
}
```

Confirm the client lists exactly these MCP tools, in the order defined by
`src/freecad_mcp/tool_registry.py`:

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
```

These document, object, and sketch-inspection tools are MCP-only; the workbench
has no matching document toolbar or menu commands. Connect the dedicated Aider
MCP test project and confirm
`create_document` remains discoverable, then run this disposable acceptance
sequence through the MCP client:

1. Request `list_documents` before creating anything and note the open and
   active documents already present in FreeCAD.
2. Request `create_document` with `name` `TestDocument` and label `MCP Test`.
   Confirm the result has `file_path: null`, `saved: false`, `modified: true`,
   `active: true`, and `object_count: 0`.
3. Request `list_documents`; confirm `TestDocument` is present in internal-name
   order and is identified as active.
4. Request `get_document` with `name` `TestDocument`; confirm the same summary
   fields and values are returned.
5. Request `save_document` for `TestDocument` with a disposable absolute path
   whose parent already exists, omit the extension, and leave `overwrite` false.
   Confirm `.FCStd` is appended, the file exists, and the result reports
   `saved: true` and `modified: false`. Confirm the label remains `MCP Test`
   rather than changing to the filename stem.
6. Change the document label in FreeCAD, then request `get_document`; confirm
   `modified: true`. Request `save_document` again with only the internal name,
   then confirm it uses the current path and returns `modified: false`.
7. In the FreeCAD GUI, create and save a disposable target document to a second
   `.FCStd` path, then close that target document. Request `save_document` for
   `TestDocument` using that existing path with `overwrite: false`; confirm the
   structured error code is `file_already_exists` and the target is unchanged.
8. Repeat the same save-as with `overwrite: true`; confirm success, the returned
   path is the requested target, and `modified` is false.
9. Request `save_document` to a path under a missing parent directory and confirm
   `parent_directory_not_found`; no directory should be created.

### Object Listing Verification

1. Create or open a document containing at least one object (such as a Part
   Design Body) in FreeCAD.
2. Call `list_objects` with the document's internal name.
3. Confirm the result returns `ok: true` with the correct `document_name`.
4. For an empty document, confirm `objects` is an empty list and the message is
   "No objects found."
5. For a populated document, confirm each object entry includes its internal
   `name`, visible `label`, `type_id`, `visibility`, `parent`, and `children`.
6. Hide an object in FreeCAD, call `list_objects` again, and confirm
   `visibility` changes to `false`.
7. Call `list_objects` with an unknown document name and confirm a structured
   `document_not_found` error is returned.
8. Call `list_objects` with an empty or whitespace-only name and confirm a
   `validation_error` is returned.
9. Confirm the document was not modified by any `list_objects` call (check
   FreeCAD's modified/saved state).

### Object Inspection Verification

1. Create or open a document containing at least one object with a known placement
   (such as a Part Design Body) in FreeCAD.
2. Call `get_object` with the document's internal name and the object's internal
   name.
3. Confirm the result returns `ok: true` with code `object_retrieved` and the
   correct `document_name`.
4. Confirm the flat `object` result includes `name`, `label`, `type_id`,
   `visibility`, `parent`, `children`, and `placement`.
5. Call `get_object` with an unknown object name and confirm the structured
   `object_not_found` error includes both `document_name` and `object_name`.
6. Call `get_object` with an unknown document name and confirm the existing
   `document_not_found` error is returned.
7. Move or rotate an object in FreeCAD, call `get_object` again, and confirm the
   placement position and rotation reflect the change.
8. Call `get_object` on an object without placement (if one exists in the test
   document) and confirm `placement` is `null`.

### Recompute Verification

1. Open a document in FreeCAD that contains computed features (such as a Part
   Design Body).
2. Call `recompute_document` with the document's internal name.
3. Confirm the result returns `ok: true` with code `document_recomputed`.
4. Confirm the returned `document` summary includes `name`, `label`,
   `file_path`, `saved`, `modified`, `active`, and `object_count`.
5. Modify a parameter in FreeCAD that requires recomputation, then call
   `recompute_document` and confirm the document's state updates accordingly.
6. Call `recompute_document` with an unknown document name and confirm the
   existing `document_not_found` error is returned.
7. Confirm the document was not saved by the recompute call (check FreeCAD's
   modified/saved state).

### Body Creation Verification

1. Start FreeCAD, select the MCP workbench, start the server.
2. Create a new unsaved document named `BodyTest` with `create_document`.
3. Call `create_body` with `document_name` `BodyTest`, `name` `MainBody`,
   and `label` `Main Body`. Confirm `ok: true`, `code: body_created`,
   `document_name: BodyTest`, and the `object` has `name: MainBody`,
   `label: Main Body`, `type_id: PartDesign::Body`.
4. Call `list_objects` on `BodyTest` and confirm the body appears with
   its correct name, label, and type. Confirm the object count is 1.
5. Call `get_object` with `document_name: BodyTest` and
   `object_name: MainBody` and confirm the returned detail matches
   the `create_body` result.
6. Verify in the FreeCAD GUI that the document is modified and the body
   exists with the correct label.
7. Call `create_body` again with the same `document_name` and `name` and
   confirm a structured `object_already_exists` error.
8. Call `create_body` with `name` `SecondBody` but the same `label`
   `Main Body` and confirm duplicate labels are allowed (object already
   exists error should NOT occur).
9. Call `create_body` with a non-existent document name and confirm
   `document_not_found`.
10. Call `create_body` without a `document_name` and confirm
    `validation_error`.
11. After each failed attempt, call `list_objects` and confirm the object
    count did not increase from a failed mutation.
12. Confirm no `create_body` toolbar button, menu item, or FreeCAD GUI
    command was added.
13. In the MCP client, confirm exactly seventeen tools are listed, including
    `create_body`, `create_sketch`, `get_sketch`, `add_sketch_geometry`, and
    `add_sketch_constraints`, with `create_sketch_centered_rectangle` last.

### create_sketch live acceptance

1. Start FreeCAD, select the MCP workbench, start the server.
2. Create a new unsaved document named `SketchTest` with `create_document`.
3. Call `create_body` to create a body named `MainBody` in `SketchTest`.
4. Call `create_sketch` with `document_name` `SketchTest`, `body_name` `MainBody`,
   `name` `BaseSketch`, and `label` `Base Sketch`. Confirm `ok: true`,
   `code: sketch_created`, `document_name: SketchTest`, `body_name: MainBody`,
   and the `object` has `name: BaseSketch`, `label: Base Sketch`,
   `type_id: Sketcher::SketchObject`, `parent: MainBody`, `children: []`.
5. Call `list_objects` on `SketchTest` and confirm the object count is 2
   (one body, one sketch). Confirm `BaseSketch` appears with the correct
   parent.
6. Call `get_object` with `document_name: SketchTest` and
   `object_name: BaseSketch` and confirm the returned detail matches
   the `create_sketch` result.
7. Verify in the FreeCAD GUI that the document is modified, the body exists
   with the sketch inside it, and the sketch is visible in the tree.
8. Verify the sketch is unattached: in the FreeCAD property editor, confirm
   `Support` is empty and `MapMode` is `Deactivated` or equivalent default.
9. Call `create_sketch` again with the same `document_name`, `body_name`,
   and `name` and confirm a structured `object_already_exists` error.
10. Call `create_sketch` with a non-existent body name and confirm
    `body_not_found`.
11. Call `create_sketch` with a non-body object (e.g. `App::Part`) as the
    body name and confirm `body_type_mismatch`.
12. Call `create_sketch` with `name` `SecondSketch` but the same `label`
    `Base Sketch` and confirm duplicate labels are allowed.
13. Call `create_sketch` with a non-existent document name and confirm
    `document_not_found`.
14. Call `create_sketch` without a `document_name` and confirm
    `validation_error`.
15. After each failed attempt, call `list_objects` and confirm the object
    count did not increase from a failed mutation.
16. Confirm no `MCP_CreateSketch` GUI command, toolbar button, or menu entry
    exists in the MCP workbench.
17. In the MCP client, confirm exactly seventeen tools are listed, including
    `create_sketch`, `get_sketch`, `add_sketch_geometry`, and
    `add_sketch_constraints`, with `create_sketch_centered_rectangle` last.
18. Call `create_sketch` with `support_plane: xy_plane` and confirm
    `attachment.kind: body_origin_plane`, `attachment.plane: xy_plane`,
    `attachment.map_mode: flat_face`.
19. Repeat with `xz_plane` and `yz_plane`.
20. Call `create_sketch` with `support_plane: XY_Plane` (wrong case) and
    confirm `validation_error`.
21. Call `create_sketch` with `support_plane: flat_face` (invalid value) and
    confirm `validation_error`.
22. Create a second body in the same document with `create_body`. Create an
    attached sketch on each body. Verify each sketch resolves that body's
    own origin plane.
23. In the FreeCAD property editor, verify `MapMode` is `FlatFace` and
    `AttachmentOffset` is identity for attached sketches.
24. Undo an attached sketch creation and verify the sketch and support are
    removed together. Redo restores both.

### get_sketch live acceptance

FreeCAD API behavior must be accepted through the complete production path:

```text
MCP client
→ live MCP endpoint
→ handler
→ Qt dispatcher
→ FreeCAD adapter
→ serialized response
```

Python-console commands may create controlled live fixtures, but all inspection
assertions must use `get_sketch` through the MCP endpoint. The completed live
acceptance covered line, circle, arc-of-circle, point, and construction
geometry; geometric and dimensional constraints; a valid unsupported B-spline;
standalone sketch ownership; rejection of a label used as an internal-name
alias; stale cached solver state; fresh solver state after an explicit external
recompute; and a complete before/after non-mutation comparison.

### add_sketch_geometry AiderDesk live acceptance plan

This milestone is not fully accepted until the separate AiderDesk run uses the
live endpoint for every mutation and `get_sketch` for every geometry readback.
FreeCAD's Python console may create disposable fixtures and record transaction,
undo, save, or timestamp state that is not exposed by an MCP inspection tool.

1. Start a fresh FreeCAD 1.1.1 session, install the development junction,
   start MCP, connect AiderDesk only to `http://127.0.0.1:8765/mcp`, and record
   Report View from server start through completion.
2. Discover tools and confirm the exact sixteen-name order. Confirm the first
   twelve remain unchanged, `get_sketch` is tenth, `add_sketch_geometry` is eleventh, and
   `add_sketch_constraints` is twelfth, with the first eleven names and schemas
   unchanged.
3. Inspect the eleventh tool schema. Confirm exactly three required top-level
   fields, a 1-to-100 array, the four discriminator mappings, every required
   item field, explicit Boolean construction, strict two-coordinate points,
   positive radii, degree angle fields, and forbidden extra item fields.
4. Create a disposable unsaved document and an empty standalone sketch.
   Snapshot `FileName`, modified state, transaction/undo/redo state, geometry
   and constraint counts, construction flags, and solver cache.
5. Through MCP, add one non-construction line to the empty sketch. Confirm code
   `sketch_geometry_added`, index `[0]`, counts, no file path, and no save.
   Read back only with `get_sketch` and compare every line coordinate and flag.
6. Through MCP, add one mixed ordered batch containing line, circle,
   circular arc, and point, with at least one construction item. Confirm
   contiguous indices, request order, geometry count, exact numeric readback,
   and construction parity through `get_sketch`.
7. Add another batch to the now-populated sketch and confirm returned indices
   continue from the previous geometry count. Treat them as temporary and use a
   fresh `get_sketch` response before any later index assertion.
8. Create a Part Design Body and an origin-plane-attached sketch. Repeat empty
   and mixed-batch mutation through MCP and confirm body ownership, attachment,
   placement, geometry order, and construction state remain intact.
9. Send empty and 101-item batches; malformed coordinates; missing required
   fields; nonnumeric and non-finite values; a zero-length line; zero and
   negative radii; equal, full-turn, and non-finite arc angles; unknown
   discriminator `ellipse`; and extra fields. Confirm controlled request errors,
   no mutation, and unchanged `get_sketch` output after every case.
10. Confirm negative and over-360 finite arc inputs normalize to the documented
    counter-clockwise span. Confirm 350→10 reads back as a 20-degree wraparound
    arc and 90→0 as a 270-degree arc.
11. Confirm duplicate and coincident valid geometry is accepted rather than
    rejected by speculative overlap checks.
12. For deterministic middle-item rollback, use the FreeCAD console only to
    install a temporary test patch around the focused `_build_geometry` helper
    that raises controlled `SketchGeometryCreationError` on the second item;
    restore the original helper in `finally`. Invoke a three-item batch through
    the MCP endpoint while the patch is active.
13. Confirm the injected call returns no partial success or index list. Use
    `get_sketch` plus the console snapshot to verify original geometry values,
    count, construction flags, constraints, transaction state, undo/redo state,
    and document save state are restored. Confirm no recompute, solve, save, or
    save-as call occurred.
14. Recompute explicitly before a successful mutation and record fresh solver
    data. Add geometry through MCP without recomputing, then call `get_sketch`;
    confirm the new geometry is present while solver facts are stale/null.
15. Call `recompute_document`, then `get_sketch`, and confirm the solver cache is
    fresh again. This establishes that mutation itself did not recompute.
16. Repeat a successful mutation on an unsaved document and confirm it remains
    unsaved. For a separately saved disposable document, record its path and
    disk timestamp, mutate, and confirm the path and timestamp are unchanged.
17. Compare complete before/after state for document transaction ownership,
    modified/file state, sketch geometry and construction, constraints,
    attachment, visibility, selection, edit mode, and solver cache. Only the
    requested appended geometry and expected dirty/stale state may differ.
18. Confirm none of `ellipse`, `arc_of_ellipse`, `arc_of_hyperbola`,
    `arc_of_parabola`, or `b_spline` is mutation-supported. Add one valid
    unsupported geometry fixture externally and confirm `get_sketch` still
    returns its controlled `unsupported` inspection record.
19. Close disposable documents without saving, remove the temporary failure
    patch if it was not already restored, stop the MCP server, and preserve the
    AiderDesk transcript plus Report View output as the acceptance evidence.

Do not claim live milestone acceptance from the automated or direct-adapter
smoke tests. The AiderDesk transcript must show endpoint mutation and
`get_sketch` readback for the successful, invalid, and rollback cases.

### Controlled Symmetry AiderDesk live acceptance plan

This Milestone 14A plan is prepared but is not executed by the implementation
task. Use only natural-language CAD requests and the sixteen exposed MCP tools.
The FreeCAD Python console may create clean disposable fixtures or record state
that MCP cannot expose, but it must not perform the accepted mutations. Make no
implementation edits, commit, or push.

1. Start a fresh FreeCAD 1.1.1 session, start MCP, connect AiderDesk only to the
   live endpoint, and preserve Report View plus the AiderDesk transcript.
2. Discover tools and confirm the exact sixteen-name order, with `get_sketch`
   tenth, `add_sketch_geometry` eleventh, `add_sketch_constraints` twelfth, and
   the three history tools at positions 13–15, and
   `create_sketch_rectangle` at position 16.
   Compare the first eleven schemas with their compatibility snapshots.
3. Inspect tool twelve: exactly three required top-level fields, a 1-to-100
   array, all 17 constraint mappings, strict point/whole-line/native references,
   and forbidden extra fields. Confirm no raw native identifiers are accepted.
4. Use one clean unsaved sketch per semantic scenario. Through natural-language
   requests, make selected points symmetric about the origin, horizontal axis,
   vertical axis, another selected geometry point, and a selected line segment.
5. Across those isolated sketches cover line start/end points, point geometry,
   circle centres, and circular-arc centres. After every mutation use
   `get_sketch` and verify `type: symmetric` with three controlled references in
   first/second/about order and no native negative IDs or point-position values.
6. Exercise a mixed valid constraint batch and verify ordering, contiguous
   indices, unchanged geometry/construction state, and no automatic save.
7. In a new empty sketch, ask Aider to create a 30 mm × 20 mm axis-aligned
   rectangle centred on the sketch origin and fully constrain it. Do not give a
   constraint recipe. Require one `create_sketch_rectangle` call translated to
   lower-left `(-15, -10)`, four non-construction lines, a closed profile, no
   helper geometry and—after explicit recompute—zero DoF and clean conflict,
   redundancy, partial-redundancy, and malformed diagnostics.
8. In separate fixtures, test missing/additional fields, raw/negative/stale
   indices, invalid point tokens, unsupported about geometry, identical selected
   points, a centre identical to a selected point, and own-line symmetry. Submit
   a valid first item followed by an invalid later item and confirm zero mutation.
9. With a temporary deterministic failure hook installed and restored in
   `finally`, verify a failure after one native symmetric addition rolls back the
   entire batch: constraints, geometry, construction, ownership, attachment,
   transaction state, and saved/unsaved state all match the baseline.
10. Confirm an unsaved fixture remains unsaved. For a separately saved
    disposable fixture, verify path, timestamp, and bytes are unchanged.
11. Confirm tangent, block, internal alignment, angle-via-point, arbitrary
    reference constraints, deletion/editing, external geometry, and generic
    mutation remain unavailable. Confirm no GUI command, toolbar item, or menu
    action was added and the repository is unchanged.
12. Stop MCP and close disposable documents without saving. Retain the schema,
    transcript, Report View, and before/after snapshots. Use the controlled MCP
    history tools, rather than manual GUI undo/redo, for covered checks.

### General Point Relationships AiderDesk live acceptance plan

This Milestone 14B plan is prepared but was not executed by the implementation
task. During acceptance, use only the sixteen exposed MCP tools: do not use the
FreeCAD Python console, edit implementation files, commit, or push. Because the
public inventory can create only body-owned sketches, prepare any required
standalone-sketch fixtures in the GUI before starting the recorded MCP session;
all inspection and mutation of those fixtures must then occur through MCP.

1. Start a fresh FreeCAD 1.1.1 session, start MCP, connect AiderDesk, and retain
   the protocol transcript plus Report View output.
2. Discover the raw tool inventory and confirm the exact sixteen-name order,
   with `get_sketch` tenth, `add_sketch_geometry` eleventh, and
   `add_sketch_constraints` twelfth. Confirm there is no new GUI command.
3. Inspect raw tool-twelve schema separately from modelling prompts: exactly
   three required top-level fields, a 1-to-100 array, 17 top-level variants,
   strict point/whole-geometry/native references, unchanged old variants, and
   forbidden additional fields, negative IDs, and native position integers.
4. Use one clean sketch per semantic scenario. Through natural-language
   modelling requests—not copied JSON recipes—ask separately for a point on a
   line, circle, and circular arc; a line endpoint on another line; a circle
   centre on a line; and an arc centre on a line. Include normal and existing
   construction line targets. Do not create helper geometry merely for axes.
5. In fresh sketches, naturally request horizontal alignment between two line
   endpoints and between mixed point kinds, then vertical alignment for the
   same two categories. Separately confirm whole-line horizontal and vertical
   remain distinct and unchanged.
6. Repeat representative ordinary-target and point-pair cases in a pre-created
   standalone sketch and in body-owned sketches created through MCP, including
   one sketch attached to a body origin plane and one unattached body sketch.
7. After every successful mutation call `get_sketch`. Verify
   `point_on_object` returns a selected point plus target `position: edge`,
   `horizontal_points`/`vertical_points` return two semantic points, axis
   membership remains controlled, geometry/construction/attachment state is
   unchanged, and no native negative ID or point-position integer appears.
8. Submit schema-negative cases separately: missing and extra fields, Boolean,
   negative and stale indices, integer or invalid point tokens, point-position
   data on a whole target, origin as target, raw axis IDs, identical point
   references, self-targets, point-geometry targets, and unsupported geometry.
   Compare `get_sketch` before and after every case to prove zero mutation.
9. Submit mixed ordered batches containing existing constraints and all three
   Milestone 14B capabilities. Verify contiguous returned indices, request
   order, exact count transitions, and controlled readback.
10. Submit each new valid form followed by a later invalid item. Verify the
    complete before/after `get_sketch` snapshots match and no partial result or
    point relationship remains.
11. For a deterministic post-add failure, use a prearranged test build or
    operator-controlled hook outside the MCP session, restore it in `finally`,
    and submit a mixed batch through MCP. Verify constraints, geometry,
    construction, Body ownership, support, map mode, transaction state, and
    saved/unsaved state all match the baseline.
12. In a fresh unsaved sketch, ask naturally for one 10 mm circle centred on
    the sketch origin, one point on the circle horizontally aligned with the
    circle centre, and a second point on the circle vertically aligned with the
    centre. Do not provide a constraint recipe or permit helper geometry or
    coordinate-dimension substitutes.
13. Inspect the cardinal-point result: exactly one circle and two point
    geometries, radius 10 mm, controlled origin coincidence, two ordinary
    `point_on_object` records, one `horizontal_points`, one `vertical_points`,
    no helper geometry, and no raw native IDs.
14. Call `recompute_document` before final solver assertions, then call
    `get_sketch` and require fresh diagnostics, zero DoF, fully constrained,
    and empty redundant, partially redundant, conflicting, and malformed lists.
15. Confirm the cardinal-point document remains unsaved. In a separate saved
    disposable fixture, record path, timestamp, and bytes before mutation and
    verify MCP does not save or alter the on-disk file.
16. Confirm tangency, semantic profiles, deletion, repair, external geometry,
    arbitrary mutation, and arbitrary Python remain unavailable.
17. Stop MCP and close disposable documents without saving. Confirm repository
    status is unchanged and retain the schema, transcript, state snapshots,
    solver results, and MCP history results as acceptance evidence.

### Controlled Document History AiderDesk Live Acceptance Prompt

This Milestone 14B-2 campaign is prepared here but is not executed by the
implementation task. Run it in a fresh FreeCAD 1.1.1 session with a dedicated
AiderDesk profile connected only to the MCP endpoint. All FreeCAD inspection
and mutation in the recorded campaign must use exposed MCP tools: do not use the
Python console, GUI undo/redo, arbitrary Python, implementation edits, or
unlisted tools. Before and after the campaign, the operator should record
`git status --short --branch`; no repository file, commit, branch, or remote may
change.

Copy this prompt into AiderDesk:

```text
Perform the controlled document-history acceptance campaign entirely through
the connected FreeCAD MCP server. Do not edit the repository, run Python, use
GUI undo/redo, commit, push, or create unrequested files. Use disposable,
uniquely named documents and report every raw tool result needed as evidence.

First request the raw tool inventory. Require exactly these seventeen tools in
this order:
create_document, list_documents, get_document, save_document, list_objects,
get_object, recompute_document, create_body, create_sketch, get_sketch,
add_sketch_geometry, add_sketch_constraints, get_document_history,
undo_document, redo_document, create_sketch_rectangle,
create_sketch_centered_rectangle.

Capture the raw input schemas for tools 13–15. get_document_history must require
only document_name. undo_document and redo_document must require document_name
and allow optional expected_transaction_name. They must reject extra fields,
including steps, count, history index, and transaction_id. Confirm none of the
first twelve schemas or descriptions changed.

Create a clean unsaved document and inspect its history before model mutation.
Require available controlled history with empty undo and redo stacks. Create a
Body and sketch, inspecting history after each successful operation. Require
the controlled top labels Create body and Create sketch. Undo and redo one known
creation step with expected_transaction_name and verify list_objects,
get_object, get_document, and history before and after.

In that same sketch, add one geometry item, then an ordered multi-geometry
batch. For each successful call, inspect history, undo exactly one Add sketch
geometry transaction, inspect the restored sketch, redo it, recompute, and
inspect again. Prove a batch is one step and restores every item together.
Repeat with one constraint and a mixed multi-constraint batch; require the top
label Add sketch constraints and exact one-step restoration.

Exercise expected-name safety in both directions. Call undo_document with a
deliberately wrong expected name, then call redo_document with a deliberately
wrong expected name after a valid undo. Require structured
undo_transaction_mismatch and redo_transaction_mismatch failures. Compare
history and sketch inspection before and after and prove both mismatches caused
zero mutation.

Create a second document with different geometry and history. Make document B
active if normal tool use does so, then undo a named step in document A. Prove
document B's geometry, constraints, object list, saved state, and history counts
are unchanged. All calls must identify the intended internal document name.

Create an origin-plane-attached sketch through create_sketch and exercise
geometry and constraint undo/redo there. Prove Body ownership, attachment kind,
plane, map mode, geometry, and controlled readback survive each history change.

Exercise Milestone 14A symmetry and Milestone 14B ordinary point_on_object,
horizontal_points, and vertical_points through successful operations followed
by controlled undo/redo. Recompute before final solver assertions. Require
controlled references only and reject any native negative ID, native point
position integer, transaction ID, transaction object, or raw stack entry in
every result.

Run the primary recovery scenario in one new body-owned sketch. Construct a
four-edge rectangle intended to be centred on the sketch origin. Deliberately
apply a technically valid symmetry batch to the wrong pair of endpoints.
Recompute and inspect; detect and explain why the result violates the intended
centre or orientation. Call get_document_history and require Add sketch
constraints at the top. Call undo_document with that exact expected name.
Inspect and prove the same sketch returned to its exact prior four-edge geometry
and constraint state. Before making a new mutation, prove redo refers to the
undone wrong constraint batch. Apply the corrected symmetry strategy in the
same sketch, recompute, and inspect the finished centred rectangle. Prove no
replacement sketch, duplicate geometry, helper, hidden abandoned sketch, or
second document was created. Prove the corrected new transaction invalidated
the previous redo entry.

This modelling-strategy scenario FAILS if you abandon or replace the original
sketch after the recoverable mistake without a clearly evidenced reason that
controlled in-place recovery was unsafe or unavailable.

Prove redo invalidation separately: perform operation A, undo A, confirm redo A,
perform new operation B, confirm redo count is zero, and require redo_document
to return redo_not_available.

For unsaved state, prove undo and redo keep file_path null and saved false. For
a separately saved disposable document, record the returned path and saved
state, make and undo/redo a later in-memory model transaction, and prove no
history call performs save_document or changes the controlled path. Do not
claim external file rollback; history does not reverse a save or overwritten
filesystem content.

After every undo or redo, inspect the affected document and sketch. Treat solver
facts as stale until recompute_document; after explicit recompute require fresh
solver diagnostics. Do not call undo after any failed atomic mutation that
already rolled back. If history shows an unexpected GUI or user transaction,
stop that scenario, report it, and ask for direction rather than undoing it.

Finish with the raw sixteen-tool inventory, raw schemas, every structured
success and expected failure code, document/sketch names, before/after history,
same-sketch recovery evidence, redo invalidation evidence, saved/unsaved and
cross-document evidence, confirmation that no native transaction IDs appeared,
and confirmation that no repository edit, commit, or push was performed. Stop
the MCP server and leave disposable documents clearly identified for cleanup.
```

The operator should retain the AiderDesk transcript, raw `tools/list`, raw
schemas, Report View output, before/after state records, and unchanged repository
status. Automated and direct-adapter smokes are supporting evidence, not a
substitute for this endpoint campaign. Future acceptance campaigns should use
these MCP history tools for covered undo/redo checks and should not require
manual GUI history actions.

### Controlled Direct Tangency AiderDesk Live Acceptance Prompt

This Milestone 14C prompt is prepared but is not executed by the implementation
task. Run it in a fresh FreeCAD 1.1.1 session with a dedicated FreeCAD Engineer
AiderDesk profile connected only to the MCP endpoint. Every document and sketch
operation must use an exposed MCP tool. Do not use the Python console, GUI
undo/redo, arbitrary Python, implementation edits, or unlisted tools. Record
`git status --short --branch` before and after; the repository, commits,
branches, and remotes must remain unchanged.

Copy this prompt into AiderDesk:

```text
Perform the controlled direct-tangency acceptance campaign entirely through
the connected FreeCAD MCP server. Do not edit the repository, run Python, use
GUI undo/redo, commit, push, or create unrequested files. Use uniquely named
disposable documents and preserve raw tool results as evidence.

First request the raw tool inventory. Require exactly these seventeen tools in
this order:
create_document, list_documents, get_document, save_document, list_objects,
get_object, recompute_document, create_body, create_sketch, get_sketch,
add_sketch_geometry, add_sketch_constraints, get_document_history,
undo_document, redo_document, create_sketch_rectangle,
create_sketch_centered_rectangle.

Capture the raw add_sketch_constraints schema. Require exactly seventeen
top-level constraint discriminators and prove all sixteen established members
are unchanged. The tangent member must have exactly this shape and no
additional properties:
{"type":"tangent","first":{"geometry_index":0},"second":{"geometry_index":1}}
Each reference must contain only one non-negative integer geometry_index. There
must be no point position, branch, side, contact, external/internal, or native
identifier field and no additional tangency tool.

In separate clean unsaved sketches, exercise direct line-circle, line-arc,
circle-circle external, circle-circle internal, circle-arc, and arc-arc
tangency. Exercise circle-line, arc-line, and arc-circle reverse heterogeneous
orders. Include a supported pair with construction geometry. Inspect after
explicit recompute and prove every public tangent item creates exactly one
native relationship, preserves request order and construction state, returns
one index, adds no helper geometry or substitute constraint, and reads back as
type tangent with exactly two controlled non-negative edge references in the
stored order. No result may expose a native geometry or point-position ID.

In fresh disposable sketches, require controlled zero-mutation failures for
same geometry, line-line, point geometry, unsupported pair/type if available,
out-of-range and negative indices, selected-point references, origin or axis
references, Boolean indices, additional fields, and branch/contact fields.
Submit a batch whose first item is valid tangent and whose later item is
invalid; compare complete before/after geometry, constraints, history, saved
state, and solver state and prove the whole request failed before mutation with
no partial indices. Do not call undo after this failed atomic request.

Create a second rollback batch where a later valid-looking tangent cannot be
accepted by the current sketch state. Require the controlled error and exact
restoration of every pre-existing geometry, construction flag, constraint,
history count, attachment fact, and saved/unsaved fact. If the endpoint cannot
inject a native constructor exception, report that limitation rather than
simulating arbitrary Python.

Repeat representative success, rejection, readback, and one-step history cases
in a body-owned sketch attached to a controlled origin plane. Prove Body
ownership, attachment kind, plane, map mode, and existing state survive. Keep
one campaign document unsaved and require file_path null and saved false. Save
a separate disposable document using save_document, then add tangency and
undo/redo it; prove the in-memory history operations do not invoke another save
or change the controlled path. Do not claim history reverses filesystem saves.

For one tangent operation, inspect Add sketch constraints at the top of
history, undo it with that exact expected name, and redo it with that exact
expected name. Prove exact geometry and controlled tangent restoration. Repeat
with a multi-tangent batch and prove the entire ordered batch is one undo/redo
step. Separately perform operation A, undo A, confirm redo A, perform operation
B, prove redo was invalidated, and require redo_document to return
redo_not_available. After every undo or redo, show stale solver facts before
recompute_document and fresh, clean facts after recompute.

Run an arc-domain case in which a line is tangent to the arc's underlying
circle but the mathematical contact is outside the arc's visible bounded
parameter interval. Use controlled geometry and solver readback to demonstrate
both facts. Report explicitly that direct arc tangency constrains the support
circle and that visible contact must be verified; do not infer endpoint joining.

Run this product test from engineering intent only. Devise the modelling
strategy yourself; do not treat this paragraph as a sequence of MCP calls:
"Create a circle of radius 10 mm centred on the sketch origin. Create a
horizontal line 30 mm long, centred on the vertical sketch axis, tangent to the
upper side of the circle. Fully constrain the sketch without helper geometry
or a coordinate offset dimension."
Accept it only with exactly two geometry elements, radius 10 mm, centre at the
origin, line length 30 mm, a horizontal line centred on the vertical axis at
y = +10 mm, top contact equivalent to (0, 10), zero DoF, fully constrained,
fresh clean solver diagnostics, one controlled tangent readback, no native IDs,
no helper or coordinate-offset dimension, and an unsaved document. Use the
smallest natural constraint set and explain any candidate constraint omitted as
redundant.

Run wrong-branch recovery in one fresh sketch. Add a circle and a line initially
below it, apply direct tangency, recompute, inspect coordinates, and prove the
lower branch is technically valid but violates upper-tangent intent. Inspect
history and undo the known Add sketch constraints transaction. If controlled
geometry replacement is needed because there is no geometry-edit tool, undo
the known Add sketch geometry transaction and add the corrected line above the
circle in the same sketch. Before the corrective mutation, show the available
redo; afterward prove it was invalidated. Reapply tangency, recompute, and prove
the upper branch. The scenario FAILS if the original sketch is abandoned or a
replacement sketch/document is created without a documented unrecoverable
reason. It also fails if an unknown GUI/user transaction is undone.

Finish with the raw sixteen-tool inventory, the seventeen discriminator names,
raw tangent schema, all supported and rejected pair evidence, construction and
attached-sketch evidence, atomic rollback snapshots, controlled readback,
saved/unsaved results, single and batch undo/redo, redo invalidation, solver
freshness, arc-domain finding, upper-tangent product result, same-sketch branch
recovery, and confirmation that no repository edit, commit, or push occurred.
Stop MCP and leave disposable documents clearly identified for cleanup.
```

Retain the AiderDesk transcript, raw `tools/list`, raw schemas, Report View
output, controlled before/after state, solver results, history snapshots, and
unchanged repository status. Automated tests and the 32-scenario adapter smoke
are supporting evidence, not a substitute for this live endpoint campaign.

### Semantic Rectangle AiderDesk Live Acceptance Prompt

This Milestone 15A prompt is prepared but is not executed by the implementation
task. It records the historical tool-16 acceptance contract and its pre-15B
centre translation product fixture; it is not current tool-selection guidance.
For a current centre-defined request use the Milestone 15B prompt linked above,
which requires tool 17 and explicitly forbids that translation. Use a fresh
FreeCAD 1.1.1 session and a FreeCAD Engineer AiderDesk profile connected only
to the MCP endpoint. Every CAD action and inspection must use an exposed MCP
tool; do not use the GUI Rectangle command, Python console, mouse simulation,
direct FreeCAD API, or repository edits.

Copy this prompt into AiderDesk:

```text
Perform the semantic axis-aligned rectangle acceptance campaign entirely
through the connected FreeCAD MCP endpoint. Preserve the repository: before
and after, record branch, HEAD, remotes, upstream, and git status; make no file
edit, stage, commit, push, pull, checkout, or cleanup action.

First request the raw tool inventory. Require exactly these sixteen tools in
this order: create_document, list_documents, get_document, save_document,
list_objects, get_object, recompute_document, create_body, create_sketch,
get_sketch, add_sketch_geometry, add_sketch_constraints,
get_document_history, undo_document, redo_document,
create_sketch_rectangle. Prove the first fifteen contracts are unchanged and
the add_sketch_constraints discriminator union still contains exactly the
established seventeen variants.

Capture the raw create_sketch_rectangle input schema. Require exactly
document_name, sketch_name, width, height, and placement; placement must contain
exactly type=lower_left, x, and y. Require additionalProperties=false at every
level, finite strict positive width/height, finite strict x/y, and rejection of
booleans. Prove centre/center, upper_right, rotation, angle, construction,
fully_constrain, helper geometry, profile IDs, and raw geometry/constraint IDs
are unavailable.

Use create_sketch_rectangle for every complete standard axis-aligned rectangle.
Use add_sketch_geometry only for deliberate unrelated pre-existing geometry or
an incomplete/custom arrangement, and add_sketch_constraints only to establish
deliberate pre-existing relationships. The campaign FAILS if a standard
rectangle is manually reconstructed with primitive calls without a documented
unrecoverable semantic-tool failure. Never call one MCP tool from another and
never invoke a GUI command.

In isolated unsaved sketches, create a 30 × 20 rectangle at lower-left (0, 0),
a positive non-zero placement, a negative non-zero placement, and a mixed-sign
placement. Recompute and inspect each. Require four normal lines in exact order:
bottom lower-left→lower-right, right lower-right→upper-right, top
upper-right→upper-left, left upper-left→lower-left. Require the result edge map
bottom/right/top/left and corner map lower_left/lower_right/upper_right/
upper_left to point to those exact endpoints, including when indices are not
zero. Require exact requested dimensions and placement, exact derived
upper-right, closed=true, axis_aligned=true, fully_constrained=true, zero DoF,
and empty conflicting, redundant, partially redundant, and malformed lists.
Require no helper or construction geometry.

Create a sketch containing unrelated normal and construction geometry plus a
controlled pre-existing constraint. Snapshot complete geometry, coordinates,
constraint readback, construction flags and indices. Append a rectangle and
prove all earlier content is byte-for-byte-equivalent at the controlled data
level and the profile maps only new indices. Undo exactly Create sketch
rectangle, recompute and inspect, and prove the complete snapshot is restored;
redo exactly that step and prove the rectangle returns fully constrained.

Create a Body-owned XY-plane-attached sketch and add a rectangle. Across
creation, exact-name undo, recompute, exact-name redo, and recompute, prove Body
ownership, support plane, attachment, MapMode, placement, sketch identity and
absence of a duplicate top-level sketch are preserved.

For an unsaved document, prove file_path remains null across creation,
undo and redo. For a disposable explicitly saved document, record path, file
size, timestamp and controlled modified state. Without calling save_document,
create, undo and redo a rectangle and prove the external bytes, size and
timestamp never change. Report native in-memory modified state without claiming
that undo reverses a save.

After a successful rectangle, inspect history and require one top transaction
named exactly Create sketch rectangle. Call undo_document first with a
deliberately wrong expected name and prove zero geometry, constraint and history
mutation. Then undo with the exact name and prove all four edges and all new
constraints disappear in one step while the sketch and earlier content remain.
Redo with the exact name and prove the complete profile returns. Undo again,
perform a new controlled mutation, and prove redo is invalidated.

Exercise rejected zero/negative dimensions, boolean and non-finite numbers,
unknown placement type, missing fields, and extra top-level/nested fields.
For every structured failed call, compare complete before/after sketch,
document and history state and prove zero mutation and no new undo entry. Do
not call undo after such a failure.

Natural-language product test: “Create a 30 mm × 20 mm axis-aligned rectangle
centred on the sketch origin.” Do not supply geometry indices or a primitive
recipe. The agent must choose create_sketch_rectangle once and translate the
intent to lower-left (-15, -10), width 30, height 20. Prove bottom
(-15,-10)→(15,-10), right (15,-10)→(15,10), top (15,10)→(-15,10), left
(-15,10)→(-15,-10), full constraint, clean diagnostics, no helpers, and one
Create sketch rectangle transaction. Do not claim center placement exists.

Same-sketch recovery test: create a correct-size rectangle at a deliberately
wrong lower-left point, recompute and prove it is valid but strategically
misplaced, inspect history, match and undo Create sketch rectangle, and prove
all its geometry/constraints are gone while the original sketch and earlier
content remain. Create the corrected rectangle in the same sketch, recompute
and inspect it, prove the old redo is invalidated, and prove there is no
replacement sketch or abandoned rectangle. The campaign FAILS if recovery
abandons the sketch.

Finish with raw tools/list and schemas, all structured success and expected
failure results, edge/corner mappings, solver and history snapshots, attached
and non-empty preservation evidence, saved/unsaved evidence, centred product
and same-sketch recovery evidence, Report View output, exact repository status,
and confirmation that no edit, commit or push occurred. Stop MCP and leave
disposable documents clearly identified for cleanup.
```

Retain the AiderDesk transcript, raw `tools/list`, raw schemas, Report View
output, controlled before/after snapshots, solver and history results, saved
file metadata, and unchanged repository status. The automated suite and
35-scenario embedded-runtime smoke are supporting evidence, not substitutes for
this separate live endpoint campaign.

### Sketch index semantics

Geometry and constraint indices describe the current sketch state. Current add
operations and future editing or deletion operations may renumber them, so
clients must call `get_sketch` after each mutation before issuing another
index-based request. Geometry tags are not exposed as permanent public identity,
and the project does not add UUID properties to sketch geometry.

The original create-only smoke prompt remains useful:

```text
Use the MCP create_document tool to create a document named TestDocument with the label "MCP Test".
```

For a fresh run, choose another internal name if `TestDocument` is already open.
Also verify an invalid internal name, an unknown `get_document` name, and a
duplicate create return structured errors. Stop and restart the server in the
same FreeCAD session and reconnect the client. Finally, close FreeCAD while the
server is running and confirm shutdown completes without an orphaned server
thread or process.

Dispatcher timeouts distinguish queued work cancelled before execution from work
that already started. Cancelled queued work is skipped when Qt later delivers
it. FreeCAD work already running cannot be terminated safely; after that timeout,
inspect document state before retrying a mutation because it may still complete.

Report View writes one JSON object per explicit command, prefixed with `[MCP]`.
Startup remains quiet unless bootstrap initialization fails.

If startup fails, record the complete Report View traceback and this console
output:

```python
import sys
print(sys.version)
print(App.getUserAppDataDir())
```
