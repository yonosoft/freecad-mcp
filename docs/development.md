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
6. Confirm the four toolbar commands are visible.
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
```

The last three are MCP-only; the workbench still has no matching toolbar or menu
commands. Run this disposable acceptance sequence through the MCP client:

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
   `saved: true` and `modified: false`.
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

The original create-only smoke prompt remains useful:

```text
Use the MCP create_document tool to create a document named TestDocument with the label "MCP Test".
```

For a fresh run, choose another internal name if `TestDocument` is already open.
Also verify an invalid internal name, an unknown `get_document` name, and a
duplicate create return structured errors. Stop and restart the server in the
same FreeCAD session, reconnect the client, and close FreeCAD with the server
running to confirm there is no separate or orphaned server process.

Report View writes one JSON object per explicit command, prefixed with `[MCP]`.
Startup remains quiet unless bootstrap initialization fails.

If startup fails, record the complete Report View traceback and this console
output:

```python
import sys
print(sys.version)
print(App.getUserAppDataDir())
```
