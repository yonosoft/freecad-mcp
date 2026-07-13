# MCP

MCP is a Python-based external FreeCAD workbench that will host a local Model
Context Protocol server inside FreeCAD. The project exposes explicit typed CAD
tools and shared command handlers rather than arbitrary Python execution.

## Current Maturity

This repository is at the bootstrap milestone. It currently provides:

- a discoverable external FreeCAD workbench named **MCP**;
- one toolbar/menu command, **Report MCP Status**;
- a shared pure-Python command handler and a FreeCAD GUI adapter;
- Windows development install scripts;
- Python quality tooling and unit tests.

No MCP server or CAD-modifying MCP tool is implemented yet. The first planned
MCP tool is `create_document`.

## Repository Layout

```text
freecad-mcp/
|-- docs/
|-- scripts/
|-- src/
|   |-- Init.py
|   |-- InitGui.py
|   |-- package.xml
|   |-- Resources/
|   `-- freecad_mcp/
`-- tests/
```

`src` is the installable FreeCAD addon root. The Python import package remains
`freecad_mcp`.

## Quick Development Setup

Use Python 3.11 for local tooling:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\scripts\test.ps1
```

On Windows, the current development install links FreeCAD's user addon folder:

```text
%APPDATA%\FreeCAD\v1-1\Mod\mcp -> <repository>\src
```

Run:

```powershell
.\scripts\install-dev.ps1
```

Restart FreeCAD, select the **MCP** workbench, click **Report MCP Status**, and
confirm Report View contains:

```text
[MCP] Workbench command is active; shared command dispatch succeeded.
```

## Documentation

- [Architecture](docs/architecture.md)
- [Development setup](docs/development.md)

## License

LGPL-2.1-or-later. See [LICENSE](LICENSE).
