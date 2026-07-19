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
Semantic axis-aligned rectangle creation belongs to
`freecad.sketch_rectangle_creation` and
`freecad.sketch_centered_rectangle_creation`. They share deterministic
four-edge generation and verification through `sketch_rectangle_profile` and
the established native translators, while each owns its public intent,
centre/lower-left constraints, complete-profile verification, and rollback.
Controlled history inspection and one-step mutation belong to
`freecad.document_history`; `freecad.history_guard` makes MCP-owned undo, redo,
and rollback visible to re-entrant calls without exposing that state publicly.

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
atomic geometry mutation, and `mcp.sketch_constraint_tools` explicitly
registers atomic constraint mutation. `mcp.document_history_tools` explicitly
registers controlled history inspection, undo, and redo.
`mcp.sketch_rectangle_tools` and `mcp.sketch_centered_rectangle_tools`
explicitly register the two semantic rectangle profiles.
`mcp.sketch_polygon_tools` explicitly appends the semantic equilateral triangle
and regular polygon profiles.
`mcp.sketch_curved_profile_tools` explicitly appends the semantic slot and
rounded-rectangle profiles.
`mcp.server` is the small composition
module that constructs FastMCP and invokes those registration functions in
authoritative tool-registry order. `get_sketch` remains exactly tool ten,
`add_sketch_geometry` follows as exactly tool eleven, and
`add_sketch_constraints` follows as exactly tool twelve. History inspection,
undo, and redo are exactly tools thirteen through fifteen;
`create_sketch_rectangle` is exactly tool sixteen and
`create_sketch_centered_rectangle` is exactly tool seventeen;
`create_sketch_equilateral_triangle` and `create_sketch_regular_polygon` are
exactly tools eighteen and nineteen; `create_sketch_slot` and
`create_sketch_rounded_rectangle` are exactly tools twenty and twenty-one. No
registration loop is used.
Registration modules depend on handlers and the tool registry, never on the
concrete FreeCAD adapter.

A dependency-free tool registry is the authoritative source for tool names and
ordering. FastMCP registration and lifecycle status both consume that registry,
so reported capabilities cannot drift from the registered set.

The registry currently exposes `create_document`, `list_documents`,
`get_document`, `save_document`, `list_objects`, `get_object`,
`recompute_document`, `create_body`, `create_sketch`, `get_sketch`,
`add_sketch_geometry`, `add_sketch_constraints`, `get_document_history`,
`undo_document`, `redo_document`, `create_sketch_rectangle`, and
`create_sketch_centered_rectangle`, `create_sketch_equilateral_triangle`, and
`create_sketch_regular_polygon`, `create_sketch_slot`, and
`create_sketch_rounded_rectangle`, in that order.

The server must not expose arbitrary Python execution. Screenshots may be used
as diagnostic checkpoints, but normal state exchange should use structured
document, object, constraint, geometry, and error data.

## Semantic Rectangle Profile

Milestone 15A establishes the semantic-profile dependency direction without a
generic profile union:

```text
create_sketch_rectangle MCP registration
→ CreateSketchRectangleHandler / application
→ DocumentAdapter.create_sketch_rectangle protocol
→ Qt main-thread dispatcher
→ FreeCADDocumentAdapter facade
→ freecad.sketch_rectangle_creation
→ shared geometry and constraint translators
→ SketchObject.addGeometry / addConstraint
→ recompute and controlled semantic inspection
```

No layer invokes `add_sketch_geometry` or `add_sketch_constraints` through MCP,
and the native adapter has no dependency on command, application, or MCP
layers. The production path does not activate the Sketcher GUI Rectangle
command, edit mode, selection, mouse input, auto-constraint preferences, or
construction-mode state.

The strict request requires exact internal `document_name` and `sketch_name`,
finite positive `width` and `height`, and one strict placement object:

```json
{"type": "lower_left", "x": 0.0, "y": 0.0}
```

`lower_left` is the entire initial placement union. All request levels reject
additional properties, booleans, NaN, and infinity. This milestone does not
expose centre, rotation, construction, partial-constraint, helper, profile-ID,
editing, or deletion controls.

The adapter precomputes four normal `LineSegment` inputs and the complete
constraint plan before opening a transaction. Geometry order and orientation
are explicit: bottom lower-left→lower-right, right lower-right→upper-right, top
upper-right→upper-left, and left upper-left→lower-left. Public corner order is
lower-left, lower-right, upper-right, upper-left. The response serializes those
names explicitly instead of deriving public meaning from mapping iteration or
assuming geometry index zero.

Constraint order is four endpoint coincidences, horizontal/vertical on all
four edges, whole-line length on bottom and right, then lower-left placement.
At the origin, placement is one origin coincidence. On only the vertical axis,
it is vertical-axis `PointOnObject` plus signed Y distance; on only the
horizontal axis, it is horizontal-axis `PointOnObject` plus signed X distance;
away from both axes, it is signed X and Y distances. This is the smallest
deterministic natural set for the four branches and adds no helper geometry.
The pre-existing 17 public constraint variants and primitive tool contracts are
unchanged.

The semantic adapter snapshots the complete geometry/constraint signatures,
construction and constraint flags, cached solver facts, Body/attachment/MapMode
context, sketch placement, document summary, and history state. If it owns the
transaction, it temporarily makes the target document active before opening
`Create sketch rectangle`; this prevents FreeCAD's native transaction
propagation from adding a step to another active document. A caller-owned
transaction remains open and is neither nested nor committed by the operation.

Four lines and every constraint are appended individually so assigned indices
and incremental/final counts can be checked. After recompute, controlled
readback must prove exact types, normal construction state, order, endpoints,
closed coincident chain, axis alignment, dimensions, requested lower-left and
derived upper-right, expected constraint records, zero degrees of freedom,
full constraint, and empty conflicting, redundant, partially redundant, and
malformed diagnostics. The exact document and sketch must remain readable;
Body ownership, attachment, MapMode, placement, pre-existing content, file
path, and unrelated documents must be unchanged. Only then is an owned
transaction committed.

Any failure removes appended constraints and geometry in reverse, aborts an
owned transaction, restores solver-moved geometry, construction and constraint
flags, recomputes when the original solver snapshot was fresh, restores the GUI
modified flag, and verifies exact restoration plus unchanged history. A failed
call returns a controlled rectangle geometry, constraint, verification, or
rollback error and intentionally creates no undo step. It must not be followed
by `undo_document`.

A successful call returns a `SketchRectangleProfile` plus the existing
controlled sketch inspection and document summary. The profile contains current
sketch-local geometry and constraint indices, explicit edge/corner mappings,
dimensions, placement, and verified closed/axis-aligned/fully-constrained
facts. It does not claim a persistent FreeCAD profile object. One owned call is
one history entry. Matching undo removes the entire rectangle, redo restores
it, and a new mutation after undo invalidates redo. A strategically misplaced
success is corrected by matching and undoing `Create sketch rectangle`, then
retrying in the same sketch. Saved files are never written by creation,
rollback, undo, or redo; unsaved documents remain pathless.

## Semantic Centred Rectangle Profile

Milestone 15B adds a second semantic profile without widening Milestone 15A's
lower-left placement union:

```text
create_sketch_centered_rectangle MCP registration
→ CreateSketchCenteredRectangleHandler / application
→ DocumentAdapter.create_sketch_centered_rectangle protocol
→ Qt main-thread dispatcher
→ FreeCADDocumentAdapter facade
→ freecad.sketch_centered_rectangle_creation
→ shared sketch_rectangle_profile geometry/verification helpers
→ shared geometry and constraint translators
→ SketchObject.addGeometry / addConstraint
→ recompute and controlled semantic inspection
```

The strict public request contains exact document and sketch names, finite
positive width and height, and `center` with exactly finite strict numeric `x`
and `y`. It does not contain `placement`, native indices, construction options,
or a branch selector. Tool 16 remains lower-left-only; tool 17 is centre-only;
all first-sixteen schemas and all 17 constraint variants remain unchanged.

`sketch_rectangle_profile` owns the shared bounds, four edge inputs, common ten
closure/orientation/dimension constraints, point references, and semantic edge
verification. The lower-left adapter calls those helpers with lower-left
bounds. The centred adapter calls them with centre-derived bounds, then adds
exactly one construction `Part.Point`. It never calls the lower-left handler,
adapter entry point, primitive MCP tools, or a GUI command.

Geometry append order is bottom, right, top, left, centre point. The four line
indices remain the profile's `geometry_indices`; the point is returned in
`reference_geometry_indices` and through a controlled `point` centre
reference. There are four normal edges, one semantic construction reference,
and zero incidental helpers. The point is used directly as the centre of one
symmetry constraint between the lower-left and upper-right corners. No
diagonal, centre line, helper circle, or duplicate point is created.

Constraint order is the shared four coincidences, four orientations, width and
height, then centre symmetry and centre placement. At the origin placement is
one point-to-origin coincidence. On the vertical axis it is
`point_on_object` plus signed Y distance; on the horizontal axis it is
`point_on_object` plus signed X distance; away from both it is signed X and Y
distance. Installed FreeCAD 1.1.1 evidence proves 12 constraints at the origin
and 13 on each non-origin branch, zero DoF, full constraint, and no redundant,
partially redundant, conflicting, or malformed constraints.

The adapter uses the same complete snapshot and caller-owned transaction
contract as tool 16. An owned operation opens exactly `Create centered sketch
rectangle`, appends and verifies each index/count/construction transition,
recomputes, performs controlled semantic readback, and commits only after full
verification. Verification includes the five-element append range, line/point
types, order, exact corners, closure, axis alignment, dimensions, requested
centre, diagonal midpoint, direct symmetry, placement references, clean solver,
unchanged pre-existing signatures, Body ownership, support, MapMode, placement,
document identity, and file path.

Failure deletes appended constraints in reverse, then the centre point and
edges in reverse, aborts only an owned transaction, restores solver-moved
pre-existing geometry and all construction/constraint flags, recomputes when
appropriate, and verifies the full snapshot and history state. A caller-owned
transaction stays active and is neither nested nor committed. A failed call
creates no history entry and needs no undo.

A successful owned call is one undo step. Exact-name undo removes four edges,
the centre reference, and all constraints while preserving the same sketch and
earlier content; redo restores order, construction state, mappings, and the
fully constrained result. A new mutation invalidates redo. Recovery from a
wrong centre uses the same sketch and the exact `Create centered sketch
rectangle` name. Create, undo, and redo never save: unsaved documents stay
pathless and explicitly saved file bytes and timestamps remain unchanged.
Body-owned and supported attached sketches keep ownership, support, MapMode,
placement, and identity throughout.

## Semantic Polygon Profiles

Milestone 15C adds two public contracts backed by one implementation path:

```text
create_sketch_equilateral_triangle MCP registration
→ CreateSketchEquilateralTriangleHandler (forces side_count = 3)
→ SketchPolygonAdapter protocol
→ FreeCADDocumentAdapter.create_sketch_polygon
→ freecad.sketch_polygon_creation

create_sketch_regular_polygon MCP registration
→ CreateSketchRegularPolygonHandler (preserves validated side_count)
→ the same SketchPolygonAdapter and native engine
```

The public transport and commands have no FreeCAD imports. The shared adapter
uses the existing geometry and constraint translators and core
`SketchObject.addGeometry` / `addConstraint` bindings. It does not call either
polygon tool, the rectangle tools, primitive MCP tools, GUI commands, edit mode,
selection, input simulation, or automatic-constraint preferences.

Both profiles are defined by centre `(cx, cy)`, circumradius `r`, first-vertex
angle `a` in degrees, and side count `n`; triangle fixes `n = 3`. Circumradius
is centre-to-vertex distance. The polygon contract admits strict integer values
3–64; 64 bounds response size and native solver work while covering common
profile use. Vertex `i` is calculated at `a + i*360/n`, positive angles are
counter-clockwise, and public readback normalizes finite negative or wrapped
inputs modulo 360 to `[0,360)`. Edge `i` is vertex `i` to vertex `(i+1) mod n`.

Append order is N normal line segments, one construction `Part.Point` at the
semantic centre, then one construction `Part.Circle` at that centre with the
requested circumradius. The explicit circumcircle is not incidental or hidden:
FreeCAD 1.1.1 source and installed-runtime probes established it as the stable
natural mechanism for one radius dimension shared by every vertex. The result
therefore returns the centre and circle as distinct
`reference_geometry_indices`, plus a controlled `circumcircle_reference`.
The reference audit used FreeCAD revision
`0108fd4b4850cc46e625b60e53cea7a7bbe69f8d`: GUI polygon handling in
`DrawSketchHandlerPolygon.h` and `CommandCreateGeo.cpp`, the Python profile in
`ProfileLib/RegularPolygon.py`, bindings in `SketchObjectPyImp.cpp` and
`ConstraintPyImp.cpp`, constraint declarations/implementation in
`Constraint.h`/`Constraint.cpp`, solver setup in `Sketch.cpp`, document and
sketch transaction behavior in `Document.cpp` and `SketchObject.cpp`, and
Planegcs behavior in `planegcs/GCS.cpp`. Official Create Regular Polygon and
Sketcher scripting documentation supplied the user-facing circumscribed-circle,
centre/first-point, and API semantics. Installed 1.1.1 probes covered side
counts 3, 4, 5, 6, 12, and 64, origin/arbitrary centres, -30/390-degree angles,
native `Part.LineSegment`/`Part.Point`/`Part.Circle` constructors,
`Sketcher.Constraint` forms, solver diagnostics, and history transitions.

The exact constraint sequence is:

1. N endpoint coincidences closing every adjacent edge pair.
2. N−1 equal constraints from edge zero to each later edge.
3. N point-on-object constraints placing each edge end on the circumcircle.
4. One centre-point/circle-centre coincidence.
5. Natural centre placement: one origin coincidence at `(0,0)`; otherwise an
   axis membership and signed dimension on an axis, or signed X and Y
   dimensions away from both axes.
6. One radius dimension on the circumcircle.
7. One angle dimension on edge zero, derived as `a + 90 + 180/n` degrees.

Consequently, the exact count is `3N+3` at the origin and `3N+4` for every
non-origin centre. This uses one natural radius and one orientation dimension;
it does not constrain every vertex by calculated X/Y coordinates or dimension
every edge or radius separately.

The adapter precomputes geometry and constraints before transaction mutation,
then verifies each assigned index, incremental count, and construction state.
After recompute, controlled readback must prove exact append ranges and types,
deterministic endpoint mapping, closure, positive signed area, equal side
lengths, requested centre and circumradius, normalized first-vertex angle,
equilateral 60-degree internal angles for the triangle contract, expected
constraint records, zero DoF, and empty redundant, partially redundant,
conflicting, and malformed diagnostics. Pre-existing geometry/constraints,
Body ownership, attachment, MapMode, placement, document identity, active
document, and file path must remain unchanged.

Owned calls use exactly `Create sketch equilateral triangle` or `Create sketch
regular polygon` and commit once only after verification. A pending
caller-owned transaction is not nested, committed, or aborted. Failure removes
new constraints and geometry in reverse, restores the full snapshot including
solver-moved content and construction/constraint flags, and verifies unchanged
history. Exact-name undo and redo remove and restore the whole semantic profile,
including both construction references. A new mutation after undo invalidates
redo. Recovery from a strategically wrong success occurs in the same sketch;
create/undo/redo never save and preserve saved file bytes and unsaved path state.

The profiles do not create persistent native profile objects or identifiers.
Polygon by side length/apothem, irregular/star/self-intersecting or construction
profiles, profile editing/removal, automatic sketch/Body creation, and automatic
saving remain outside the contract. The existing first seventeen tools and
seventeen constraint discriminators remain unchanged.

## Semantic Curved Profiles

Milestone 16 appends two public contracts while keeping the first nineteen
tool names, request/result schemas, transaction labels, rectangle/polygon
semantics, and the 17-way public constraint union unchanged:

```text
create_sketch_slot MCP registration
→ CreateSketchSlotHandler
→ SketchCurvedProfileAdapter.create_sketch_slot
→ freecad.sketch_slot_creation
→ freecad.sketch_curved_profile_creation
→ freecad.sketch_curved_profile

create_sketch_rounded_rectangle MCP registration
→ CreateSketchRoundedRectangleHandler
→ SketchCurvedProfileAdapter.create_sketch_rounded_rectangle
→ freecad.sketch_rounded_rectangle_creation
→ the same curved-profile creation and verification infrastructure
```

The focused profile modules own their deterministic coordinate and native
constraint plans. The shared pure module owns bounded-arc facts, endpoint
extraction, line/arc tangent tests, closed topology, traversal, analytic signed
area, sweep direction/magnitude, and result join construction. The shared
FreeCAD adapter owns `Part.LineSegment`, `Part.Circle`, `Part.ArcOfCircle`, and
`Sketcher.Constraint` construction, index/count transitions, recompute,
controlled readback, full snapshot verification, transaction commit, and mixed
geometry rollback. MCP-to-MCP calls, rectangle-tool delegation, GUI commands,
edit mode, selection, automatic constraints, and hidden helper geometry are
absent.

The source audit targeted installed revision
`0108fd4b4850cc46e625b60e53cea7a7bbe69f8d`. Relevant primary sources were
`DrawSketchHandlerSlot.h`, the rounded-rectangle sections of
`DrawSketchHandlerRectangle.h`, `CommandCreateGeo.cpp`,
`SketchObjectPyImp.cpp`, `ConstraintPyImp.cpp`, `Constraint.cpp`, `Sketch.cpp`,
`SketchObject.cpp`, `Document.cpp`, and Planegcs constraint sources. The GUI
slot implementation confirmed native endpoint-position tangent constraints and
equal arcs; the rounded-rectangle implementation confirmed bounded tangent
joins and shared radii. Python bindings confirmed bounded
`Part.ArcOfCircle` insertion, and document sources confirmed open/commit/abort
and undo restoration behavior. GUI implementations are evidence only and are
never invoked in production.

Installed FreeCAD 1.1.1 / Python 3.11.14 probes established the final slot
strategy. Append order is top line, right semicircle, bottom line, left
semicircle. Stored directions form the true counter-clockwise traversal top →
left arc → bottom → right arc. Four endpoint tangencies jointly constrain
bounded contact and tangent direction, followed by one arc equality. Centre at
the origin uses symmetry of the arc centres; other centres use signed placement
of the left arc centre. One arc-centre distance expresses
`overall_length - overall_width`, one radius expresses
`overall_width / 2`, and one bottom-line angle expresses orientation. Counts
are exactly 9 at origin and 10 otherwise.

Rounded-rectangle append and traversal order is bottom, lower-right arc, right,
upper-right arc, top, upper-left arc, left, lower-left arc. Eight endpoint
tangencies close all bounded line/arc joins; three equalities share four radii;
two horizontal and two vertical constraints preserve axes; centre distances
between corner arcs express `width - 2r` and `height - 2r`; one radius preserves
`r`. Centre-at-origin uses opposite corner-centre symmetry, while every other
placement uses signed lower-left corner-centre coordinates. Counts are exactly
19 for centre-at-origin and 20 otherwise.

The endpoint-tangent constructor is internal to these fully specified semantic
profiles. The public primitive `tangent` request remains whole-geometry-only,
and established general sketch-inspection behavior is unchanged. The curved
adapter compares exact native geometry/position fields, checks every bounded
endpoint coordinate and tangent direction, verifies 180° or 90° visible CCW
sweeps, positive signed area, dimensions, centre/bounds, exact constraint
ranges, zero DoF, and clean redundant/partial/conflict/malformed diagnostics.
Results expose controlled bounded arcs and joins without native objects.

Both tools snapshot geometry including arc parameters, construction flags,
constraints, solver state, Body/support/MapMode/placement context, document
identity/file state, and history before mutation. An owned operation opens
exactly `Create sketch slot` or `Create sketch rounded rectangle` and commits
only after semantic verification. Failure removes constraints and mixed
geometry in reverse, aborts only an owned transaction, restores solver-moved
content and flags, and verifies exact history restoration. Caller-owned
transactions are never nested, committed, or aborted. Exact-name undo/redo
removes/restores a complete profile; an intervening correction in the same
sketch invalidates redo. Creation never saves.

The direct embedded-runtime campaign is
`scripts/smoke_sketch_curved_profiles.py`. It records 78 named scenarios,
including the two product fixtures, negative/wrapped angles, near-degenerate
valid branches, non-empty/attached/saved contexts, injected geometry/arc/
tangent/verification rollback, history and same-sketch recovery, all earlier
profile regressions, tool selection, and raw-object exclusion.

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

## Controlled Document History

The history path preserves the normal dependency direction:

```text
MCP history tool
→ Application / typed history handler
→ DocumentAdapter protocol
→ Qt main-thread dispatcher
→ freecad.document_history
→ exact named App::Document
```

The public models are `DocumentHistorySnapshot`,
`DocumentHistoryInspectionResult`, `DocumentHistoryTransaction`, and
`DocumentHistoryOperationResult`. A snapshot contains only counts, availability,
the current top undo and redo names, pending-transaction state, and the existing
controlled document summary. Native transaction objects, IDs, internal nodes,
and complete stack entries never cross the adapter boundary. Top names are
current-step safety labels and are not durable identifiers.

FreeCAD 1.1.1 exposes the required Python state as `UndoMode`, `UndoCount`,
`RedoCount`, `UndoNames`, `RedoNames`, and `HasPendingTransaction`. `UndoNames`
and `RedoNames` are top-first. The Python-bound `undo()` and `redo()` methods
return `None` on the normal path even though the underlying C++ methods return
a Boolean, so the adapter accepts native `None` and treats an explicit injected
`False` as failure. It never opens a transaction around native history
movement: doing so would create unsafe grouping and could make undo itself
user-visible history.

Before mutation, the adapter requires the exact named document to remain open,
enabled readable history, no pending transaction, no MCP-owned undo, redo, or
rollback already in progress, an available entry in the requested direction,
and a readable non-empty top name. When `expected_transaction_name` is supplied,
matching is exact and case-sensitive; mismatch performs no native call. The
request schema forbids extra fields, including multi-step counts and native IDs.

After native undo, the adapter verifies the complete internal top-first name
transition is exactly `undo[1:]` and `(moved_name, *redo)`. Redo verifies the
inverse. It also verifies history remains enabled, no transaction remains
pending, the same document object remains open under the requested name, and
the controlled document summary is readable. The full names are used only for
internal verification and are never returned. An inconsistent native result is
reported as `document_history_verification_failed`; the adapter does not hide
it with an automatic compensating history operation.

Model mutations use the central safety labels `Create body`, `Create sketch`,
`Add sketch geometry`, `Add sketch constraints`, `Create sketch rectangle`,
`Create centered sketch rectangle`, `Create sketch equilateral triangle`, and
`Create sketch regular polygon`.
Document creation, saving, recomputation, and inspection do not create an
MCP-owned undo transaction.
Atomic-operation rollback remains separate from controlled undo: rollback
removes a failed call's partial mutation, while undo removes one successful but
unwanted transaction. Rollback paths enter the same process-local activity guard
so a re-entrant history request is rejected.

Undo and redo are deliberately in-memory, one-step operations. They never save,
reverse a prior save, change an external file, clear history, or switch undo
mode. They target the named document even when another document is active.
An installed FreeCAD 1.1.1 full-GUI probe set a document clean, committed one
transaction, and observed `FreeCADGui.Document.Modified` as true after the
mutation, its undo, and its redo. The adapter reports that native GUI dirty flag
without trying to infer equality with a prior saved state.
FreeCAD leaves relevant sketches touched after undo/redo, so the adapter does
not recompute and `get_sketch` reports cached solver data as stale. Clients must
explicitly call `recompute_document` and inspect again. A new committed model
mutation follows native FreeCAD semantics and invalidates the redo stack.

Agent recovery should use this capability after a successful operation proves
strategically wrong: recompute and inspect, inspect history, match and undo the
known step, inspect the restored state, then correct the same sketch or model.
It must not undo a failed call that already rolled back, or an unexpected GUI
or user step whose ownership is unclear.

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

## Sketch Constraint Mutation

### add_sketch_constraints

`add_sketch_constraints` is the controlled atomic constraint-creation path for
an existing `Sketcher::SketchObject`. Its dependency flow is:

```text
MCP sketch-constraint registration
→ add-sketch-constraints command handler
→ protocols, models, exceptions and validation
→ FreeCADDocumentAdapter facade
→ focused sketch-constraint-creation module
→ Qt main-thread dispatcher
→ FreeCAD Sketcher API
```

The focused responsibilities live in
`commands/sketch_constraints.py`, `freecad/sketch_constraint_creation.py`, and
`mcp/sketch_constraint_tools.py`. Models, validation, commands, and transport
do not import FreeCAD. `FreeCADDocumentAdapter` remains publicly importable from
`freecad_mcp.freecad.document`; there is no generic constraint registry,
registration loop, arbitrary property mutation, or raw constructor passthrough.

#### Input Models and Units

The top-level schema requires exactly `document_name`, `sketch_name`, and a
`constraints` array with 1 to 100 items. Both names use exact internal-name
lookup. The strict nested discriminated union has 17 top-level variants and
supports:

```text
horizontal / vertical
  geometry_index

horizontal_points / vertical_points
  first, second: two distinct controlled geometry points

parallel / perpendicular / equal
  first_geometry_index, second_geometry_index

coincident
  first, second: exactly one geometry point plus origin, or two geometry points

point_on_object
  first: one controlled geometry point
  second: one whole line/circle/circular-arc reference or controlled sketch axis

symmetric
  first, second: two distinct geometry points
  about: origin, horizontal axis, vertical axis, a distinct geometry point,
         or one line-segment geometry reference

tangent
  first, second: two distinct strict whole-geometry references

distance
  line_length: geometry_index, value
  point_to_origin: point, value
  between_points: first, second, value

distance_x / distance_y
  point_to_origin: point, value
  between_points: first, second, value

radius / diameter
  geometry_index, value

angle
  line_angle: geometry_index, value_degrees
  between_lines: first_geometry_index, second_geometry_index, value_degrees
```

A geometry-point reference is `{geometry_index, position}`. Public position tokens map
to verified FreeCAD point-position integers as `start → 1`, `end → 2`,
`center → 3`, and `point → 1` for `Part.Point`. The adapter admits
`start`/`end` for lines, `start`/`end`/`center` for circular arcs, `center` for
circles, and `point` for point geometry. Strict native-sketch references add
exactly `{"reference": "origin"}`, `{"reference": "horizontal_axis"}`, and
`{"reference": "vertical_axis"}`. Origin is accepted by `coincident` and as a
symmetry centre; the two axes are accepted by `point_on_object` and as symmetry
lines. Both public orders are accepted by the existing two-sided reference
constraints. A symmetric line reference is the strict
`{"geometry_index": non_negative_integer}` shape and is resolved only in the
FreeCAD layer. Unknown literals, additional reference fields, raw negative
geometry IDs, external geometry, and internal geometry are rejected.

For ordinary `point_on_object`, the selected point is `first` and `second` is
the same strict whole-geometry reference shape used elsewhere:
`{"geometry_index": non_negative_integer}`. The adapter resolves that target
only to `Part.LineSegment`, `Part.Circle`, or `Part.ArcOfCircle`; no point
position accompanies the target. The established reverse public order remains
accepted only for legacy axis-target requests. `horizontal_points` and
`vertical_points` reuse the exact existing selectable-point model and do not
overload the one-field whole-line `horizontal` and `vertical` variants.

The focused FreeCAD layer alone translates `origin` to the native root point,
`horizontal_axis` to the native horizontal sketch axis, and `vertical_axis` to
the native vertical sketch axis. FreeCAD 1.1.1 verification confirmed that
origin membership is a native `Coincident` constraint and axis membership is a
native `PointOnObject` constraint. No construction geometry or zero-valued X/Y
distance constraints are synthesized. The existing explicit Euclidean
`point_to_origin` modes and their controlled inspection readback are unchanged.

FreeCAD 1.1.1 source and runtime verification locks three additional native
translations. Ordinary membership uses
`PointOnObject(point_geometry, point_position, target_geometry)`, whose legacy
readback has `SecondPos == 0`. Point-pair alignment uses the four-index
`Horizontal(first_geometry, first_position, second_geometry, second_position)`
or matching `Vertical` form. Whole-line orientation retains the one-index
constructors and reads back with `FirstPos == 0` and an unused second geometry.
FreeCAD's Python wrapper exposes only the legacy first/second/third fields for
these records in the installed build; generic element access is not public.
The solver source admits more curve targets than this controlled contract, but
the adapter deliberately limits ordinary targets to lines, circles, and
circular arcs.

Controlled direct tangency uses exactly the native two-index constructor
`Tangent(first_geometry, second_geometry)`. The accepted compatibility matrix
is line-circle, line-circular-arc, circle-circle, circle-circular-arc, and
circular-arc-circular-arc, with both orders accepted for heterogeneous pairs.
No selected point, contact point, branch flag, or helper constraint is exposed
or synthesized. Official FreeCAD 1.1.1 source and the installed build confirm
that line tangency is a centre-to-infinite-line/radius relationship and curved
pairs use centre/radius circumferential tangency. The solver chooses the branch
from initial placement. For circular arcs, direct native tangency constrains
the underlying support circle rather than requiring the contact point to lie in
the visible parameter interval.

For controlled symmetry, the FreeCAD layer selects one of the two verified
native constructor forms: two points plus a third point for origin/geometry
point symmetry, or two points plus a whole line for axis/line-segment symmetry.
The matching Python-bound constraint stores the selected points as its first
two element pairs; point-centred symmetry has a point-qualified third element,
while line-centred symmetry has a whole-edge third element. This behavior was
verified against FreeCAD's official `ConstraintPyImp.cpp`, the legacy/readback
fields in `Constraint.h`, the internal solve behavior in
`SketchObjectPyImp.cpp`, and the installed 1.1.1 build at commit
`0108fd4b4850cc46e625b60e53cea7a7bbe69f8d`.

Lengths are public millimetres. Euclidean distances, radii, and diameters are
strict finite positive values. Signed and zero `distance_x`/`distance_y` values
are preserved. Angles are strict finite degrees converted directly to radians.
FreeCAD 1.1.1 stores the supplied radians without normalization and accepts
zero, ±180°, full turns, and values beyond a full turn. The public contract
therefore performs no normalization; line direction controls absolute and
between-line orientation semantics.

#### Geometry Compatibility and Validation Boundary

Pure request validation rejects malformed unions, missing/additional fields,
unsupported discriminators or modes, non-integer or negative indices, invalid
position tokens, same-geometry pairs, origin-to-origin pairs, invalid native
reference combinations, nonnumeric/non-finite values, nonpositive unsigned
dimensions, identical symmetric points, a centre identical to either selected
point, degenerate own-line symmetry, identical tangent geometries, tangent
references with positions or additional fields, empty batches, and batches
above 100.
Before opening a transaction,
the FreeCAD adapter resolves every current index and enforces:

- horizontal, vertical, parallel, perpendicular, line length, and angles:
  `Part.LineSegment` only;
- equal: line-to-line or any circle/circular-arc pair;
- coincident, point-on-object, point-pair alignment, and point distances: only
  point tokens valid for the runtime geometry type;
- ordinary point-on-object targets: line segment, circle, or circular arc only,
  never the selected point's own geometry; point geometry, unsupported curves,
  and out-of-range targets fail before the transaction;
- horizontal-points and vertical-points: two non-identical selected points;
  distinct endpoints of the same line remain valid, with whole-line forms
  preferred for simple line orientation;
- symmetric: both selected points and any point-centre must use valid tokens;
  a whole-line centre must resolve specifically to `Part.LineSegment`;
- tangent: both references resolve to line, circle, or circular arc; two lines,
  point/unsupported geometry, identical indices, and out-of-range indices fail
  before a transaction, while construction state has no effect;
- radius and diameter: `Part.Circle` or `Part.ArcOfCircle` only.

Construction geometry is valid under the same rules. Standalone and attached
sketches share the same path. FreeCAD constructor acceptance is not treated as
validation: the 1.1.1 binding can append incompatible or malformed constraints
and report them only through solver state.

#### Transaction, Rollback, and Solver Policy

The adapter snapshots geometry and construction state plus every existing
constraint's type, three geometry/position pairs, dimensional value, name,
driving flag, active flag, and virtual-space flag. The rollback snapshot also
records the document file name, Body ownership, attachment support, and map
mode. It observes
`Document.HasPendingTransaction`: with no pending transaction it opens exactly
one `MCP Add Sketch Constraints` transaction and owns the matching commit or
abort; with a pending caller transaction it does not open, commit, or abort it.

Each constraint is constructed and added in request order. Assigned indices,
incremental counts, final count, and returned-index count are verified. Success
commits once only when the transaction is owned. With undo enabled, that owned
batch is expected to be one undo/redo step; caller-owned grouping remains the
caller's responsibility.

On any post-open failure, appended tail constraints are deleted in reverse,
the owned transaction is aborted, safe tail cleanup is repeated, and existing
constraint flags are restored where needed. Because FreeCAD's Python
`addConstraint` binding internally sets up and solves the sketch and may move
geometry immediately, rollback compares and, only when required, restores the
captured geometry property and construction flags. It then verifies constraint
count and complete constraint state, geometry and construction state, and
document path, Body ownership, attachment support, map mode, and transaction
ownership. A failure of any restoration or verification becomes
`sketch_constraint_rollback_failed`; no partial index list is returned.

The tool itself never calls `Sketch.solve()`, `Document.recompute()`,
`evaluateConstraints()`, `validateConstraints()`, `save()`, or `saveAs()`.
FreeCAD's internal add-binding solve is distinguished from an explicit tool
solve. The document remains touched and `get_sketch` treats solver facts as
stale until the client explicitly calls `recompute_document`. Redundancy and
conflicts are not speculative request failures.

A successfully solved but unintended tangent branch is likewise not an atomic
creation failure. The controlled recovery path is to inspect history, undo the
known top `Add sketch constraints` transaction, correct placement or strategy
in the same sketch, reapply tangency, recompute, and inspect. The next mutation
invalidates the abandoned redo branch. Failed atomic creation already restores
zero mutation and must not be followed by an extra undo.

#### Result, Errors, and Non-Goals

Success code `sketch_constraints_added` returns `document_name`, `sketch_name`,
ordered `added_indices`, derived `added_count`, final `constraint_count`, and
`Sketch constraints added.`. Indices are immediate state only and clients must
call `get_sketch` after mutation.

Public error codes are `validation_error`, `document_not_found`,
`sketch_not_found`, `sketch_type_mismatch`,
`sketch_constraint_creation_failed`, `sketch_constraint_rollback_failed`, and
`internal_error`. Controlled reasons include `empty_constraint_batch`,
`constraint_batch_too_large`, `unsupported_constraint_type`,
`invalid_constraint_input`, `invalid_geometry_reference`,
`geometry_reference_out_of_range`, `invalid_position_reference`,
`same_geometry_reference`, `same_origin_reference`, `unsupported_reference`,
`invalid_point_reference`, `invalid_constraint_value`, and
`incompatible_geometry_type`, plus the focused symmetric reasons
`identical_symmetric_points`, `identical_symmetry_centre`, and
`degenerate_symmetry_line`, plus `identical_point_references`,
`point_on_object_self_target`, and `unsupported_point_on_object_target`, plus
`identical_tangent_geometry`, `incompatible_tangent_geometry_pair`, and
`unsupported_tangent_geometry`, plus
transaction/index/count/rollback
reasons. Raw FreeCAD exception text is never public.

Version one creates only active driving dimensional constraints. Point-specific
tangency, line-line tangency, block, internal alignment, angle-via-point,
B-spline-specific and
arbitrary reference constraints; expressions, names, editing and deletion; and
external/internal geometry references remain unsupported. Axis references are
limited to native `point_on_object` and the `about` side of `symmetric`.

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

Constraint inspection preserves the existing ordered `references` array. A
native origin coincidence is returned with the geometry-point reference plus
`{"reference": "origin"}` in the order stored by FreeCAD. Native
`PointOnObject` axis membership is returned as the geometry point plus
`{"reference": "horizontal_axis"}` or `{"reference": "vertical_axis"}`.
Ordinary membership returns the selected point plus a non-negative controlled
geometry reference with `position: edge`; target construction state is retained
on the geometry record rather than duplicated on the constraint. Four-index
native `Horizontal` and `Vertical` records return `horizontal_points` and
`vertical_points` with two semantic point references, while one-index records
remain `horizontal` and `vertical` with one edge reference.
Supported native `Symmetric` constraints return `type: symmetric` and exactly
three controlled references in stored first/second/about order. The about
reference is reconstructed as `origin`, either native axis, a geometry point,
or a line geometry reference with `position: edge`. Incompatible or degenerate
native symmetric records become controlled `unsupported` records without
breaking inspection of the remaining constraints.
Supported native two-index `Tangent` records return `type: tangent` and exactly
two non-negative controlled geometry references with `position: edge` in
stored first/second order. Inspection admits only the public line-circle,
line-arc, circle-circle, circle-arc, and arc-arc matrix. Point-specific,
line-line, identical, out-of-range, position-qualified, and otherwise malformed
tangent records become one controlled `unsupported` record without exposing
native fields or interrupting inspection of later constraints.
Degenerate, unsupported-target, or out-of-range records in the new point
relationship forms likewise become one controlled `unsupported` record so the
following native constraints remain inspectable.
Private root/axis IDs never cross the adapter boundary. Constraint type is
interpreted together with point position: an axis-like native ID in a
`Coincident` record is not misreported as origin or as controlled
`point_on_object`.

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
