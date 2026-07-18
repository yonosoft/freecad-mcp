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

The concrete FreeCAD integration is divided by responsibility while retaining
one public adapter type. `freecad.document` defines `FreeCADDocumentAdapter` as
the stable facade; `freecad.document_operations` owns document lookup,
summaries, persistence, creation, and recomputation;
`freecad.object_inspection` owns controlled object hierarchy, visibility, and
placement extraction; and `freecad.body_creation` and
`freecad.sketch_creation` own their respective transactional mutations.
Atomic geometry addition belongs to `freecad.sketch_geometry_creation`, while
read-only sketch state belongs to `freecad.sketch_inspection`. Both remain
separate from sketch creation and behind the same public adapter facade.

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

Shared structural concerns sit below the handlers: `freecad_mcp.models` owns
controlled document, object, placement, and attachment data;
`freecad_mcp.protocols` defines the document-adapter, dispatch, executor, and
server-runner boundaries; `freecad_mcp.exceptions` owns controlled failures;
and `freecad_mcp.validation` owns explicit request validation. These modules
remain pure Python and do not import handlers or concrete FreeCAD, Qt, MCP, or
server implementations. Legacy command-module imports are compatibility
re-exports of the same objects.

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

`FreeCADDocumentAdapter` remains the sole concrete implementation of the shared
`DocumentAdapter` protocol and is imported from `freecad_mcp.freecad.document`.
Its methods delegate to the focused FreeCAD integration modules without moving
handlers, validation, transport, or runtime composition into that package.
Object-detail construction is shared by inspection, body creation, and sketch
creation, while transaction ownership stays with each mutating operation so its
FreeCAD call order and rollback boundary remain explicit.

FreeCAD document changes must:

1. execute on the main Qt thread;
2. open a named document transaction where the operation supports one;
3. validate inputs before mutation where practical;
4. apply changes;
5. recompute only when the operation's public contract requires it;
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

FastMCP registrations are explicit and grouped by contract:
`mcp.document_tools` registers document creation, listing, lookup, saving, and
recomputation; `mcp.object_tools` registers object listing and lookup and owns
the separate `get_sketch` registration; and `mcp.creation_tools` registers body
and sketch creation. `mcp.sketch_geometry_tools` explicitly registers the
atomic geometry mutation. `mcp.server` is the small composition module that
constructs FastMCP and invokes those registration functions in authoritative
tool-registry order. `get_sketch` remains exactly tool ten and
`add_sketch_geometry` is registered after it as exactly tool eleven; no
registration loop is used.
Registration modules depend on handlers and the tool registry, never on the
concrete FreeCAD adapter.

A dependency-free tool registry is the authoritative source for tool names and
ordering. FastMCP registration and lifecycle status both consume that registry,
so reported capabilities cannot drift from the registered set.

The registry currently exposes `create_document`, `list_documents`,
`get_document`, `save_document`, `list_objects`, `get_object`,
`recompute_document`, `create_body`, `create_sketch`, `get_sketch`, and
`add_sketch_geometry`, in that order.

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

The parent is the first supported container found for the object. The adapter
queries `getParentGeoFeatureGroup()` (PartDesign Body, GeoFeatureGroup) followed
by `getParentGroup()` (App::Part, regular groups). Both return `None` when no
supported container exists. Top-level objects with no container parent receive
`null`.

Children are derived only from a supported container's direct `Group` property.
Non-container objects have no `Group` and report an empty children list. Each
child list is sorted by internal name.

`InList` and `OutList` are generic dependency relationships and must not be used
to derive containment. Dependencies such as Sketch-to-Pad appear in those lists
but are not parent/child containment and are excluded from the summary.

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

### get_object

`get_object` retrieves one object by exact internal document name and exact
internal object name. It follows the same dispatch chain as `list_objects`:

```text
MCP tool → Application → GetObjectHandler → FreeCADDocumentAdapter → Qt dispatcher → FreeCAD API
```

The handler reuses the existing container-only parent and child semantics,
visibility extraction, and document-not-found behaviour from `list_objects`.
An additional `object_not_found` error is returned when the object name cannot
be resolved; labels are never used as fallback lookup keys.

#### Placement

The result includes a controlled `placement` field alongside the standard
`ObjectSummary` fields. Placement is extracted from the FreeCAD object's
`Placement` attribute using ``Base`` position, ``Rotation.Axis``, and
``Rotation.Angle``. The angle is converted from FreeCAD's internal radians to
degrees, and all values are converted to plain `float`.

When placement is unavailable, the ``Placement`` attribute is absent, or any
extracted value cannot be represented safely, the field is `null` rather than
failing the entire tool. No matrices, arbitrary properties, or expressions are
exposed.

The flat response contract places summary fields directly alongside
`placement` without a nested `summary` wrapper:

```json
{
  "document_name": "BracketDesign",
  "object": {
    "name": "Body",
    "label": "Bracket Body",
    "type_id": "PartDesign::Body",
    "visibility": true,
    "parent": null,
    "children": ["Pad001", "Sketch001"],
    "placement": {
      "position": {"x": 0.0, "y": 0.0, "z": 0.0},
      "rotation": {
        "axis": {"x": 0.0, "y": 0.0, "z": 1.0},
        "angle_degrees": 0.0
      }
    }
  }
}
```

### recompute_document

`recompute_document` recomputes one open document through the full dispatch
chain and returns its updated controlled `DocumentSummary`:

```text
MCP tool → Application → RecomputeDocumentHandler → FreeCADDocumentAdapter → Qt dispatcher → FreeCAD API
```

The tool looks up the document by exact internal name, invokes
`Document.recompute()` on the main thread, and returns the document's
post-recompute summary with the same fields used by `get_document`. The
document label is preserved, the file path is unchanged, and the document is
not saved automatically.

A dedicated `document_recompute_failed` error is returned when the FreeCAD
recompute itself fails. Missing documents use the existing `document_not_found`
convention. The tool is MCP-only and has no matching toolbar or menu command.

## Body Creation

### create_body

`create_body` is the first modelling mutation tool. It creates exactly one
`PartDesign::Body` in an open document through the full dispatch chain:

```text
MCP tool → Application → CreateBodyHandler → FreeCADDocumentAdapter → Qt dispatcher → FreeCAD API
```

The handler validates inputs using the shared document-name policy and an
object-name policy that identifies the body-name field as ``"name"``. It then
marshals execution to the main thread through the existing dispatcher.

#### Success Contract

On success, the result returns the same controlled ``ObjectDetail`` contract
used by `get_object`:

```json
{
  "ok": true,
  "code": "body_created",
  "document_name": "BracketDesign",
  "object": {
    "name": "Body",
    "label": "Bracket Body",
    "type_id": "PartDesign::Body",
    "visibility": true,
    "parent": null,
    "children": [],
    "placement": {
      "position": {"x": 0.0, "y": 0.0, "z": 0.0},
      "rotation": {
        "axis": {"x": 0.0, "y": 0.0, "z": 1.0},
        "angle_degrees": 0.0
      }
    }
  },
  "message": "FreeCAD body created."
}
```

#### Transaction and Rollback

The adapter opens a FreeCAD document transaction with the label
``"MCP Create Body"`` before creating the body. After successful creation and
recomputation, the transaction is committed. On any failure after the
transaction is opened, ``abortTransaction()`` is attempted on a best-effort
basis and the original error is preserved. An abort failure does not replace
the primary error.

#### Duplicate Name Rejection

The adapter checks for an existing object with the requested internal name
before opening a transaction. If one exists, ``ObjectAlreadyExistsError`` is
raised and the handler returns ``object_already_exists``. If FreeCAD silently
renames the body (e.g., from ``"Body"`` to ``"Body001"``), that is treated as
``BodyCreationError`` and the handler returns ``body_creation_failed``. Labels
may be duplicated freely.

#### Error Codes

- ``validation_error``: invalid or missing document name, body name, or label;
- ``document_not_found``: the document does not exist;
- ``object_already_exists``: an object with the requested internal name
  already exists;
- ``body_creation_failed``: FreeCAD could not create the body, including
  addObject returning null, unexpected renaming, label assignment failure,
  recompute failure, or commit failure;
- ``freecad_error``: main-thread dispatch failure or FreeCAD document
  inspection failure;
- ``internal_error``: unexpected exceptions.

## Sketch Creation

### create_sketch

`create_sketch` is the second modelling mutation tool. It creates exactly one
empty, unattached `Sketcher::SketchObject` inside an existing `PartDesign::Body`
through the full dispatch chain:

```text
MCP tool → Application → CreateSketchHandler → FreeCADDocumentAdapter → Qt dispatcher → FreeCAD API
```

The handler validates document, body, and sketch names using the shared policies,
then marshals execution to the main thread. The adapter resolves the document
and body by exact internal name, verifies the body type, checks for duplicate
sketch names before opening a transaction, and creates the sketch using
`body.newObject("Sketcher::SketchObject", name)` to establish correct ownership.

#### Success Contract

On success the result returns the same controlled `ObjectDetail` contract:

```json
{
  "ok": true,
  "code": "sketch_created",
  "document_name": "BracketDesign",
  "body_name": "Body",
  "object": {
    "name": "BaseSketch",
    "label": "Base Sketch",
    "type_id": "Sketcher::SketchObject",
    "visibility": true,
    "parent": "Body",
    "children": [],
    "placement": {
      "position": {"x": 0.0, "y": 0.0, "z": 0.0},
      "rotation": {
        "axis": {"x": 0.0, "y": 0.0, "z": 1.0},
        "angle_degrees": 0.0
      }
    }
  },
  "message": "FreeCAD sketch created."
}
```

#### Transaction and Rollback

The adapter opens a FreeCAD document transaction with the label
``"MCP Create Sketch"`` before creating the sketch. After successful creation,
recomputation, and ownership verification, the transaction is committed. On any
failure after the transaction is opened, ``abortTransaction()`` is attempted on a
best-effort basis and the original error is preserved. An abort failure does not
replace the primary error.

#### Ownership Verification

After recomputation the adapter uses the shared `_build_object_detail` function
and verifies that the computed ``parent`` field equals the requested body's
internal name. If it does not, the transaction is aborted and
``SketchCreationError`` is raised.

#### Attachment

`create_sketch` accepts an optional `support_plane` parameter. When `null` or
omitted, the sketch is created unattached. When one of
`xy_plane`, `xz_plane`, or `yz_plane` is supplied, the adapter resolves the
plane from the target body's `Origin.OriginFeatures` by semantic `Role`
(`"XY_Plane"`, `"XZ_Plane"`, `"YZ_Plane"`) rather than by document-level name,
supporting multiple bodies with suffixed origin feature names such as
`XY_Plane001`.

The resolved origin feature is assigned through the sketch's
`AttachmentSupport` property and `MapMode` is set to `FlatFace`.
`AttachmentOffset` is not modified and therefore remains at FreeCAD's default
under the supported creation path.

#### Attachment Verification

After recomputation the adapter verifies the sketch still belongs to the
requested body, the support references the selected origin feature with the
correct `Role`, and `MapMode` is `FlatFace`. Verification reads
`AttachmentSupport` first and uses the existing `Support` property only when
`AttachmentSupport` cannot be read. The adapter does not explicitly inspect or
verify `AttachmentOffset`; that remains a live FreeCAD acceptance check. Any
verified mismatch aborts the transaction and returns `sketch_creation_failed`.

#### Attachment Result

The public result includes an `attachment` field: `null` for unattached sketches,
or `{"kind": "body_origin_plane", "plane": "<plane>", "map_mode": "flat_face"}`
for attached sketches. Raw FreeCAD support tuples and origin feature objects are
never exposed.

#### Error Codes

- ``validation_error``: invalid or missing document name, body name, sketch
  name, label, or support_plane;
- ``document_not_found``: the document does not exist;
- ``body_not_found``: no object with the requested body internal name exists;
- ``body_type_mismatch``: an object with the body name exists but is not a
  PartDesign::Body;
- ``origin_plane_not_found``: the requested origin plane could not be resolved
  from the target body's Origin (missing Origin, unusable OriginFeatures,
  or requested role absent);
- ``object_already_exists``: an object with the requested sketch internal
  name already exists (detected before transaction start);
- ``sketch_creation_failed``: FreeCAD could not create or attach the sketch,
  including newObject returning null, unexpected renaming, wrong type,
  missing body ownership, support/map-mode assignment failure, recompute
  failure, attachment verification failure, or commit failure;
- ``freecad_error``: main-thread dispatch failure or FreeCAD document
  inspection failure;
- ``internal_error``: unexpected exceptions.

## Sketch Geometry Mutation

### add_sketch_geometry

`add_sketch_geometry` is the controlled atomic mutation path for geometry in a
`Sketcher::SketchObject`. It accepts exact internal `document_name` and
`sketch_name` values plus a required ordered `geometry` array. Its
responsibility flow is:

```text
MCP sketch-geometry registration
→ add-sketch-geometry command handler
→ application facade
→ document adapter protocol
→ FreeCADDocumentAdapter facade
→ focused sketch-geometry-creation module
→ Qt main-thread dispatcher
→ FreeCAD Sketcher API
```

The handler lives in `src/freecad_mcp/commands/sketch_geometry.py`; the focused
adapter operation lives in
`src/freecad_mcp/freecad/sketch_geometry_creation.py`. Models and validation do
not import FreeCAD. The concrete adapter remains publicly importable from
`freecad_mcp.freecad.document` and only delegates to the focused operation.

#### Input Contract

The shared model layer defines an explicit Pydantic-discriminated union. Every
model forbids extra fields, uses finite strict numbers, and requires an
explicit strict Boolean `construction` field:

```text
LineSegmentGeometryInput
  type: "line_segment"
  start: {x: number, y: number}
  end: {x: number, y: number}
  construction: boolean

CircleGeometryInput
  type: "circle"
  center: {x: number, y: number}
  radius: number > 0
  construction: boolean

ArcOfCircleGeometryInput
  type: "arc_of_circle"
  center: {x: number, y: number}
  radius: number > 0
  start_angle_degrees: number
  end_angle_degrees: number
  construction: boolean

PointGeometryInput
  type: "point"
  position: {x: number, y: number}
  construction: boolean
```

Point mutation and inspection use distinct typed models:
`PointGeometryInput.position` represents mutation input, while
`SketchPointGeometry.point` represents controlled inspection output. This
asymmetry is intentional and is covered independently by schema, adapter, and
serialization tests.

The batch has `minItems: 1` and `maxItems: 100`. The handler repeats these
limits for non-transport callers and validates exact internal-name policy,
unknown discriminators, missing or extra fields, numeric types, finite values,
positive radii, exactly equal line endpoints, and collapsing arc angles before
dispatch. Duplicate or coincident geometry is not rejected.

The input union is intentionally additive: later controlled geometry input
models can join it without changing handler dispatch or transaction handling.
Ellipse, conic, and B-spline input models are not present in this milestone.

#### Arc Parameter Policy

FreeCAD 1.1.1 accepts negative and over-360-degree-equivalent parameters,
normalizes each parameter, converts a wraparound endpoint to a positive
counter-clockwise span, and accepts a complete circle as `ArcOfCircle`. It
throws `Part.OCCError` for exactly equal raw parameters, while non-finite
parameters can construct malformed objects instead of failing immediately.

The public contract therefore accepts any finite degree values, normalizes each
modulo 360, and makes the end the next counter-clockwise parameter after the
start. Equal normalized endpoints are rejected, including 360-degree and
multi-turn spans. The canonical finite angles are converted to radians only in
the focused FreeCAD module. This prevents constructor-dependent ambiguity and
keeps full circles represented by the `circle` discriminator.

#### Transaction, Construction, and Rollback

After validation, the adapter locates the exact document and object, confirms
`isDerivedFrom("Sketcher::SketchObject")`, and captures the original geometry
count and every pre-existing construction flag. It opens one transaction named
`MCP Add Sketch Geometry`, then constructs and inserts each item in request
order using `Sketch.addGeometry(geometry, construction)`. The returned index,
incremental geometry count, construction flag, final count, and number of
indices are verified. Success commits once.

The operation follows the existing mutation ownership policy: it opens,
commits, or aborts exactly its own transaction call, preserving an outer
transaction in runtimes that support nesting. It never opens one transaction
per item.

FreeCAD 1.1.1 with `UndoMode == 0` does not remove `addGeometry` changes when
`abortTransaction()` is called. Rollback therefore deletes every appended tail
index in reverse before abort, aborts the transaction, repeats safe tail
cleanup for compensation, restores any changed pre-existing construction
flags, and verifies the original count and construction tuple. Any failed
verification or abort becomes `sketch_geometry_rollback_failed`; partial index
lists are never returned.

The mutation deliberately does not call `Document.recompute()`, `Sketch.solve()`,
`save()`, or `saveAs()`. Clients use explicit `recompute_document` when wanted
and then call `get_sketch` for authoritative geometry and solver-cache readback.

#### Success and Index Semantics

Success uses code `sketch_geometry_added` and contains `document_name`,
`sketch_name`, ordered `added_indices`, derived `added_count`, final
`geometry_count`, and message `Sketch geometry added.`. Raw FreeCAD objects are
never returned.

Indices describe the immediate post-operation sketch state and are not
permanent identities. Later geometry mutations can renumber them; clients must
call `get_sketch` after mutation. FreeCAD geometry tags and synthetic UUID
properties are not exposed.

#### Error Codes

- `validation_error`: invalid names, malformed input, unsupported
  discriminator, invalid number, empty or over-limit batch, zero-length line,
  invalid radius, or collapsing arc;
- `document_not_found`: the document does not exist;
- `sketch_not_found`: no object has the exact requested sketch name;
- `sketch_type_mismatch`: the object is not derived from a Sketcher sketch;
- `sketch_geometry_creation_failed`: controlled constructor, insertion,
  construction verification, index/count, transaction, document-access, or
  dispatch failure;
- `sketch_geometry_rollback_failed`: abort or controlled state restoration
  could not be verified;
- `internal_error`: an unexpected non-FreeCAD implementation failure.

FreeCAD exception text, traceback data, object representations, and memory
addresses are not included in these results.

## Sketch Inspection

### get_sketch

`get_sketch` is the controlled read-only path for a `Sketcher::SketchObject`.
It accepts required `document_name` and `sketch_name` inputs and resolves both
by exact internal name. Its responsibility flow is:

```text
MCP object-tool registration
→ get-sketch command handler
→ application facade
→ sketch document protocol
→ FreeCADDocumentAdapter facade
→ focused sketch-inspection module
→ Qt main-thread dispatcher
→ FreeCAD Sketcher API
```

The handler lives in `src/freecad_mcp/commands/sketch_query.py`; the focused
adapter responsibility lives in
`src/freecad_mcp/freecad/sketch_inspection.py`. The shared `DocumentAdapter`
protocol and application facade expose the operation without importing
FreeCAD. `FreeCADDocumentAdapter` remains publicly importable from
`freecad_mcp.freecad.document` and delegates inspection to the focused module,
while `sketch_creation.py` remains responsible only for transactional creation.

The result uses controlled models for identity, owning body, visibility,
placement, map mode, attachment, geometry, constraints, units, and cached
solver facts. Placement and attachment offset reuse the existing
`PlacementData` representation. A recognized body-origin attachment contains
`kind: body_origin_plane`, its semantic `plane`, and a controlled `offset`;
support objects and raw FreeCAD tuples are not exposed. Raw FreeCAD objects and
arbitrary property maps never cross the adapter boundary.

Success uses code `sketch_retrieved` and the normal `CommandResult` envelope:
`ok`, `code`, `document_name`, controlled `sketch`, and `message`. Lengths are
normalized to `millimeter` and angles to `degree`. The `solver` object contains
`available`, `fresh`, `degrees_of_freedom`, `fully_constrained`, and the
conflicting, redundant, partially redundant, and malformed constraint-index
lists. When FreeCAD's cached sketch state is stale, `available` remains true
but the cached facts are null; inspection does not recompute them.

#### Unsupported and Malformed Data

Valid but unsupported FreeCAD geometry or constraints are successful
`unsupported` records with a sanitized FreeCAD type name. A recognized geometry
or constraint whose required data is malformed fails with
`sketch_geometry_malformed` or `sketch_constraint_malformed`, respectively.
Unexpected controlled adapter or dispatch failures use
`sketch_inspection_failed`.

The complete expected public error set is:

- `validation_error`: invalid document or sketch internal-name input;
- `document_not_found`: the document does not exist;
- `sketch_not_found`: no object has the requested sketch internal name;
- `sketch_type_mismatch`: the named object is not a Sketcher sketch;
- `sketch_geometry_malformed`: supported geometry lacks valid required data;
- `sketch_constraint_malformed`: a supported constraint lacks valid required data;
- `sketch_inspection_failed`: controlled FreeCAD or dispatch inspection failure;
- `internal_error`: unexpected exceptions.

#### Non-Mutation Contract

The inspection path does not call `openTransaction`, `commitTransaction`,
`abortTransaction`, `solve`, `recompute`, `save`, `saveAs`, `addProperty`,
`setDriving`, or `setVirtualSpace`. It only reads current state and never
refreshes stale solver data implicitly.

Live acceptance confirmed that inspection preserves the active document,
modified state, file name, transaction state, undo and redo counts, sketch
state, geometry and constraint counts, visibility, selection, edit mode, map
mode, attachment, placement, and attachment offset.

## Test Ownership

The pure-Python suite mirrors the production responsibilities rather than
collecting all adapter or transport behavior in single modules:

- handler and validation tests remain grouped by application operation under
  `tests/test_*.py`, including `tests/test_get_sketch.py` and
  `tests/test_add_sketch_geometry.py`;
- FreeCAD adapter tests are split into document operations, object inspection,
  body creation, sketch creation, sketch attachment, and read-only sketch
  inspection modules; atomic geometry mutation and rollback belong in
  `tests/test_freecad_sketch_geometry_creation.py`;
- MCP tests are split into document, object, creation, and sketch-geometry
  registrations, while server composition, authoritative inventory, lifecycle
  agreement, and HTTP transport remain together;
- `tests/test_module_compatibility.py` exclusively owns legacy/canonical identity
  promises;
- `tests/test_architecture.py` owns stable import-direction, explicit-registration,
  canonical-definition, and clean-process import safeguards.

`freecad_adapter_stubs.py` and `mcp_server_stubs.py` are non-collectable,
test-only support modules. They provide only stateful fakes genuinely shared by
multiple responsibility files; each test constructs fresh mutable state.

These tests run under standalone Python 3.11 and do not import a running FreeCAD
process. FreeCAD API behavior, Qt integration, workbench startup, and GUI state
remain live acceptance responsibilities documented in `docs/development.md`.

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

`runtime.py` is the concrete composition root. It constructs the single
`FreeCADDocumentAdapter`, the Qt dispatcher, all application handlers, and the
MCP runner/lifecycle service. Dependency direction remains MCP registration to
application handlers to shared protocols/models/exceptions/validation to the
concrete FreeCAD integration and Qt dispatcher; lower layers do not import the
composition root or transport registration.
