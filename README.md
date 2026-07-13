# FreeCAD MCP

A Python-based, installable FreeCAD workbench intended to host a local Model Context Protocol (MCP) server inside FreeCAD. The project will expose explicit typed CAD tools, not arbitrary Python execution.

## Current maturity

**Bootstrap milestone only.** The repository currently provides:

- a discoverable external FreeCAD workbench;
- one toolbar/menu command named **Report MCP Status**;
- a shared pure-Python command handler and a FreeCAD GUI adapter;
- Windows development-junction scripts;
- Python quality tooling and unit tests;
- Eclipse/PyDev and AiderDesk setup documentation.

No MCP server or CAD-modifying MCP tool is implemented yet. The first planned MCP tool is `create_document`.

## Repository layout

```text
FreeCAD-MCP/
├── .aider-desk/agents/          Project-level reusable Python agent profile
├── docs/                        Architecture and development documentation
├── scripts/                     Windows development-link and test scripts
├── src/FreeCADMCP/              Installable FreeCAD addon root
│   ├── Init.py                  FreeCAD application-mode bootstrap
│   ├── InitGui.py               Workbench registration
│   ├── package.xml              Addon metadata
│   ├── freecad_mcp/             Python implementation package
│   └── Resources/icons/         Workbench and command SVG icons
└── tests/                       Pure-Python unit tests
```

The extra `FreeCADMCP` directory under `src` is deliberate: FreeCAD requires `Init.py` and `InitGui.py` at the addon root, while the implementation remains in the importable `freecad_mcp` package beneath that root.

## Development installation on Windows

Keep the repository in a normal development folder. From PowerShell in the repository root:

```powershell
.\scripts\install-dev.ps1
```

This creates a directory junction:

```text
%APPDATA%\FreeCAD\Mod\FreeCADMCP
    -> <repository>\src\FreeCADMCP
```

The script refuses to overwrite an ordinary directory. It only replaces an existing reparse point when `-Force` is supplied.

Remove the link with:

```powershell
.\scripts\uninstall-dev.ps1
```

No source files are copied. Edits made in Eclipse are visible to FreeCAD after the affected modules are reloaded or, for the initial workflow, after FreeCAD is restarted.

## Minimal FreeCAD test

1. Close FreeCAD.
2. Run `scripts\install-dev.ps1`.
3. Start FreeCAD 1.1 or later.
4. Open **View → Panels → Report View**.
5. Select **FreeCAD MCP** in the workbench selector.
6. Click **Report MCP Status** on the toolbar or in the **FreeCAD MCP** menu.
7. Confirm Report View contains:

```text
[FreeCAD MCP] Workbench command is active; shared command dispatch succeeded.
```

If the workbench is absent, inspect Report View for import errors and run this in FreeCAD's Python console:

```python
App.getUserAppDataDir()
```

Confirm that its `Mod\FreeCADMCP` entry is the junction created by the script.

## Python development environment

Use external CPython 3.11 for tests, linting, type checking, and Eclipse analysis. Do not install development tools into FreeCAD's embedded Python environment.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\scripts\test.ps1
```

Package installation is a user-controlled setup action. The scripts never install packages automatically.

## Eclipse and AiderDesk

Use a separate Eclipse workspace, for example:

```text
C:\Users\Goran\eclipse-workspace-freecad
```

Detailed PyDev configuration, source folders, FreeCAD import handling, and manual runtime testing are in [`docs/development.md`](docs/development.md).

A project-level **Python Engineer – Power Tools** profile template is stored under `.aider-desk/agents/python-engineer-power-tools`. Select a provider and model in AiderDesk after importing/opening the profile. FreeCAD-specific rules remain in [`AGENTS.md`](AGENTS.md), keeping the profile reusable for other Python repositories.

## Planned embedded MCP architecture

The future MCP transport will run locally inside FreeCAD. Transport adapters and toolbar commands will dispatch to the same command application layer. CAD mutations will be marshalled to FreeCAD's main Qt thread, wrapped in document transactions, recomputed, validated, and returned as structured results.

See [`docs/architecture.md`](docs/architecture.md) for the component boundaries and the planned `create_document` flow.

## License

LGPL-2.1-or-later. See [`LICENSE`](LICENSE).

## Packaging status

The current milestone is a junction-based development install. Addon Manager publication and release packaging are intentionally deferred; the addon root is already self-contained to make that later work straightforward.
