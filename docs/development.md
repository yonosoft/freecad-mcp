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

Confirm the client lists exactly these document tools:

```text
create_document
list_documents
get_document
save_document
list_objects
get_object
recompute_document
```

These document and object-inspection tools are MCP-only; the workbench has no
matching document toolbar or menu commands. Connect the dedicated Aider MCP test
project and confirm
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
13. In the MCP client, confirm exactly nine tools are listed, including
    `create_body` and `create_sketch`.

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
17. In the MCP client, confirm exactly nine tools are listed, including
    `create_sketch`.
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
