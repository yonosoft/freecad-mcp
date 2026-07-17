# FreeCad MCP

FreeCad Context Protocol server inside FreeCAD. It exposes explicit typed CAD tools and
shared command handlers rather than arbitrary Python execution.

## Current Maturity

This repository is in active early-stage development. It provides controlled
document and object inspection plus body and sketch creation; it is not yet a
complete Part Design or Sketcher automation API, and it is not production-ready.

Current capabilities include:

- a discoverable external FreeCAD workbench named **MCP**;
- start, stop, and status toolbar/menu commands for the embedded server;
- a local Streamable HTTP server at `http://127.0.0.1:8765/mcp`;
- typed MCP tools for document creation, inspection, saving, recomputation, and
  controlled Part Design body and sketch creation, plus read-only sketch
  inspection;
- shared handlers used by both MCP and FreeCAD GUI adapters;
- Windows development install scripts;
- pure-Python quality tooling and unit tests, with documented live FreeCAD
  acceptance checks.

The project intentionally has no configuration panel, remote binding, or
arbitrary Python execution.

The repository is mirrored on [GitHub](https://github.com/yonosoft/freecad-mcp)
and [Codeberg](https://codeberg.org/aeromaker/freecad-mcp).

## Verified Environment

The currently verified live environment is FreeCAD `1.1.1.20260414` with
embedded Python `3.11.15` and PySide6 / Qt `6.8.3`. The MCP SDK uses stable v1
(`>=1.27.2,<2`). Pure-Python automated checks run with standalone Python 3.11;
live FreeCAD acceptance remains a manual check.

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

The exact tool names and order are defined by the authoritative
`src/freecad_mcp/tool_registry.py` registry:

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
```

`create_body` requires exact internal document and body names, accepts an
optional visible label, creates one `PartDesign::Body` in a transaction,
recomputes, and returns a structured controlled result. It does not save
automatically, create sketches or features, or add a toolbar/menu command.

`create_sketch` requires exact internal document, body, and sketch names and
accepts an optional visible label. It creates one empty body-owned sketch. Its
optional `support_plane` is limited to `xy_plane`, `xz_plane`, or `yz_plane`;
omitted or `null` means unattached. Attached sketches resolve the target body's
origin plane by semantic role and use controlled `flat_face` attachment. It
does not accept arbitrary faces or datum planes, alter attachment offsets, add
geometry or constraints, enter sketch edit mode, save automatically, or add a
toolbar/menu command.

### get_sketch

`get_sketch` performs controlled, read-only inspection using the required
`document_name` and `sketch_name` inputs. Both are exact internal names; visible
labels are not lookup aliases. The result contains sketch identity, owning body
when present, visibility, placement, controlled attachment data, geometry,
constraints, and cached solver facts. Raw FreeCAD objects and arbitrary
property maps are never returned.

Version-one geometry support is `line_segment`, `circle`, `arc_of_circle`, and
`point`. Geometry remains in current sketch-index order and includes its
construction state. The supported constraint discriminators are `coincident`,
`horizontal`, `vertical`, `parallel`, `perpendicular`, `equal`, `distance`,
`distance_x`, `distance_y`, `radius`, `diameter`, and `angle`. Valid geometry or
constraints outside those sets are returned as controlled `unsupported`
records rather than failing the entire sketch.

Lengths use `millimeter` and angles use `degree`. Solver facts come only from
FreeCAD's cached properties: they are populated when the sketch state is up to
date and nullable when that cache is stale. Inspection creates no transaction,
performs no save, and does not implicitly solve or recompute the sketch.
Geometry and constraint indices describe only the current sketch state; they
are not permanent identifiers and clients must inspect again after later
mutations.

These document, object, and sketch-inspection tools are MCP-only capabilities.
They do not add workbench commands or toolbar icons. `get_object` performs exact
internal-name lookup only; labels are not used as lookup keys. If placement is
unavailable the ``placement`` field returns ``null`` rather than failing the
entire tool.

## Documentation

- [Architecture](docs/architecture.md)
- [Development setup and CI](docs/development.md)

## License

LGPL-2.1-or-later. See [LICENSE](LICENSE).
