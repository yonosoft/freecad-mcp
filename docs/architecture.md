# Architecture

## Purpose

MCP is an external Python FreeCAD workbench that embeds a local MCP server.
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
       queued Qt dispatch to FreeCAD main thread
```

## Bootstrap Modules

- `Init.py` ensures the addon root is importable in application/console mode.
- `InitGui.py` registers `MCPWorkbench` and lazily registers GUI commands.
- `package.xml` supplies FreeCAD addon metadata.

Startup code must remain small and robust. Substantial work belongs behind
workbench activation, command activation, or the future MCP server lifecycle.

## Shared Command Layer

`freecad_mcp.commands` contains operations expressed without direct FreeCAD
imports. Handlers return `CommandResult` objects with stable codes, user-facing
messages, and structured data. This layer is the common entry point for GUI
commands and MCP transport adapters.

`create_document` validates a strict FreeCAD internal name, then dispatches the
adapter operation to the main Qt thread. Names use an ASCII letter or underscore
followed by letters, digits, or underscores. This avoids FreeCAD's automatic
sanitization. An already-open internal name is rejected instead of allowing
FreeCAD to silently append a numeric suffix.

## FreeCAD and GUI Adapters

`freecad_mcp.gui` owns FreeCAD GUI command registration and Report View output.
Document adapters own imports such as `FreeCAD`, `Part`, and `Sketcher` and
translate semantic requests into FreeCAD API operations.

FreeCAD document changes must:

1. execute on the main Qt thread;
2. open a named document transaction where the operation supports one;
3. validate inputs before mutation where practical;
4. apply changes;
5. recompute the document;
6. inspect the result;
7. commit on success or abort/roll back on failure where supported;
8. return structured results.

Transport threads must never modify FreeCAD documents directly.

Creating a document cannot open a transaction before the document exists. The
adapter instead rejects duplicates before creation, applies the label, recomputes,
and closes the newly created document if initialization fails.

## Main-Thread Dispatch

FreeCAD 1.1.1 on Windows supplies PySide6 and Qt 6.8.3 through FreeCAD's
`PySide` compatibility package. A Qt-owned executor receives Python callables via
a queued signal. Calls already on the Qt application thread execute directly;
calls from the MCP server thread wait on a `Future`, preserving return values and
exceptions without polling or starting another Qt event loop.

## Embedded MCP Server

One process-owned lifecycle service manages the `stopped`, `starting`,
`running`, `stopping`, and `error` states. It creates at most one runner and
handles duplicate start/stop requests without spawning another thread.

The runner uses the official MCP Python SDK 1.27.x with FastMCP's stateless JSON
Streamable HTTP app and uvicorn. One daemon thread owns the HTTP event loop, and
graceful shutdown is requested through uvicorn. Qt's `aboutToQuit` signal stops
the runner when FreeCAD exits. The server binds only to `127.0.0.1` at:

```text
http://127.0.0.1:8765/mcp
```

SDK-specific registration is isolated under `freecad_mcp.mcp`; it parses typed
requests, calls the shared handler, and serializes structured results without
containing CAD implementation logic.

The server must not expose arbitrary Python execution. Screenshots may be used
as diagnostic checkpoints, but normal state exchange should use structured
document, object, constraint, geometry, and error data.

## First Tool: `create_document`

The `create_document` tool creates a FreeCAD document through the shared
application path. It validates document-name rules, detects collisions, marshals
execution to the main thread, creates and labels the document, recomputes it,
and returns the actual name and label.

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

The official MCP SDK is the only declared runtime dependency and is constrained
to `mcp>=1.27.2,<2` while SDK v2 remains prerelease. FreeCAD imports remain
runtime adapter dependencies. Development tools (`pytest`, `ruff`, `mypy`) run
under an external Python 3.11 virtual environment.
