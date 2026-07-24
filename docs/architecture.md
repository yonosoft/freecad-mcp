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
Controlled external-reference enumeration and mutation belong to
`freecad.sketch_external_geometry`; read-only attachment, expression,
constraint, consumer, broken, and cross-document dependency extraction belongs
to `freecad.sketch_dependencies`. Both remain behind the same adapter facade,
but only the former owns transactions.
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
`mcp.sketch_polyline_tools` explicitly appends the semantic connected polyline
profile.
`mcp.sketch_curved_profile_tools` explicitly appends the semantic slot and
rounded-rectangle profiles.
`mcp.sketch_analysis_tools` explicitly appends read-only sketch analysis,
profile validation, and open-vertex location.
`mcp.sketch_external_geometry_tools` explicitly appends controlled external
geometry add/list/remove and sketch dependency inspection.
`mcp.sketch_removal_tools`, `mcp.sketch_editing_tools`, and
`mcp.sketch_reference_constraint_tools` append tools 29–35.
`mcp.sketch_constraint_expression_tools` explicitly appends constraint naming,
expression set/clear, and expression listing as tools 36–39.
`mcp.sketch_topology_editing_tools` appends trim, split, and extend as tools
40–42. `mcp.sketch_geometry_transform_tools` appends the six copy-only
transform tools at 43–48. `mcp.sketch_constraint_state_tools` appends driving,
active, and virtual-space state management as tools 49–51.
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
`create_sketch_rounded_rectangle` are exactly tools twenty and twenty-one;
`analyze_sketch`, `validate_sketch_profile`, and
`list_sketch_open_vertices` are exactly tools twenty-two through twenty-four;
`add_external_geometry`, `list_external_geometry`, `remove_external_geometry`,
and `get_sketch_dependencies` are exactly tools twenty-five through
twenty-eight; removal/construction tools are 29–31, editing tools are 32–34,
reference-constraint addition is 35, constraint name/expression tools are
36–39, topology-editing tools are 40–42, geometry-transform tools are 43–48,
and constraint-state tools are 49–51.
No registration loop is used.
Registration modules depend on handlers and the tool registry, never on the
concrete FreeCAD adapter.

A dependency-free tool registry is the authoritative source for tool names and
ordering. FastMCP registration and lifecycle status both consume that registry,
so reported capabilities cannot drift from the registered set.

The registry currently exposes exactly 54 public tools. The maintained
[public tool inventory](public-tool-inventory.md) records their exact names and
order without duplicating registration definitions in architecture prose.

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

## Shared Sketch Analysis Engine

The three analysis tools are separate public operations over one implementation
path:

```text
MCP sketch-analysis registration
-> typed analysis command handler
-> SketchAnalysisAdapter protocol
-> FreeCADDocumentAdapter facade
-> focused read-only sketch-analysis adapter
-> existing controlled sketch inspector
-> pure sketch-topology engine
-> controlled result models
```

The FreeCAD-facing adapter resolves the exact named document and sketch,
reuses `sketch_inspection.py` for controlled geometry, constraint, solver, and
attachment data, optionally translates `ExternalGeo`, and then passes ordinary
Python mappings to `sketch_topology.py`. Native objects, native geometry
indices, arbitrary properties, and exception text do not cross that boundary.
External geometry receives result-local negative indices because FreeCAD's
native index convention includes hidden axis slots and is not a stable public
contract.

`sketch_topology.py` has no FreeCAD, Qt, MCP, handler, or runtime imports. It
owns the fixed endpoint tolerance, deterministic clustering, graph components,
open and branch vertices, endpoint-on-edge T junctions, duplicates, negligible
geometry, overlaps, line/arc/circle intersections, closed-loop traversal,
Green-theorem area, orientation, containment, and final classification. The
broad analysis, profile validation, and open-vertex projection functions all
consume the same computed analysis; public tools do not call one another.

Construction and external geometry are visible as controlled counts but do not
participate unless explicitly requested. An optional non-empty, unique list of
non-negative internal geometry indices narrows the profile and opening tools;
it never selects native external references. Points remain informational,
unsupported curves yield controlled findings, and full circles are intrinsic
closed profiles.

The complete path is read-only. It does not open or commit a transaction,
recompute or solve, add or change geometry or constraints, save, move history,
enter edit mode, change selection, or activate a document. Cached solver facts
therefore retain the freshness reported by `get_sketch`. All expected input,
lookup, malformed-data, topology, adapter, and dispatch failures are mapped to
stable command codes without leaking native exception details.

## External Geometry and Dependency Inspection

Milestone 18 adds four separate public operations while leaving the first 24
tool names and schemas and the 17-way sketch-constraint union unchanged:

```text
MCP external-geometry registration
-> typed validation and command handler
-> SketchExternalGeometryAdapter or SketchDependencyAdapter protocol
-> FreeCADDocumentAdapter facade
-> freecad.sketch_external_geometry or freecad.sketch_dependencies
-> controlled result models
```

The input source is a strict discriminated union. `object_subelement` resolves
one canonical positive `EdgeN` or `VertexN` on a same-document non-sketch
object. `sketch_geometry` resolves a zero-based line, circle, or bounded
circular-arc geometry index on another same-document sketch. The public add
contract excludes point and B-spline projection, whole-object projection,
subelement chains, intersection geometry, carbon copy, and cross-document
creation. Duplicate identity is the normalized `(source internal name,
subelement)` pair and is rejected before a transaction opens.

### Observed FreeCAD 1.1.1 native facts

Focused embedded-runtime probes established these facts independently of the
public policy:

- `SketchObject.addExternal(name, subelement, False, False)` creates one normal
  reference and returns `None`; exact native duplicates raise `ValueError`.
- `ExternalGeo` begins with two built-in axes. Public external reference `n`
  appears in constraint geometry fields as native index `-3-n`.
- `ExternalGeometry` groups subelement names by source object; deterministic
  public order requires flattening those groups. A second geometry from the
  same source sketch is appended inside that source's group while producing a
  second flattened projection in the same order. Interleaving another source
  can produce a later group for the original source. `ExternalTypes` uses zero
  for normal references but can retain stale values after removal.
- Object edges and vertices and source-sketch line, circle, and bounded-arc
  geometry project successfully. Point projection did not provide a usable
  controlled result in the tested build.
- FreeCAD container policy remains authoritative. A target sketch inside a
  PartDesign Body rejected an ordinary source object outside that Body in the
  tested build, even though both objects were in the same document.
- Moving or dimensionally changing a source updates a projection after
  recompute. Save/reopen preserves valid mappings.
- `delExternal(n)` returns `None`, renumbers later external identities, and can
  silently delete constraints that use the removed reference.
- Deleting a source may drop its mapping while leaving projection data. With
  more than one source, remaining positions cannot always be reconstructed
  reliably from the surviving grouped mapping.
- Same-document add/remove undo and redo as one named transaction. Native
  cross-document add attempts tested with ordinary and document-qualified names
  were rejected.

These are observations for the verified build, not guarantees of persistent
topological naming. The project does not promise that `EdgeN`/`VertexN` survives
unrelated upstream topology changes.

### Controlled identity and read-only policy

`external_reference_number` is the non-negative position in the target
sketch's current flattened external-reference order. Native negative indices
never cross the adapter boundary. The number is sketch-local and can be
renumbered by removal; it is not a persistent identifier.

Enumeration returns controlled source identity and labels, category, mode,
resolved/broken state, sanitized geometry, and every constraint index using the
reference. If the number of grouped mappings no longer equals the number of
native projections, positional attribution is not provable. The adapter marks
all affected entries unresolved with source `null` and
`source_mapping_incomplete` rather than assigning a potentially wrong source.
Observed cross-document mappings are reported but remain unresolved and outside
the mutation boundary.

`list_external_geometry` and `get_sketch_dependencies` perform no recompute,
solve, transaction, history movement, save, activation, edit-mode transition,
selection change, or repair. Dependency inspection returns controlled external
sources, attachment sources, expression sources, constraint-to-external
mappings, downstream consumers, broken references, and cross-document
observations. Expression parsing deliberately identifies only simple internal
object references that can be represented safely; it is not a general FreeCAD
expression parser. Native objects, raw link arrays, arbitrary properties,
memory addresses, and negative indices never appear in results.

### Mutation, refusal, and rollback policy

An owned add opens exactly `Add sketch external geometry`; an owned removal
opens exactly `Remove sketch external geometry`. Both capture the complete
controlled external mapping, internal geometry and construction flags,
normalized constraints, cached solver state, attachment/Body/placement context,
document identity and path, modified state, active document, selection, edit
mode, history stacks, and pending-transaction state. They mutate once,
recompute, verify complete semantic readback and preserved surroundings, then
commit one history step. They never save.

Removal is narrower than native `delExternal`: used, unresolved, unsupported,
non-normal, and cross-document references are refused before mutation, and no
dependent constraint is ever deleted automatically. An owned transaction may
remove a safe non-tail reference because native abort can restore it exactly. A
caller-owned transaction may remove only its current unused tail reference, for
which the adapter has a proven exact manual inverse; the caller's transaction is
never committed or aborted by this operation.

After failure, owned operations abort and recompute when required to restore a
previously fresh solver snapshot. Caller-owned operations apply only the exact
manual inverse and leave the caller transaction open. Add verification and its
manual inverse locate the new reference through the exact normalized source
identity `(source internal name, native subelement)`, never projected
coordinates, a native negative ID, or an assumed flattened tail. A pre-existing
mapping that cannot be uniquely represented by those identities is rejected
before mutation.

Rollback verifies the complete captured external, sketch, document, history,
solver, and GUI state. The document modified state is required for safe model
restoration. Selection and edit-mode identity are optional observations:
readable values must remain equal, while an unavailable getter or unreadable
value is recorded by field and does not alone block mutation. FreeCAD GUI
`getInEdit()` returns a view provider in the verified build, so the adapter
unwraps its `.Object` before comparing model identity. If exact required-state
restoration cannot be proven, a distinct rollback failure is returned; callers
must not issue undo after an internally restored failure. A wrong successful
reference is recovered by exact-name undo and retry in the same sketch, which
also preserves ordinary redo invalidation semantics.

Known limits are no cascade option, automatic replacement, healing,
topological-name repair, attachment remapping, general cross-document support,
GUI intersection projection, carbon copy, or automatic save.

## Controlled Sketch Removal and Construction State

Tools 29–31 append to the unchanged first 28 registrations:

```text
MCP registration
-> RemoveSketchConstraintsHandler, RemoveSketchGeometryHandler,
   or SetSketchGeometryConstructionHandler
-> SketchControlledMutationAdapter protocol
-> FreeCADDocumentAdapter
-> freecad.sketch_removal
-> Qt main-thread dispatcher
-> SketchObject delConstraint, delGeometry, or toggleConstruction
-> semantic verification and controlled result
```

No public tool calls another MCP tool. The shared internal mutation module owns
snapshot, preflight, transaction, rollback, context-preservation, remapping, and
profile-impact helpers, while each public operation retains a separate request,
handler, error code, transaction label, verification branch, and result type.
All selections are strict non-empty arrays of unique non-negative pre-call
indices. Native negative external IDs never reach `delGeometry` or
`toggleConstruction`.

### Observed native behavior and implemented policy

Focused FreeCAD 1.1.1 probes observed that `delConstraint`, `delGeometry`,
`toggleConstruction`, and `setVirtualSpace` return `None`. Constraint and
geometry identities renumber immediately. Descending deletion therefore
preserves a pre-call multi-selection; ascending geometry deletion can invalidate
a later index. `delGeometry` also silently deletes every dependent constraint
and remaps surviving constraints' geometry references. `toggleConstruction`
preserves constraint content and counts, while forwarding a native negative
external index produced an access-violation error.

Public constraint removal deletes only selected supported constraints in
descending order. It snapshots exact native constraint state and verifies the
survivor sequence, flags, names, values, references, controlled summaries, and
old-to-new mapping. Virtual-space constraints are eligible. Unsupported
controlled readback is refused. Deleting a named expression-backed constraint
clears its attached expression while downstream expressions can remain dangling,
while unnamed constraints can be addressed as `Constraints[index]` and native
deletion renumbers surviving numeric expression paths. Selected named or numeric
dependencies, and numeric references whose target index would change, are
reported and refused before mutation.

Public geometry removal is deliberately narrower than native `delGeometry`.
Preflight examines First/Second/Third native constraint geometry slots and
returns exact selected-geometry to dependent-constraint indices. Any dependency
refuses the complete batch; callers explicitly remove constraints first. Safe
removal verifies the ordered subset of controlled geometry, construction flags,
native constraint-reference remapping, unchanged constraint identities/count,
external mapping, and before/after topology summary. Survivor mapping is derived
from pre-call order and verified against the complete ordered fingerprints; it
does not pretend geometrically identical elements have durable identity.

Construction input is desired-state idempotent. The adapter classifies selected
geometry into changed and already-correct indices, calls `toggleConstruction`
only for changed members, and verifies exact final flags plus unchanged geometry,
constraint, external, attachment, Body, placement, and document context. An
all-correct call does not recompute or open a transaction. The result reports
before/after selected summaries, normal/construction counts, solver readback,
and compact profile impact from the shared Milestone 17 topology engine.

### Transactions, rollback, and identity

Owned changes use exactly one `Remove sketch constraints`, `Remove sketch
geometry`, or `Set sketch geometry construction` transaction. Caller-owned
transactions are neither committed nor aborted. A pre-mutation snapshot contains
cloned ordered geometry, construction flags, native and controlled constraints,
expressions for every document object, external mapping, solver state, Body and
attachment context, placement, history stacks, document summary, active
document, selection, and edit state.

Owned failure aborts its transaction and recomputes only when restoring a
previously fresh solver. Caller-owned failure assigns the snapshotted `Geometry`
and `Constraints`, restores construction and constraint flags, recomputes, and
leaves the caller transaction pending. FreeCAD 1.1.1 probes confirmed these
assignments restore exact ordering, geometry references, names, active and
virtual-space flags. Rollback verifies the complete snapshot, including history
and GUI observations, rather than counts alone. If exact restoration cannot be
proved, a distinct rollback error is returned.

Indices in public results remain current-order-local. Removed entries have no
new index. Every survivor mapping is ordered by `old_index`, and later mutations
may renumber it again. Results contain controlled dataclasses and mappings only;
no native objects, transaction IDs, memory addresses, or negative IDs escape.

Milestone 18 live broken-source mapping reporting remains unverified because the
public MCP API cannot delete or invalidate source objects. It is non-blocking
and remains deferred until a safe fixture or controlled object-deletion
capability exists.

## Controlled Sketch Editing

Tools 32–34 append after the unchanged first 31 registrations:

```text
MCP registration
-> UpdateSketchGeometryHandler, ReplaceSketchConstraintHandler,
   or UpdateSketchConstraintValueHandler
-> SketchEditingAdapter protocol
-> FreeCADDocumentAdapter
-> freecad.sketch_editing
-> Qt main-thread dispatcher
-> SketchObject moveGeometry, delConstraint/addConstraint, or setDatum
-> recompute, solver/profile verification, and controlled result
```

The transport schemas are explicit and closed. Geometry editing has a four-way
same-type union without `construction`; replacement imports the existing
17-variant constraint union directly; datum editing accepts one strict finite
number. The command layer owns validation and stable controlled error envelopes,
while the FreeCAD layer owns native fingerprints, dependency inspection,
transaction/rollback, and semantic comparison. No registration function calls
another MCP tool, and no production path uses GUI commands, edit mode, selection,
or arbitrary Python execution.

### Native facts and public policy

FreeCAD 1.1.1 `SketchObject` has neither `setGeometry` nor `movePoint`.
`moveGeometry(index, point_position, vector, false)` returns `None` and retains
the index for underconstrained lines, points, circles, and circular arcs. Line
positions 1/2 address start/end, point position 1 addresses its point, circle
position 3 moves the center and 0 changes radius through an edge target. For an
arc, moving the center first makes a later endpoint move fail. The proven
sequence is start/end, center, then two start/end passes; it preserves
construction state and converges below `1e-7`.

Because `moveGeometry` solves through temporary weak constraints, actual edits
are limited to geometry with no constraint references in any native reference
slot. Semantic equality is checked first, so an already-correct constrained
item remains a transaction-free no-op. Actual dimensionally controlled edits
return `dimensionally_controlled`; other references return
`dependent_constraints`. Unsupported geometry and type conversion are refused.
Successful verification requires exactly the selected controlled geometry to
change, with geometry/constraint counts, constraint fingerprints, construction,
external mappings, Body/attachment/placement, and surrounding context intact.

`setDatum` returns `None`. Distance, distance-x/y, radius, and diameter requests
are sent as millimetre quantities; angle requests are sent as degree quantities.
Controlled inspection reports the established `millimeter`/`degree` units.
Generic distance, radius, and diameter remain positive; signed distance-x/y and
unwrapped angle requests reuse the add-constraint contract. Reference/driven,
inactive, virtual, geometric, unsupported, and expression-sensitive constraints
are refused. Datum verification preserves every native identity field and every
unrelated constraint fingerprint, while reporting geometry moved legitimately
by the solver.

FreeCAD has no safe constraint-slot replacement. `delConstraint` returns
`None`; `addConstraint` returns the appended index. The public atomic operation
therefore deletes one eligible constraint, appends one controlled replacement,
verifies the exact survivor sequence, and reports the new tail index plus the
complete old-index-ordered survivor mapping. A semantic no-op is detected before
mutation. A replacement equal to another survivor is refused as a duplicate.
Named, expression-sensitive, inactive, virtual, reference, and unsupported
constraints are refused because reconstructing their metadata is outside this
milestone. Fresh solver conflict, redundancy, partial redundancy, malformed
state, or unavailable verification rolls back the complete mutation.

### Transactions, rollback, and comparisons

Owned changes use one exact `Update sketch geometry`, `Replace sketch
constraint`, or `Update sketch constraint value` transaction. Caller-owned
transactions are not committed or aborted. All no-ops precede recompute and
transaction opening. Success requires fresh solver diagnostics, unchanged
ordered state outside the documented target, complete common snapshot equality,
and explicit before/after profile summaries.

The editing adapter reuses the Milestone 19 full-state snapshot and rollback
engine. Owned failures abort; caller-owned failures restore native geometry and
constraint snapshots while leaving the caller transaction open. Verification
covers ordered geometry/constraints, dimensional values, names, expressions,
active/virtual/driving flags, construction, external mappings, attachment, Body,
placement, file/saved/modified state, history, active document, selection, and
edit mode where observable. No result contains a native object, memory address,
or negative geometry ID.

## Unified Reference-Constraint Boundary

Milestone 21 appends `add_sketch_reference_constraints` without changing the
first 34 tools or the original 17-way `add_sketch_constraints` union. Its path
is deliberately explicit:

```text
mcp/sketch_reference_constraint_tools.py
-> commands/sketch_reference_constraints.py
-> DocumentAdapter protocol
-> FreeCADDocumentAdapter
-> freecad/sketch_reference_constraints.py
-> controlled Sketcher.Constraint construction
-> recompute, semantic/native/solver/dependency verification
-> SketchReferenceConstraintAdditionResult
```

The transport owns a closed, discriminated internal/external operand union and
the application handler owns pure request validation and controlled error
envelopes. The adapter resolves current-order-local public identities to native
GeoIds, but those negative external IDs do not cross the boundary. It prepares
the entire batch against `reference_constraint_capabilities.py` before opening
a transaction. The policy is a static allowlist derived from isolated FreeCAD
1.1.1 subprocess probes; production does not trial constraints against the
user's sketch.

The adapter snapshots internal geometry, constraint fingerprints and flags,
construction, virtual state, external source mapping and ordering, dependencies,
Body/attachment/placement, solver, document/history/modified state, active
document, and observable GUI selection/edit mode. An owned success is one `Add
sketch reference constraints` transaction. A caller-owned transaction stays
open. Before opening an owned transaction, the adapter temporarily activates
the exact target document; it restores the previous active document before
context verification, return, or rollback verification. This prevents
FreeCAD's linked transaction marker from polluting a different active
document's history. Caller-owned calls never perform this switch. Addition
order is request order. Any unsupported item, stale reference,
duplicate, native mismatch, recompute failure, or unhealthy solver rejects the
whole batch. Explicit horizontal/vertical orientation constraints provide a
pre-transaction proof for redundant Parallel and Perpendicular requests. A
freshly fully constrained target also permits conservative geometric redundancy
checks for selected Coincident, Point-on-Object, Equal, and Tangent forms;
coincidental geometry with relevant freedom is not refused.

For an owned post-mutation failure, native abort runs before any compensating
mutation. Addition, recompute, solver/native/dependency verification, and context
verification all precede commit. The shared inverse path then deletes only any
still-appended constraints, restores geometry and flags, recomputes a previously
fresh solver, restores modified state, and verifies the complete snapshot. The
observed committed undo limit is 20: an open transaction may temporarily expose
21 names and abort exactly, while commit trims and irreversibly evicts the oldest
name. Defensive cleanup is therefore limited to the exact uncapped
count-plus-one leak. Same-count/changed-top history is never repaired or reported
as exact. Cleanup activates only the target and restores the prior active
document. Caller-owned failures use the inverse path without commit, abort, or
internal undo.

`get_sketch` inspects `ExternalGeo[2:]` only to type controlled operands. A
native GeoId at or below `-3` is translated to `kind: external_geometry` and a
non-negative `external_reference_number`; unsupported projections continue to
produce the established unsupported constraint summary. Internal-only summary
serialization is unchanged. Dependency inspection consumes the same native
constraint slots, so external-removal and internal-geometry-removal preflight
see exact mixed-constraint indices. Constraint removal compares external source
identity/order while intentionally permitting the removed constraint's usage
set to disappear. Milestone 20 replacement and datum editing inspect native
slots and reject mixed constraints without widening their schemas.

The detailed operand and geometry allowlists are maintained in
`docs/sketch-reference-constraint-capabilities.md`. The principal semantic
distinction is that Coincident is point-to-point, while Point-on-Object places a
point on a whole line, arc, or circle. External geometry remains read-only even
though it has equal public addressing. Name and expression mutation is a
separate boundary and does not widen reference-constraint construction.

## Constraint-Expression Boundary

Milestone 22 appends four explicit tools at positions 36–39:

```text
mcp/sketch_constraint_expression_tools.py
-> commands/sketch_constraint_expressions.py
-> constraint_expression_language.py
-> DocumentAdapter protocol
-> FreeCADDocumentAdapter
-> freecad/sketch_constraint_expressions.py
-> shared inspection/dependency/removal/editing safeguards
```

`constraint_expression_language.py` is a pure-Python lexer, parser,
canonicalizer, constant-domain validator, reference extractor, and dimensional
inference engine. It has no FreeCAD, MCP, or command imports. Its closed grammar
accepts finite numbers, `mm`/`deg`, grouping, unary signs, the four arithmetic
operators, only dimensionless `sqrt`, and named same-sketch or same-document
cross-sketch constraint references. This prevents the transport or adapter from
passing arbitrary strings to FreeCAD's much broader expression engine.

`freecad/sketch_constraint_expressions.py` is the authoritative graph and
mutation service. It inspects all sketches in the target document, maps native
numeric or named constraint target paths to current public indices, parses each
binding, resolves named sources, annotates opaque/broken state, finds exact
dependents, and detects cycles. Graph records use document/sketch/constraint
public identities only. The same service feeds list results, `get_sketch`
expression fields, dependency inspection, source rename/clear preflight,
removal preflight, and value-edit refusal. Raw opaque expressions and native
property paths never cross the public boundary.

Source datum editing also captures this same resolved graph before mutation and
computes its complete dependent closure. The editing verifier permits only
finite recomputed scalar values at those dependent nodes, while proving stable
constraint identity/order/type/name/state plus unchanged canonical bindings and
resolved dependencies. All constraint changes outside the pre-mutation closure
retain the existing `unrelated_constraint_changed` refusal and atomic rollback.

Only active, non-virtual, driving `distance`, `distance_x`, `distance_y`,
`radius`, `diameter`, and `angle` constraints with available data participate.
Names use a separate case-sensitive ASCII identifier policy and exact
same-sketch uniqueness. Cross-sketch resolution uses internal object `Name`,
not user-visible `Label`. The initial policy refuses referenced source renames
or clears, expression-bound target renames, dependent-target expression
changes, and mutations whose safety cannot be proved because another binding
is opaque or invalid.

Name and expression changes use the existing complete Milestone 19 mutation
snapshot. An owned success has one named transaction, recompute, controlled
readback, target semantic verification, unrelated expression-engine equality,
full context verification, commit, and exact history/non-target-history checks.
No-op and all preflight refusals occur before transaction opening. Owned
failures abort. Caller-owned failures inverse the native expression, restore an
unbound target's previous datum and solver-moved native geometry, recompute,
and pass the shared exact rollback verifier without closing the caller's
transaction. Clear retains the evaluated datum. No operation saves.

The observed 20-entry history limit is handled as native capacity behavior:
successful commit may evict the oldest entry, while conservative preflight
ensures a refusal cannot evict anything. Verification accepts only the exact
growth or exact capped-success shape; it does not synthesize history.

Transport schemas for all four tools are registered explicitly and then made
`extra="forbid"`. `DocumentHandlers`, application composition, runtime
composition, and server registration preserve the existing dependency
direction. The full capability contract is maintained in
`docs/sketch-constraint-expression-capabilities.md`.

## Sketch Topology-Editing Boundary

Milestone 23 appends three explicit tools at positions 40–42 without changing
the first 39:

```text
mcp/sketch_topology_editing_tools.py
-> commands/sketch_topology_editing.py
-> SketchTopologyEditingAdapter protocol
-> FreeCADDocumentAdapter
-> freecad/sketch_topology_editing.py
-> existing snapshot/dependency/history/rollback services
-> native SketchObject.trim / split / extend
-> controlled readback and complete mapping verification
-> SketchTopologyEditResult
```

The transport exposes three closed schemas rather than a generic topology
operation. Points use the existing finite strict two-coordinate model; extend
adds one exact `start | end` enum. Handler validation and safe error translation
remain FreeCAD-independent. The adapter owns all native signatures, geometric
planning, semantic verification, transaction ownership, and result mappings.

The native discovery surface is intentionally larger than production. Direct
FreeCAD 1.1.1 probes established `trim(int, Vector)`, `split(int, Vector)`, and
`extend(int, float, int)`, including constraint deletion/transfer hazards,
generated constraints, circles/arcs, construction state, histories, caller
transactions, undo/redo, and persistence. Production freezes the smaller common
domain that can prove complete mappings: unconstrained internal line segments,
with construction lines included and every other operated family refused.

### Deterministic planning

Planning uses public inspected geometry and a fixed `1e-7` sketch-coordinate
tolerance before a transaction opens. Line projection produces a normalized
source parameter and perpendicular distance. Trim uses finite-segment cross
products to enumerate and sort internal line-boundary intersections by source
parameter then boundary index. It rejects endpoint, coincident/overlapping,
equal-position, exact-pick, unsupported-boundary, external-boundary, and
near-zero outcomes. Split canonicalizes the accepted Cartesian point back onto
the source. Extend converts an explicit collinear endpoint target to the native
positive increment and PointPos 1/2 selector; it never asks FreeCAD to choose an
implicit intersection.

The planner does not match topology by approximate geometry identity after the
fact. Native probes established the exact supported survivor assignment: trim
and split retain the first source-parameter result at the original index, append
the second when present, and preserve orientation. Extend modifies the original
index in place. Those rules plus exact count/readback assertions define the
mapping; duplicate unrelated geometry cannot create mapping ambiguity.

### Constraint and mapping verification

Preflight reuses Milestone 19 native operand scanning and Milestones 21–22
dependency/expression inspection. Any pre-existing constraint referencing the
operated line refuses, with expression-bound then named then ordinary dependency
reason precedence. This prevents FreeCAD's observed silent dimensional loss,
expression detachment, and solver-driven movement of the unselected endpoint.
Broken, cross-document, and downstream topology dependencies refuse; trim also
requires zero external geometry and all internal boundaries to be line
segments.

After recompute, verification compares the complete geometry collection,
construction flags, pre-existing native constraint tuples, public constraint
readback, generated native operands/state, expressions, external mappings,
sketch context, placement, Body ownership, GUI observations, solver, and
document identity. Trim's generated Point-on-Object constraints and split's
generated Coincident constraint are asserted at exact appended indices. Native
constraint state proves their driving/active/virtual flags; public geometric
constraints legitimately serialize `driving: null` because the public
inspection model reserves that scalar for dimensional constraints.

`SketchTopologyEditResult` carries one original-order geometry mapping for every
pre-call internal item and one original-order constraint mapping for every
pre-call constraint. The supported result domain uses unchanged, modified, and
one-to-many split mappings, plus separate exact created/removed/modified entity
lists. Generated constraints are distinguished as native generation versus
split joining constraints. No native GeoId or object identity crosses the
boundary.

### Transactions, history, and recovery

The service reuses the complete Milestone 19 snapshot and exact rollback
verifier. Owned operations activate a non-active target before opening one
`Trim sketch geometry`, `Split sketch geometry`, or `Extend sketch geometry`
transaction, restore the previous active document, complete all semantic and
non-target-history checks while the transaction is open, then commit. Target
history verification accepts only exact ordinary growth or the proven
capacity-20 success shape. Refusals and endpoint/equality no-ops open no
transaction.

Caller-owned calls neither switch the active document nor open, commit, abort,
undo, or close the caller transaction. On a partial native or verification
failure, the shared same-object path restores geometry, constraints, flags,
solver, modified state, and controlled context inside that transaction, then
verifies that it remains open. Owned failures abort before commit. Every open
document's history is captured, and non-target histories are rechecked before
commit so an isolation defect remains rollback-safe. No operation calls save.

The permanent capability matrix is
`docs/sketch-topology-editing-capabilities.md`; isolated native evidence is in
`scripts/probe_sketch_topology_editing.py`, and the real-adapter campaign is
`scripts/smoke_sketch_topology_editing.py`.

## Sketch Geometry-Transform Boundary

Milestone 24 appends six explicit tools at positions 43–48 without changing the
first 42:

```text
mcp/sketch_geometry_transform_tools.py
-> commands/sketch_geometry_transforms.py
-> SketchGeometryTransformAdapter protocol
-> FreeCADDocumentAdapter
-> freecad/sketch_geometry_transforms.py
-> existing removal snapshot + dependency + topology transaction services
-> native addGeometry of controlled affine reconstructions
-> complete semantic readback and mapping verification
-> SketchGeometryTransformResult
```

The transport retains separate closed schemas for mirror, translation,
rotation, uniform scale, rectangular array, and polar array. It does not expose
a generic matrix, a mode Boolean, or a FreeCAD method selector. Pure validation
canonicalizes a non-empty unique selection, enforces finite coordinates and
angles, discriminates mirror references, and caps selections and arrays before
dispatch. Handlers own controlled error translation; only the adapter imports
FreeCAD and owns geometry construction, recompute, verification, recovery, and
result mappings.

### Evidence-bounded copy engine

FreeCAD 1.1 discovery found native `addCopy`, `addMove`, and
`addRectangularArray`, but their constraint/name semantics, mixed-family move
reversibility, and missing complete mapping output could not satisfy this
project's contract. Mirror, rotate, scale, and polar array also lack matching
SketchObject native methods. Production therefore freezes all six operations as
copy-only and reconstructs line segments, points, circles, and bounded circular
arcs through one affine engine. Originals keep exact current indices and state;
created items append in selected/instance order.

The affine model carries the 2x2 matrix, translation, radius scale, orientation
relationship, instance index, and controlled provenance. Reflections reverse a
bounded arc's endpoint order before reconstructing the native counter-clockwise
parameter interval. Positive uniform scale multiplies radii; translation and
rotation preserve them. Every expected public entity is computed before the
transaction, but native objects are constructed only inside the adapter.

Mirror planning supports the built-in horizontal and vertical axes, origin,
one unselected internal construction line, or one unselected internal point.
Arrays are source-inclusive: rectangular copies are row-major then canonical
source order; polar copies are ascending instance then source order. Duplicate
placements are detected before mutation. The fixed public limits are 50 source
items, 20 positions per rectangular axis, 100 instances, and 500 created items.

### Preservation and complete mappings

The engine deliberately copies no constraints. Native discovery showed that
blind copying can duplicate names, omit expression semantics, or substitute
`Equal` for a dimensional relationship. Preflight therefore refuses every
selected source referenced by any constraint, with expression-bound, named,
and ordinary dependency reason precedence. Unrelated constraints are preserved
as exact identity mappings. Broken/cross-document relationships and downstream
consumers refuse; existing external mappings remain read-only and exact.

After recompute, verification asserts the expected geometry count, exact
constraint count and native tuples, original geometry and construction state,
every created geometry and assigned index, solver health, expressions, external
mappings, sketch context, document identity, dependencies, GUI observations,
saved/modified state, and all target/non-target histories. The public result
contains an original-order mapping for every pre-call geometry and constraint,
ordered created/copied records, empty modified/replaced/removed and generated-
constraint collections, construction facts, instance provenance, profile
impact, solver state, and complete sketch/document readback. Current indices
remain local ordering, never persistent or native identity.

### Transactions and recovery

Owned operations reuse the Milestone 19 snapshot and Milestone 23 transaction
architecture. A non-active target is activated before its named transaction,
the previous active document is restored before final verification, and commit
occurs only after the complete result is proven. Successful history accepts
ordinary one-step growth or the native capacity-20 shape that evicts only the
oldest entry. Rectangular 1x1 returns a no-op without opening a transaction;
ambiguous overlaps and invalid operations refuse before mutation.

An owned partial failure aborts before commit and passes exact rollback
verification on the same sketch object. In a caller-owned transaction, the
adapter neither changes active-document ownership nor opens, commits, aborts,
undoes, or closes the transaction; it removes only its partial work, recomputes,
and verifies the caller's complete prior in-transaction state. No path saves.

The frozen public matrix, request rules, error taxonomy, transaction labels,
and response shape are summarized in the README and enforced by focused tests.
Isolated evidence is in `scripts/probe_sketch_geometry_transforms.py`; the
permanent production-adapter campaign is
`scripts/smoke_sketch_geometry_transforms.py`. Whole-sketch and cross-sketch
transforms remain deferred to Milestone 28.

## Test Ownership

The pure-Python suite mirrors the production responsibilities rather than
collecting all adapter or transport behavior in single modules:

- handler and validation tests remain grouped by application operation under
  `tests/test_*.py`, including `tests/test_get_sketch.py` and
  `tests/test_add_sketch_geometry.py`;
- FreeCAD adapter tests are split into document operations, object inspection,
  body creation, sketch creation, sketch attachment, and read-only sketch
  inspection modules; atomic geometry mutation and rollback belong in
  `tests/test_freecad_sketch_geometry_creation.py`; external mapping and source
  translation belong in `tests/test_freecad_sketch_external_geometry.py`, and
  dependency categories belong in `tests/test_freecad_sketch_dependencies.py`;
  Milestone 19 preflight, remapping, transaction, construction no-op, and
  rollback behavior belong in `tests/test_freecad_sketch_removal.py`; Milestone
  20 comparison, move sequencing, editing preflight, transaction, remapping, and
  rollback routing belong in `tests/test_freecad_sketch_editing.py`; reference
  operand preflight and the tested allowlist belong in
  `tests/test_sketch_reference_constraint_capabilities.py`; owned/caller-owned
  abort-versus-inverse ordering belongs in
  `tests/test_freecad_sketch_reference_constraints.py`; parser and dimensional
  semantics belong in `tests/test_constraint_expression_language.py`; graph
  resolution, exact native calls, and transaction ownership belong in
  `tests/test_freecad_sketch_constraint_expressions.py`; handler validation and
  error mapping belong in `tests/test_sketch_constraint_expression_commands.py`;
  topology planning, exact native argument translation, mapping verification,
  history isolation, and rollback routing belong in
  `tests/test_freecad_sketch_topology_editing.py`; topology handler validation
  and error translation belong in
  `tests/test_sketch_topology_editing_commands.py`;
- MCP tests are split into document, object, creation, and sketch-geometry
  registrations; tools 25--28 have exact schema and delegation coverage in
  `tests/test_mcp_sketch_external_geometry_tools.py`; tools 29–31 have strict
  schema, order, and delegation coverage in
  `tests/test_mcp_sketch_removal_tools.py`; tools 32–34 have strict schema,
  order, and delegation coverage in `tests/test_mcp_sketch_editing_tools.py`;
  tool 35 has exact schema, order, and no-chaining coverage in
  `tests/test_mcp_sketch_reference_constraint_tools.py`; tools 36–39 have strict
  schema, order, description, and delegation coverage in
  `tests/test_mcp_sketch_constraint_expression_tools.py`; tools 40–42 have
  strict schema, order, description, and typed delegation coverage in
  `tests/test_mcp_sketch_topology_editing_tools.py`;
  server composition, authoritative
  inventory, lifecycle agreement, and HTTP transport remain together;
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
