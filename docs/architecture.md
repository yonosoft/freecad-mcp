# Architecture

## Purpose

MCP is an external Python FreeCAD workbench that will embed a local MCP server.
It is designed around explicit typed CAD operations, shared command handlers,
validation, and structured state feedback.

## Source Layout

`src` is the FreeCAD addon root. FreeCAD discovers `Init.py`, `InitGui.py`, and
`package.xml` directly under the installed addon folder, so development links
the whole `src` directory into FreeCAD's user `Mod` directory.

```text
src/
|-- Init.py
|-- InitGui.py
|-- package.xml
|-- Resources/
`-- freecad_mcp/
```

Naming is intentionally split by role:

- visible workbench name: `MCP`;
- installed addon folder: `mcp`;
- Python package: `freecad_mcp`;
- workbench class: `MCPWorkbench`;
- FreeCAD command namespace: `MCP_`.

The lowercase installed folder keeps filesystem behavior predictable across
platforms. The Python package remains `freecad_mcp` to avoid colliding with MCP
SDK modules that may use the `mcp` namespace.

## Component Model

```text
FreeCAD toolbar/menu       MCP transport
         |                     |
         `---- adapters -------'
                    |
             application layer
                    |
       typed command handlers and schemas
                    |
      FreeCAD document/GUI adapter boundary
                    |
       FreeCAD main Qt thread + transactions
```

## Bootstrap Modules

- `Init.py` ensures the addon root is importable in application/console mode.
- `InitGui.py` registers `MCPWorkbench` and lazily registers GUI commands.
- `package.xml` supplies FreeCAD addon metadata.

Startup code must remain small and robust. Substantial work belongs behind
workbench activation, command activation, or the future MCP server lifecycle.

## Shared Command Layer

`freecad_mcp.commands` contains operations expressed without direct FreeCAD
imports where practical. Handlers return `CommandResult` objects with stable
codes, user-facing messages, and structured data. This layer is the common entry
point for GUI commands and future MCP transport adapters.

The initial `report_status` handler demonstrates the path without modifying a
document. The first planned explicit MCP tool is `create_document`.

## FreeCAD and GUI Adapters

`freecad_mcp.gui` owns FreeCAD GUI command registration and Report View output.
Future document adapters will own imports such as `FreeCAD`, `Part`, and
`Sketcher` and translate semantic requests into FreeCAD API operations.

FreeCAD document changes must:

1. execute on the main Qt thread;
2. open a named document transaction;
3. validate inputs before mutation where practical;
4. apply changes;
5. recompute the document;
6. inspect the result;
7. commit on success or abort/roll back on failure where supported;
8. return structured results.

Transport threads must never modify FreeCAD documents directly.

## Embedded MCP Server

The future MCP server will run locally inside the FreeCAD process. The transport
layer will parse typed requests, call the shared command layer, and serialize
structured results. It must not contain CAD implementation logic.

The server must not expose arbitrary Python execution. Screenshots may be used
as diagnostic checkpoints, but normal state exchange should use structured
document, object, constraint, geometry, and error data.

## Planned First Tool: `create_document`

The `create_document` tool will create a FreeCAD document through the shared
application path. It should validate document-name rules, detect collisions,
marshal execution to the main thread, create the document, make it active,
recompute as needed, and return structured state.

## Tool Levels

- **High-level workflows:** common modeling sequences with strong validation and
  fewer round trips.
- **Mid-level operations:** explicit sketch, constraint, feature, document, and
  inspection tools.
- **Inspection/recovery:** document summaries, object properties, validation
  reports, transaction/error recovery, and optional diagnostic screenshots.

Avoid exposing raw numeric enum values when semantic strings are possible. Avoid
face/edge indices when stable references or geometric selection rules can be
used.

## Dependency Policy

Runtime code should initially use only Python's standard library and modules
shipped with FreeCAD. Development tools (`pytest`, `ruff`, `mypy`) run under an
external Python 3.11 virtual environment and are not runtime dependencies.
