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
run the current command
```

## Report View Verification

In FreeCAD, enable **View -> Panels -> Report View**. Also enable redirection of
Python output/errors in FreeCAD preferences when diagnosing startup failures.

Manual bootstrap check:

1. Exit every FreeCAD process.
2. Run `.\scripts\install-dev.ps1`.
3. Start FreeCAD.
4. Open Report View.
5. Select the **MCP** workbench.
6. Click **Report MCP Status**.
7. Confirm Report View contains:

```text
[MCP] Workbench command is active; shared command dispatch succeeded.
```

If startup fails, record the complete Report View traceback and this console
output:

```python
import sys
print(sys.version)
print(App.getUserAppDataDir())
```
