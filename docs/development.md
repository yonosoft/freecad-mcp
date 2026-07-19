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
- MCP schemas, descriptions, and delegation belong in
  `test_mcp_document_tools.py`, `test_mcp_object_tools.py`, or
  `test_mcp_creation_tools.py`; the exact geometry union and tool-eleven
  contract belong in `test_mcp_sketch_geometry_tools.py`, while the strict
  nested constraint union and tool-twelve contract belong in
  `test_mcp_sketch_constraint_tools.py`; server composition,
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
the exact 14-member top-level constraint schema. Symmetric coverage locks all
five `about` forms, every supported point token, strict whole-line references,
degenerate-reference rejection, and preservation of every preceding union
member.

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

Controlled symmetry adapter tests lock both verified native constructor forms,
origin and both axes, geometry-point and line-segment centres, complete-batch
validation before a transaction, native failure rollback, and controlled
readback without raw IDs. The centred-rectangle regression uses four lines,
four endpoint coincidences, two horizontal and two vertical constraints, 30 mm
and 20 mm whole-line dimensions, and one origin symmetry. The direct FreeCAD
run proves zero DoF and clean conflict/redundancy/malformed diagnostics.

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

### Native Sketch Reference Live Acceptance Plan (Not Executed Here)

Use a focused AiderDesk MCP profile only after automated checks and the direct
adapter smoke pass:

1. Record `git status --short --branch` and preserve the repository without
   edits, commits, pulls, pushes, or generated files.
2. Discover tools and verify the exact unchanged twelve-tool order, with
   `add_sketch_constraints` still tool twelve.
3. Capture the exact updated schema: 14 constraint mappings; strict geometry
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
13. In the MCP client, confirm exactly twelve tools are listed, including
    `create_body`, `create_sketch`, `get_sketch`, `add_sketch_geometry`, and
    `add_sketch_constraints`.

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
17. In the MCP client, confirm exactly twelve tools are listed, including
    `create_sketch`, `get_sketch`, `add_sketch_geometry`, and
    `add_sketch_constraints`.
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
2. Discover tools and confirm the exact twelve-name order. Confirm
   `get_sketch` is tenth, `add_sketch_geometry` is eleventh, and
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
task. Use only natural-language CAD requests and the twelve exposed MCP tools.
The FreeCAD Python console may create clean disposable fixtures or record state
that MCP cannot expose, but it must not perform the accepted mutations. Make no
implementation edits, commit, or push.

1. Start a fresh FreeCAD 1.1.1 session, start MCP, connect AiderDesk only to the
   live endpoint, and preserve Report View plus the AiderDesk transcript.
2. Discover tools and confirm the exact twelve-name order, with `get_sketch`
   tenth, `add_sketch_geometry` eleventh, and `add_sketch_constraints` twelfth.
   Compare the first eleven schemas with their compatibility snapshots.
3. Inspect tool twelve: exactly three required top-level fields, a 1-to-100
   array, all 14 constraint mappings, strict point/whole-line/native references,
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
   constraint recipe. Verify four non-construction lines, a closed profile,
   controlled origin-symmetry readback, no helper geometry or signed corner
   dimensions, and—after explicit recompute—zero DoF and clean conflict,
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
    transcript, Report View, and before/after snapshots. Because MCP exposes no
    undo/redo tool, leave one-step GUI undo and redo as a clearly separate manual
    check rather than claiming it from the MCP transcript.

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
