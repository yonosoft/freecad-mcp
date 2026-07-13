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
workbench activation, command activation, or the MCP server lifecycle.

## Shared Command Layer

`freecad_mcp.commands` contains operations expressed without direct FreeCAD
imports. Handlers return `CommandResult` objects with stable codes, user-facing
messages, and structured data. This layer is the common entry point for GUI
commands and MCP transport adapters.

Document handlers validate requests and dispatch adapter operations to the main
Qt thread. The MCP server accepts internal names consisting of an ASCII letter
or underscore followed by letters, digits, or underscores. This is an MCP input
policy, not a claim about every name FreeCAD can represent. It avoids automatic
sanitization, and an already-open name is rejected instead of allowing FreeCAD
to append a numeric suffix.

### Shared Document Summary

`create_document`, `list_documents`, `get_document`, and `save_document` use one
document summary contract:

- `name`: FreeCAD's stable internal document identifier;
- `label`: the user-visible document label;
- `file_path`: FreeCAD's actual `Document.FileName`, or `null` when empty;
- `saved`: whether `file_path` is non-null;
- `modified`: the actual `FreeCADGui.Document.Modified` dirty flag;
- `active`: whether the document is FreeCAD's current active document;
- `object_count`: the current length of `Document.Objects`.

`Document.isSaved()` is not used for `modified`: FreeCAD documents that have a
backing filename remain "saved" while containing later unsaved changes. The GUI
document's `Modified` property is the authoritative state used for close/save
prompts. Reading it requires normal FreeCAD GUI mode; the embedded MCP runtime is
therefore not a headless `FreeCADCmd` service.

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
adapter instead rejects duplicates before creation, applies the label,
recomputes, and closes the newly created document if initialization fails.
Listing and inspection are read-only. Saving changes persistence state rather
than model data, so it uses FreeCAD's save API without opening a model
transaction or forcing a recompute.

## Main-Thread Dispatch

FreeCAD 1.1.1 on Windows supplies PySide6 and Qt 6.8.3 through FreeCAD's
`PySide` compatibility package. A Qt-owned executor receives Python callables via
a queued signal. Calls already on the Qt application thread execute directly;
calls from the MCP server thread wait on a `Future`, preserving return values and
exceptions without polling or starting another Qt event loop.

If the wait times out, the dispatcher cancels the `Future`. The queued Qt slot
uses `set_running_or_notify_cancel()` and skips an operation cancelled before it
starts. Once the slot has marked an operation running, it cannot safely terminate
FreeCAD work. The client receives a typed dispatch timeout indicating whether
pre-start cancellation succeeded; when it did not, the operation may already
have completed or may complete later, so the client should inspect document
state before retrying a mutation.

## Embedded MCP Server

One process-owned lifecycle service manages the `stopped`, `starting`,
`running`, `stopping`, and `error` states. It creates at most one runner and
handles duplicate start/stop requests without spawning another thread.

FreeCAD process shutdown asks the lifecycle service to clean up any runner it
still owns, including ownership retained after a partial startup failure. The
cleanup path is idempotent and does not issue a duplicate stop while an explicit
stop is already in progress.

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

A dependency-free tool registry is the authoritative source for tool names and
ordering. FastMCP registration and lifecycle status both consume that registry,
so reported capabilities cannot drift from the registered set.

The server must not expose arbitrary Python execution. Screenshots may be used
as diagnostic checkpoints, but normal state exchange should use structured
document, object, constraint, geometry, and error data.

## Document Tools

The `create_document` tool creates a FreeCAD document through the shared
application path. It validates document-name rules, detects collisions, marshals
execution to the main thread, creates and labels the document, recomputes it,
and returns its full unsaved document summary. It is MCP-only and has no matching
toolbar or menu command.

`list_documents` returns documents ordered by internal name and reports the
actual active document. `get_document` performs an exact internal-name lookup;
labels are not lookup keys. Both reads cross the same main-thread dispatcher as
mutating operations because FreeCAD document and GUI state are thread-affine.

`save_document` uses `Document.save()` when no new path is supplied for an
already-saved document, or when the requested path resolves to its existing
path. It uses `Document.saveAs()` for an unsaved document or a different
destination. The actual post-save `FileName` and `Modified` values are returned.

FreeCAD's App-level `Document.saveAs()` replaces `Document.Label` with the new
filename stem, while FreeCAD's GUI Save As path separately clears the GUI
document's modified flag. The adapter preserves the pre-save user-visible label,
persists it with a follow-up `save()` when `saveAs()` changed it, and clears the
GUI modified flag only after every required write succeeds. This matches normal
FreeCAD GUI save semantics while keeping MCP labels stable across save-as.

Save-as paths are handled with `pathlib`: user-home markers are expanded,
relative paths resolve against the FreeCAD process working directory, and the
result is absolute. A missing extension is appended as `.FCStd`; case variants
of that extension are normalized to `.FCStd`; other extensions are rejected.
The parent directory must already exist. The handler does not create directories,
browse the filesystem, or delete files.

Before save-as, the handler checks whether the destination exists. Existing
destinations return `file_already_exists` unless `overwrite` is explicitly true.
This guard does not block a normal `save()` to a document's own backing file.
Filesystem checks and the FreeCAD save execute inside the single dispatched
operation, while transport threads never access a document directly.

## Object Inspection

`list_objects` is the first MCP-only object-inspection tool. It returns
controlled `ObjectSummary` records through the full dispatch chain:

```text
MCP tool → Application → ListObjectsHandler → FreeCADDocumentAdapter → Qt dispatcher → FreeCAD API
```

### Shared Object Summary

Each `ObjectSummary` provides a narrow, stable view of one FreeCAD document
object without exposing arbitrary properties:

- `name`: FreeCAD's stable internal object identifier;
- `label`: the user-visible object label;
- `type_id`: FreeCAD's type identifier such as `PartDesign::Body`;
- `visibility`: current GUI visibility (`True` when no view provider exists);
- `parent`: internal name of the primary containing object, or `null` for
  top-level objects;
- `children`: deterministic list of direct child internal names, sorted
  alphabetically.

### Parent and Child Semantics

The parent is the first entry in the FreeCAD object's `InList`. When `InList` is
non-empty, another object depends on or contains this one. Top-level objects
with no incoming reference receive `null`.

Children are the object's `OutList` entries sorted by internal name. This
captures dependency and containment relationships; a future refinement may
distinguish strict container membership from general dependency links.

### Deterministic Ordering

Top-level result objects are sorted by internal name within the adapter. Each
`children` list is also sorted by internal name. This ensures repeatable
ordering across calls.

### Visibility Fallback

When a FreeCAD GUI document or view provider is not available (headless
environments, fake objects, or error conditions), visibility defaults to `True`
rather than `null` or an exception. This keeps the tool usable without a GUI
while still returning actual visibility when the GUI is present.

### Why Arbitrary Properties Are Not Exposed

FreeCAD objects carry dozens of properties, expressions, links, and
view-provider internals. Exposing all of them would:
- couple MCP clients to FreeCAD implementation details;
- produce extremely large responses;
- break when FreeCAD's internal representation changes.

The `ObjectSummary` model is deliberately narrow. Future tools such as
`get_object` can add detail incrementally without changing this contract.

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
