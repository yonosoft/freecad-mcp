# Development setup

## Prerequisites

- Windows 10 or 11.
- FreeCAD 1.1 or later.
- Git.
- Eclipse with PyDev.
- External CPython 3.11 for development tools.
- AiderDesk when agent-assisted development is required.

FreeCAD 1.1.x release packages use Python 3.11, so external Python 3.11 is the closest development-tooling match. Always confirm the exact embedded version in the installed build from FreeCAD's Python console:

```python
import sys
print(sys.version)
```

Do not assume packages installed into system Python or `.venv` are available inside FreeCAD.

## Repository and virtual environment

From PowerShell:

```powershell
git clone <repository-url> FreeCAD-MCP
cd FreeCAD-MCP
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\scripts\test.ps1
```

The repository scripts never install packages automatically.

## Development junction

Run:

```powershell
.\scripts\install-dev.ps1
```

Default link:

```text
%APPDATA%\FreeCAD\Mod\FreeCADMCP
```

Default target:

```text
<repository>\src\FreeCADMCP
```

A directory junction is used because it works on normal Windows installations without enabling Developer Mode or granting symbolic-link privileges. The source remains in the repository; there is no copy step.

To remove it:

```powershell
.\scripts\uninstall-dev.ps1
```

Both scripts refuse to delete an ordinary directory at the link location.

## Eclipse/PyDev without affecting ESP32

### Separate workspace

Start Eclipse and select a separate workspace such as:

```text
C:\Users\Goran\eclipse-workspace-freecad
```

Do not open or convert the existing ESP32 workspace. Eclipse workspaces keep project metadata, perspectives, launch configurations, and toolchain settings separate.

### Install PyDev

Use **Help → Eclipse Marketplace**, search for **PyDev**, install it, and restart Eclipse. This adds Python tooling; it does not change the ESP32 C++ compiler or project settings.

### Configure the interpreter

1. Create `.venv` with external CPython 3.11 as shown above.
2. Open **Window → Preferences → PyDev → Interpreters → Python Interpreter**.
3. Add `<repository>\.venv\Scripts\python.exe` and name it `FreeCAD-MCP Python 3.11`.
4. Keep the detected standard-library and site-packages paths.

Use the external virtual environment for code analysis and tests. Do not select `FreeCAD.exe` as the initial PyDev interpreter. FreeCAD runtime testing is performed by launching FreeCAD itself.

### Create the PyDev project from existing sources

1. Choose **File → New → Project → PyDev → PyDev Project**.
2. Project name: `FreeCAD-MCP`.
3. Clear **Use default** and point **Project contents** to the existing Git repository.
4. Choose Python grammar 3.11 and interpreter `FreeCAD-MCP Python 3.11`.
5. Finish without creating another repository or copying sources.
6. In project properties, set `src/FreeCADMCP` as a PyDev source folder.
7. Optionally set `tests` as an additional source folder for test navigation.

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

Eclipse `.project`, `.pydevproject`, `.settings`, and workspace `.metadata` are intentionally ignored so local IDE configuration does not become repository policy.

### FreeCAD-specific imports

Modules such as `FreeCAD`, `FreeCADGui`, `Part`, and `Sketcher` are supplied by FreeCAD's embedded runtime. They generally cannot be imported safely by an unrelated system Python because compiled modules and DLL search paths are tied to the FreeCAD installation.

Use these practices:

- keep FreeCAD imports inside adapter modules or function bodies;
- keep schemas, validation, dispatch, and result objects in pure-Python modules;
- use narrow `# type: ignore[import-not-found]` comments where an adapter must import a FreeCAD module;
- do not add FreeCAD as a pip dependency;
- do not add the entire FreeCAD installation to the external interpreter unless a tested local setup proves compatible.

For PyDev editor warnings, **Forced Builtins** can be tried for `FreeCAD`, `FreeCADGui`, `Part`, and `Sketcher`, but PyDev may be unable to inspect them from external Python. If that occurs, use PyDev predefined completions or project-local type stubs later rather than forcing runtime imports into `.venv`.

### Run and debug model

- Pure Python tests and quality tools run under `.venv`.
- Workbench startup, FreeCAD API behavior, Qt behavior, and document mutation run inside FreeCAD.
- The ordinary loop is:

```text
Edit in Eclipse
→ run scripts/test.ps1 for pure code
→ restart FreeCAD
→ select FreeCAD MCP workbench
→ inspect Report View
→ run the current command
```

Python module reload can be introduced later for selected pure modules, but restarting FreeCAD is the reliable baseline while workbench lifecycle code is changing.

### Report View

In FreeCAD, enable **View → Panels → Report View**. Also enable redirection of Python output/errors in FreeCAD preferences when diagnosing startup failures.

### Optional remote debugging later

Remote debugging is not required for the bootstrap milestone. Later, a compatible `pydevd` package can be made available to FreeCAD's embedded Python and invoked from a deliberate debug-only command. The version must match the installed PyDev debugger protocol, startup must never block normal FreeCAD use, and the debug listener must bind locally unless explicitly configured otherwise.

Do not install `pydevd` into FreeCAD automatically. Document the exact FreeCAD Python package location and obtain approval before changing it.

## Manual milestone test

1. Exit every FreeCAD process.
2. In repository PowerShell, run `.\scripts\install-dev.ps1`.
3. Verify the script prints both link and target paths.
4. Start FreeCAD.
5. Enable **View → Panels → Report View**.
6. Select **FreeCAD MCP** from the workbench selector.
7. Confirm a toolbar named **FreeCAD MCP** appears with one icon.
8. Click **Report MCP Status**.
9. Confirm this message appears:

```text
[FreeCAD MCP] Workbench command is active; shared command dispatch succeeded.
```

10. Close FreeCAD and run `.\scripts\uninstall-dev.ps1` only when the development link is no longer wanted.

If startup fails, record the complete Report View traceback and the output of:

```python
import sys
print(sys.version)
print(App.getUserAppDataDir())
```

## AiderDesk profile

A reusable profile template is committed at:

```text
.aider-desk\agents\python-engineer-power-tools\
```

AiderDesk supports project profiles in `{projectDir}/.aider-desk/agents/`. The included profile deliberately leaves provider, model, and project directory blank because those values are machine/account-specific. Open the profile in AiderDesk settings and select them before first use.

The profile uses Power Tools and Aider tools, allows read/search and targeted editing, asks before shell commands, new-file writes, Aider prompts, network fetches, or delegation, and disables automatic subagent delegation. The full generic behavior is in the profile's `rules/python-engineer.md`.

Project-specific FreeCAD and MCP constraints are in the repository root `AGENTS.md`, which AiderDesk reads as project context.

### Engineer versus manager profile

Use **Python Engineer – Power Tools** as the initial default. It directly inspects, edits, tests, and maintains the repository with fewer orchestration layers. A manager profile becomes worthwhile only after provider/model selection, subagent quality, task isolation, and delegation approval behavior have been verified on this installation. At that point, create a separate manager profile that delegates bounded tasks to this engineer rather than replacing it.

## Release packaging

This milestone validates the junction-based development install. Addon Manager publication and distributable release packaging are future tasks. Keep `src/FreeCADMCP` self-contained so it can later be packaged without relying on the monorepo layout.
