# MCP

MCP is a Python-based external FreeCAD workbench that hosts a local Model
Context Protocol server inside FreeCAD. It exposes explicit typed CAD tools and
shared command handlers rather than arbitrary Python execution.

## Current Maturity

This repository is at its first functional MCP server milestone. It provides:

- a discoverable external FreeCAD workbench named **MCP**;
- start, stop, and status toolbar/menu commands for the embedded server;
- a local Streamable HTTP server at `http://127.0.0.1:8765/mcp`;
- typed MCP document tools for creating, listing, inspecting, and saving documents, and creating PartDesign bodies;
- shared handlers used by both MCP and FreeCAD GUI adapters;
- Windows development install scripts;
- Python quality tooling and unit tests.

The milestone intentionally has no configuration panel, remote binding, or
arbitrary Python execution.

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

The embedded server also requires `mcp>=1.27.2,<2` in FreeCAD's Python
environment. For the current FreeCAD 1.1 Windows development setup, install it
once into FreeCAD's per-user package directory:

```powershell
& "C:\Program Files\FreeCAD 1.1\bin\python.exe" -m pip install `
  --target "$env:APPDATA\FreeCAD\v1-1\AdditionalPythonPackages\py311" `
  "mcp>=1.27.2,<2"
```

On Windows, the current development install links FreeCAD's user addon folder:

```text
%APPDATA%\FreeCAD\v1-1\Mod\mcp -> <repository>\src
```

Run:

```powershell
.\scripts\install-dev.ps1
```

Restart FreeCAD, select **MCP**, and use **Start Server**, **Stop Server**, or
**Report Status**. Configure an MCP client with:

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

Available document tools:

- `create_document` creates a new unsaved document from a required internal
  `name` and optional visible `label`;
- `list_documents` lists open documents and identifies the active document;
- `get_document` inspects one document by its internal name;
- `save_document` persists a document using protected save or save-as behavior.
- `list_objects` returns controlled summaries of all objects in an open FreeCAD
  document: internal name, visible label, type ID, visibility, parent container,
  and children.
- `get_object` retrieves one object by exact internal document name and exact
  internal object name, returning its summary fields plus controlled placement
  data.

- `recompute_document` recomputes one open document and returns its updated
  controlled summary.
- `create_body` creates one empty Part Design Body in an open document. It requires exact internal document and object names, applies an optional visible label, opens a FreeCAD transaction, creates the body, recomputes, commits, and returns the controlled object detail with placement. Duplicate internal names are rejected. The tool does not save automatically or create sketches or features.

Tool names the MCP client can see:

```text
create_document
list_documents
get_document
save_document
list_objects
get_object
recompute_document
create_body
```

These document and object-inspection tools are MCP-only capabilities. They do not
add workbench commands or toolbar icons. `get_object` performs exact internal-name
lookup only; labels are not used as lookup keys. If placement is unavailable the
``placement`` field returns ``null`` rather than failing the entire tool.

## Documentation

- [Architecture](docs/architecture.md)
- [Development setup](docs/development.md)

## License

LGPL-2.1-or-later. See [LICENSE](LICENSE).
