# Architecture

## Purpose

FreeCAD MCP is an external Python FreeCAD workbench that will embed a local MCP server. It is designed around explicit typed CAD operations, shared command handlers, validation, and structured state feedback.

## Component model

```text
FreeCAD toolbar/menu       MCP transport
         │                     │
         └──── adapters ───────┘
                    │
             application layer
                    │
       typed command handlers and schemas
                    │
      FreeCAD document/GUI adapter boundary
                    │
       FreeCAD main Qt thread + transactions
```

### Bootstrap modules

- `Init.py` ensures the addon root is importable in application/console mode. It must remain lightweight.
- `InitGui.py` registers the Python workbench and lazily registers GUI commands.
- `package.xml` supplies FreeCAD Addon Manager metadata even though development uses a junction.

### Pure command layer

`freecad_mcp.commands` contains operations expressed without direct FreeCAD imports where possible. Handlers return `CommandResult` objects with a stable code, message, and structured data. This layer is the common entry point for GUI and future MCP adapters.

The initial `report_status` handler demonstrates this dispatch path without modifying a document.

### FreeCAD and GUI adapters

`freecad_mcp.gui` owns FreeCAD GUI command registration and Report View output. Future document adapters will own imports such as `FreeCAD`, `Part`, and `Sketcher` and will translate semantic requests into FreeCAD API operations.

FreeCAD document changes must:

1. execute on the main Qt thread;
2. open a named document transaction;
3. validate inputs before mutation where practical;
4. apply changes;
5. recompute the document;
6. inspect the result;
7. commit on success or abort/roll back on failure where supported.

Transport threads must never modify FreeCAD documents directly.

### MCP transport

The future MCP server will run locally inside the FreeCAD process. The transport layer will parse typed requests, call the application layer, and serialize structured results. It must not contain CAD implementation logic.

The server must not expose arbitrary Python execution. Screenshots may be requested for checkpoints or diagnosis, but normal state exchange should use structured object, document, constraint, geometry, and error data.

## Planned first MCP tool: `create_document`

Proposed request shape:

```json
{
  "name": "GliderTrimmer",
  "label": "Glider Trimmer"
}
```

Proposed success result:

```json
{
  "ok": true,
  "code": "document.created",
  "message": "Created document 'GliderTrimmer'.",
  "data": {
    "name": "GliderTrimmer",
    "label": "Glider Trimmer",
    "active": true
  }
}
```

The implementation should validate FreeCAD document-name rules, detect collisions, marshal execution to the main thread, create the document in a transaction-aware application service where applicable, make it active, recompute, and return structured state.

## Tool levels

- **High-level workflows:** common modeling sequences with strong validation and fewer round trips.
- **Mid-level operations:** explicit sketch, constraint, feature, document, and inspection tools.
- **Inspection/recovery:** document summaries, object properties, validation reports, transaction/error recovery, and optional diagnostic screenshots.

Avoid exposing raw numeric enum values when semantic strings are possible. Avoid face/edge indices when stable references or geometric selection rules can be used.

## Dependency policy

Runtime code should initially use only Python's standard library and modules shipped with FreeCAD. Development tools (`pytest`, `ruff`, `mypy`) run under an external Python 3.11 virtual environment and are not runtime dependencies.
