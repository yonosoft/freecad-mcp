# FreeCAD MCP

A Model Context Protocol server embedded in FreeCAD. It exposes explicit, typed CAD tools and
shared command handlers instead of arbitrary Python execution.

## Current Maturity

This repository is in active early-stage development. It provides controlled
document and object inspection plus body and sketch creation; it is not yet a
complete Part Design or Sketcher automation API, and it is not production-ready.

Current capabilities include:

- a discoverable external FreeCAD workbench named **MCP**;
- start, stop, and status toolbar/menu commands for the embedded server;
- a local Streamable HTTP server at `http://127.0.0.1:8765/mcp`;
- nineteen typed MCP tools for document creation, inspection, saving,
  recomputation, controlled Part Design body and sketch creation, read-only
  sketch inspection, atomic controlled sketch-geometry addition, and atomic
  controlled sketch-constraint addition, controlled document-history
  inspection, one-step undo and redo, plus verified semantic axis-aligned
  lower-left and centre-defined rectangles, equilateral triangles, and regular
  polygons;
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
embedded Python `3.11.14` and PySide6 / Qt `6.8.3`. The MCP SDK uses stable v1
(`>=1.27.2,<2`). Pure-Python automated checks run with standalone Python 3.11;
direct FreeCAD adapter smokes use the embedded runtime, while live MCP endpoint
acceptance remains a separate recorded check.

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
add_sketch_geometry
add_sketch_constraints
get_document_history
undo_document
redo_document
create_sketch_rectangle
create_sketch_centered_rectangle
create_sketch_equilateral_triangle
create_sketch_regular_polygon
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
`distance_x`, `distance_y`, `radius`, `diameter`, `angle`, and
`point_on_object`, `horizontal_points`, `vertical_points`, `symmetric`, and
`tangent`.
Ordinary `point_on_object` targets read back as a controlled geometry reference
with `position: edge`; point-pair alignment reads back with its two semantic
point tokens and remains distinct from whole-line orientation. Valid geometry
or constraints outside those sets are returned as controlled `unsupported`
records rather than exposing native references.

Lengths use `millimeter` and angles use `degree`. Solver facts come only from
FreeCAD's cached properties: they are populated when the sketch state is up to
date and nullable when that cache is stale. Inspection creates no transaction,
performs no save, and does not implicitly solve or recompute the sketch.
Geometry and constraint indices describe only the current sketch state; they
are not permanent identifiers and clients must inspect again after later
mutations.

### add_sketch_geometry

`add_sketch_geometry` is an atomic ordered batch mutation. Its required inputs
are `document_name`, `sketch_name`, and `geometry`; both names are exact
internal names, never visible-label aliases. `geometry` must contain between 1
and 100 items. Each item is one member of a strict discriminated union and must
include its `type` and an explicit Boolean `construction` field:

- `line_segment`: finite `start` and `end` points; exactly equal endpoints are
  rejected;
- `circle`: finite `center` and a finite positive `radius`;
- `arc_of_circle`: finite `center`, finite positive `radius`, and finite
  `start_angle_degrees` and `end_angle_degrees`;
- `point`: finite `position`.

For circular arcs, each angle is normalized modulo 360 and the end is the next
counter-clockwise parameter after the start. Equal normalized endpoints are
rejected, including full-turn and multi-turn spans; use `circle` for a full
circle. Negative angles and values greater than 360 degrees are accepted under
that normalization policy. No clockwise or sweep field is inferred.

For example:

```json
{
  "document_name": "Bracket",
  "sketch_name": "Sketch",
  "geometry": [
    {
      "type": "line_segment",
      "start": {"x": 0.0, "y": 0.0},
      "end": {"x": 40.0, "y": 0.0},
      "construction": false
    }
  ]
}
```

Point coordinate field names intentionally differ by direction. Point creation
input uses `position`:

```json
{
  "type": "point",
  "position": {
    "x": 3.0,
    "y": 4.0
  },
  "construction": false
}
```

`get_sketch` returns the same point using `point`:

```json
{
  "index": 0,
  "type": "point",
  "construction": false,
  "point": {
    "x": 3.0,
    "y": 4.0
  }
}
```

The mutation input field is named `position`; the controlled inspection output
field is named `point`. Clients must not assume input and output field names are
symmetrical.

The entire batch uses one document transaction and preserves request order.
Geometry and construction state are added together with FreeCAD's indexed
`addGeometry` API. On failure, appended tail geometry is removed in reverse,
the transaction is aborted, and the original geometry count plus all
pre-existing construction flags are verified. The tool never calls
`recompute`, `solve`, `save`, or `saveAs`.

Success has this exact shape:

```json
{
  "ok": true,
  "code": "sketch_geometry_added",
  "document_name": "Bracket",
  "sketch_name": "Sketch",
  "added_indices": [2, 3],
  "added_count": 2,
  "geometry_count": 4,
  "message": "Sketch geometry added."
}
```

The returned indices describe the immediate post-operation state only. Later
mutations can renumber them, so clients must call `get_sketch` after each
mutation for authoritative readback. Ellipses, conics, B-splines, and any other
unsupported creation discriminator are controlled request errors. Valid
unsupported geometry already present in a sketch remains inspectable through
`get_sketch`; mutation support intentionally does not exceed controlled
inspection support.

### add_sketch_constraints

`add_sketch_constraints` atomically appends an ordered batch of 1 to 100
constraints to an existing sketch. Its required top-level inputs are exactly
`document_name`, `sketch_name`, and `constraints`; lookup uses exact internal
names and never visible-label aliases. Each constraint is a strict typed union
member with no additional fields. The top-level discriminator has exactly 17
variants. Version one supports:

- `horizontal` and `vertical` on line segments;
- `parallel` and `perpendicular` between distinct line segments;
- `equal` between distinct line segments, or between any distinct pair of
  circles and circular arcs;
- `coincident` between distinct geometry-point references, or between one
  geometry point and the native sketch origin;
- `point_on_object` from one selected geometry point to a line segment, circle,
  circular arc, or the native horizontal or vertical sketch axis;
- `horizontal_points` between two distinct selected points that must share a Y
  coordinate;
- `vertical_points` between two distinct selected points that must share an X
  coordinate;
- `symmetric` between two distinct geometry points, about the sketch origin,
  either native sketch axis, another distinct geometry point, or a line segment;
- `tangent` between two distinct whole geometries for line-circle, line-arc,
  circle-circle, circle-arc, and arc-arc pairs, in either heterogeneous order;
- `distance` modes `line_length`, `point_to_origin`, and `between_points`;
- `distance_x` and `distance_y` modes `point_to_origin` and `between_points`;
- `radius` and `diameter` on circles or circular arcs;
- `angle` modes `line_angle` and `between_lines` on line segments.

For example:

```json
{
  "document_name": "Bracket",
  "sketch_name": "Sketch",
  "constraints": [
    {
      "type": "horizontal",
      "geometry_index": 0
    },
    {
      "type": "distance",
      "mode": "between_points",
      "first": {"geometry_index": 0, "position": "end"},
      "second": {"geometry_index": 1, "position": "start"},
      "value": 15.0
    }
  ]
}
```

Point references use semantic tokens rather than FreeCAD integers:
`start → 1`, `end → 2`, `center → 3`, and `point → 1` for `Part.Point`
geometry. Lines allow `start`/`end`, arcs allow `start`/`end`/`center`, circles
allow `center`, and point geometry allows `point`. Native sketch references
are strict one-field objects:

```json
{"reference": "origin"}
{"reference": "horizontal_axis"}
{"reference": "vertical_axis"}
```

`origin` is accepted by `coincident` and as `symmetric.about`.
`horizontal_axis` and `vertical_axis` are accepted by `point_on_object` and as
`symmetric.about`; either public order remains accepted for the two-sided
axis-target `point_on_object` contract for backward compatibility. For ordinary
targets, `first` is the selected point and `second` is the strict whole-geometry
reference `{"geometry_index": n}`. Its target may resolve only to a current
line segment, circle, or circular arc; line construction state does not change
compatibility. Point geometry, origin, external/datum geometry, ellipses,
B-splines, self-targets, and references carrying a point position are rejected.
Negative geometry indices, internal geometry, native point-position integers,
and other reference literals are also rejected. The existing `point_to_origin`
distance modes remain unchanged and do not expose FreeCAD's internal root-point
encoding.

Point-pair alignment uses the existing point-reference vocabulary:

```json
{"type": "horizontal_points", "first": {"geometry_index": 0, "position": "center"}, "second": {"geometry_index": 1, "position": "point"}}
{"type": "vertical_points", "first": {"geometry_index": 0, "position": "start"}, "second": {"geometry_index": 1, "position": "center"}}
```

These forms accept mixed supported point kinds. Distinct endpoints of the same
line are valid, although whole-line `horizontal` or `vertical` is preferred
when the intent is simply to orient that line.

The strict symmetric shape reuses the same point-reference model for `first`,
`second`, and point-centred `about`. A whole line is a strict one-field geometry
reference and is verified to be a current line segment before mutation:

```json
{
  "type": "symmetric",
  "first": {"geometry_index": 0, "position": "start"},
  "second": {"geometry_index": 2, "position": "start"},
  "about": {"reference": "origin"}
}
```

Supported `about` values are exactly the three native reference objects, a
controlled geometry-point reference, or `{"geometry_index": 3}` for a line
segment. Circles, arcs, external/datum geometry, raw native identifiers,
identical selected points, a selected point reused as the centre, and a
selected point taken from its own symmetry line are rejected before mutation.

Direct tangency uses exactly two strict whole-geometry references:

```json
{
  "type": "tangent",
  "first": {"geometry_index": 1},
  "second": {"geometry_index": 0}
}
```

Each accepted item creates exactly one native
`Sketcher.Constraint("Tangent", first_index, second_index)` in request order.
The supported matrix is line segment-circle, line segment-circular arc,
circle-circle, circle-circular arc, and circular arc-circular arc. Reversing a
heterogeneous pair is supported and retained in controlled readback.
Construction state does not change compatibility. Same-geometry references,
line-line, point geometry, unsupported curves, out-of-range indices, selected
point references, sketch axes, origin references, and any branch or contact
field are rejected before a transaction.

FreeCAD chooses external versus internal circle tangency, and the side of a
line, from the geometry's current placement. Place geometry near the intended
solution before adding the constraint, then explicitly recompute and inspect
actual coordinates and solver diagnostics. For an arc, native direct tangency
constrains its underlying support circle; the mathematical contact can lie
outside the visible bounded arc. Verify that the visible arc contains the
intended contact rather than assuming it does.

For example, a circle can be centered natively on the sketch origin without an
artificial anchor point:

```json
{
  "document_name": "BearingSketch",
  "sketch_name": "Sketch",
  "constraints": [
    {
      "type": "coincident",
      "first": {
        "geometry_index": 0,
        "position": "center"
      },
      "second": {
        "reference": "origin"
      }
    },
    {
      "type": "radius",
      "geometry_index": 0,
      "value": 10.0
    }
  ]
}
```

This creates one native `Coincident` constraint for the origin reference. It
does not create construction geometry or zero-valued X/Y distance constraints.
Axis membership creates native `PointOnObject`, not `Coincident`, even though
FreeCAD's GUI exposes both through its unified coincidence command. Native
negative reference IDs remain private to the FreeCAD layer. These operations
are not a composite `lock` constraint.

Use `point_on_object` for point-to-line/circle/arc/axis membership and
`coincident` for point-to-point coincidence. Use whole-line `horizontal` or
`vertical` for one line and `horizontal_points` or `vertical_points` for two
independently selected points. Prefer native sketch axes over helper
construction lines for sketch datums; reuse an existing construction line when
it is intentional design geometry, but do not create one when a native axis
expresses the same intent. Use symmetry when the design intent is symmetric and
the smallest natural constraint set. Avoid duplicate, redundant, and
substitute constraints. After explicit recompute, require no redundant,
partially redundant, conflicting, or malformed constraints. The tool exposes
these controlled choices but does not choose a strategy for the calling agent.

Use `tangent` only for the supported whole-edge relationship. It does not join
selected endpoints and is not a substitute for `coincident`,
`point_on_object`, `parallel`, `perpendicular`, or collinearity. If a
successful call chooses the wrong branch, inspect document history, undo the
known `Add sketch constraints` transaction, correct the initial placement or
strategy in the same sketch, reapply tangency, recompute, and inspect again.
Do not undo after a failed atomic call that already restored zero mutation, and
do not abandon a recoverable sketch merely to obtain another branch.

A complete axis-aligned rectangle should use a semantic rectangle tool, not a
sequence of primitive geometry and constraint calls. Use
`create_sketch_rectangle` for lower-left-defined intent and
`create_sketch_centered_rectangle` for centre-defined intent. Do not calculate
a lower-left corner for a centre-defined request when tool 17 is available.
Use `add_sketch_geometry` only for custom, incomplete, or non-rectangular line
arrangements and `add_sketch_constraints` to modify existing relationships.

A second direct regression uses one origin-centred 10 mm circle and two point
geometries near `(10, 0)` and `(0, 10)`. Each point uses ordinary
`point_on_object` to the circle; the first uses `horizontal_points` to the
circle centre and the second uses `vertical_points`. With origin coincidence
and one radius constraint, FreeCAD 1.1.1 reports zero degrees of freedom, full
constraint, and empty conflict, redundant, partially-redundant, and malformed
diagnostics. The sketch contains no helper geometry, remains unsaved, reads
back only controlled references, and the six-constraint batch is one undo/redo
step.

A direct upper-tangent regression uses one origin-centred circle of radius
10 mm and one 30 mm line initially above it. The smallest natural set is five
constraints: centre-to-origin coincidence, circle radius, line length, line
endpoint symmetry about the vertical sketch axis, and direct line-circle
tangency. Endpoint symmetry already forces the line horizontal, so adding a
separate horizontal constraint is redundant. FreeCAD 1.1.1 reports the line at
`y = +10 mm`, zero DoF, full constraint, and empty conflict, redundant,
partially-redundant, and malformed diagnostics. The sketch has exactly two
geometry elements, no helper or coordinate-offset dimension, controlled
tangent readback, and remains unsaved.

Length values are millimetres. Euclidean `distance`, `radius`, and `diameter`
values must be finite and positive. `distance_x` and `distance_y` preserve
finite signed values, including zero. Angle inputs are finite degrees and are
converted directly to radians without normalization; zero, ±180°, ±360°, and
values beyond a full turn are preserved. Line direction therefore affects the
meaning of both one-line and two-line angles.

The batch uses one owned document transaction when no caller transaction is
already pending. Constraints are added in request order and every assigned
index and incremental/final count is verified. On failure, appended constraints
are removed in reverse, the owned transaction is aborted, pre-existing
constraint type/reference/value and driving/active/virtual flags are verified,
and geometry plus construction state are restored if FreeCAD's internal solver
moved them. A successful owned transaction is expected to be one undo step
when FreeCAD undo is enabled; a caller-owned transaction retains its caller's
grouping.

The tool never calls `solve`, `recompute`, `save`, or `saveAs`. FreeCAD 1.1.1's
`addConstraint` binding does internally set up and solve the sketch and may move
geometry immediately; the document is still left touched and cached solver
facts are treated as stale until an explicit `recompute_document`. Clients must
call `get_sketch` after mutation.

Success has this exact shape:

```json
{
  "ok": true,
  "code": "sketch_constraints_added",
  "document_name": "Bracket",
  "sketch_name": "Sketch",
  "added_indices": [0, 1],
  "added_count": 2,
  "constraint_count": 2,
  "message": "Sketch constraints added."
}
```

Indices are temporary current-state indices. Only driving dimensional
constraints are created. Point-specific tangency, line-line tangency, block,
internal alignment, angle-via-point, B-spline-specific and arbitrary reference
constraints;
constraint names, expressions, editing, and deletion; external/internal
geometry references; and arbitrary `Sketcher.Constraint` passthrough remain
unsupported. Controlled axes are accepted only by `point_on_object` and as the
`about` reference of `symmetric`. Supported native symmetry reads back as three
controlled references in `first`, `second`, `about` order; private negative IDs
and native point-position integers are never returned. Ordinary
`PointOnObject` and point-pair `Horizontal`/`Vertical` read back as
`point_on_object`, `horizontal_points`, and `vertical_points` without exposing
their native constructor fields. Supported native direct `Tangent` records
read back as `tangent` with exactly two non-negative geometry edge references
in stored order; point-specific, line-line, degenerate, or malformed tangent
records remain controlled `unsupported` entries. Existing unsupported
constraints remain inspectable through `get_sketch`; redundancy and conflicts
are assessed only after explicit recompute.

These document, object, and sketch-inspection tools are MCP-only capabilities.
They do not add workbench commands or toolbar icons. `get_object` performs exact
internal-name lookup only; labels are not used as lookup keys. If placement is
unavailable the ``placement`` field returns ``null`` rather than failing the
entire tool.

### Semantic axis-aligned rectangles

`create_sketch_rectangle` is exactly tool 16. It targets an existing sketch
and accepts this strict request; every object forbids additional properties:

```json
{
  "document_name": "Model",
  "sketch_name": "BaseSketch",
  "width": 30.0,
  "height": 20.0,
  "placement": {"type": "lower_left", "x": -15.0, "y": -10.0}
}
```

Width and height are finite strict numbers greater than zero. Coordinates are
finite strict numbers, and booleans are never numbers. `lower_left` is the only
placement variant. Centred, rotated, rounded, construction, and partially
constrained rectangles remain outside this contract.

The adapter appends four normal lines in explicit counter-clockwise semantic
order: `bottom` (lower-left to lower-right), `right` (lower-right to
upper-right), `top` (upper-right to upper-left), then `left` (upper-left to
lower-left). Its returned corners are explicitly ordered `lower_left`,
`lower_right`, `upper_right`, `upper_left`, with each mapped to a controlled
line endpoint. Indices are current sketch-local indices, including when the
sketch was already non-empty; they are not persistent profile IDs.

The deterministic constraint sequence is four endpoint coincidences, four
horizontal/vertical orientations, bottom and right whole-line dimensions, and
natural lower-left placement. Placement at `(0, 0)` uses origin coincidence;
`x = 0` uses the vertical axis plus Y distance; `y = 0` uses the horizontal
axis plus X distance; otherwise it uses X and Y distances. It creates no
helper or construction geometry and does not rely on automatic constraints.
The existing `add_sketch_geometry` and `add_sketch_constraints` tools remain
appropriate for incomplete/custom arrangements and relationships on existing
geometry. Their schemas, including all 17 constraint variants, are unchanged.

Success returns the normal command envelope with code
`sketch_rectangle_created`, a `profile` containing geometry and constraint
indices, explicit edge/corner mappings, requested dimensions and placement,
and verified `closed`, `axis_aligned`, and `fully_constrained` flags. It also
returns the existing complete controlled `sketch` inspection and `document`
summary. The result describes ordinary sketch geometry and constraints, not a
persistent FreeCAD profile object.

```json
{
  "ok": true,
  "code": "sketch_rectangle_created",
  "profile": {
    "type": "rectangle",
    "geometry_indices": [4, 5, 6, 7],
    "constraint_indices": [10, 11, 12],
    "edges": {"bottom": 4, "right": 5, "top": 6, "left": 7},
    "corners": {
      "lower_left": {"geometry_index": 4, "position": "start"},
      "lower_right": {"geometry_index": 4, "position": "end"},
      "upper_right": {"geometry_index": 5, "position": "end"},
      "upper_left": {"geometry_index": 6, "position": "end"}
    },
    "width": 30.0,
    "height": 20.0,
    "placement": {"type": "lower_left", "x": -15.0, "y": -10.0},
    "closed": true,
    "axis_aligned": true,
    "fully_constrained": true
  },
  "sketch": {"...": "existing controlled sketch inspection"},
  "document": {"...": "existing controlled document summary"},
  "message": "Created and verified an axis-aligned sketch rectangle."
}
```

All lines and constraints are created through core Sketcher APIs inside one
`Create sketch rectangle` transaction. After recompute, the adapter verifies
the exact append ranges, geometry/order/endpoints, closure relationships,
dimensions, placement, zero degrees of freedom, clean solver diagnostics, and
unchanged Body ownership, attachment, MapMode, placement, and document state.
It commits only after verification. Any geometry, constraint, recompute, or
semantic-verification failure removes the appended tail, aborts its owned
transaction, restores solver-moved geometry and construction/constraint state,
and verifies the complete pre-call snapshot. A structured failed call therefore
needs no undo and creates no history entry.

One successful call is one history step. Matching one-step undo removes the
whole rectangle while preserving the sketch and its earlier content; redo
restores it. Recompute and inspect after either movement. If a valid rectangle
has the wrong design placement, inspect history, undo the exact `Create sketch
rectangle` step, and create the corrected profile in the same sketch; do not
create a replacement sketch. A new mutation invalidates the prior redo entry.
Standalone, Body-owned, and supported attached sketches are preserved. Unsaved
documents remain without a path, and saved files are not written until an
explicit `save_document` call. The implementation calls neither another MCP
tool nor a GUI Rectangle command.

### Semantic centred rectangles

`create_sketch_centered_rectangle` is exactly tool 17 and is distinct from the
lower-left-only tool 16. It targets an existing sketch and accepts this strict
request; every object forbids additional properties:

```json
{
  "document_name": "Model",
  "sketch_name": "BaseSketch",
  "width": 30.0,
  "height": 20.0,
  "center": {"x": 12.0, "y": -7.0}
}
```

`center` contains exactly finite strict numeric `x` and `y` values. Width and
height are finite strict numbers greater than zero; booleans are rejected as
numbers. The tool does not accept `placement`, `lower_left`, rotation,
construction-edge, partial-constraint, native-index, or branch controls. Tool
16 remains exactly lower-left-only, and the established 17 constraint
variants are unchanged.

The adapter derives all four corners and appends exactly four normal lines in
`bottom`, `right`, `top`, `left` order, followed by one construction
`Part.Point` at the requested centre. The first four indices are profile
geometry; the fifth is returned separately in `reference_geometry_indices`.
The point is deliberate semantic profile metadata and the symmetry centre, not
an incidental hidden helper. No diagonal, centre line, circle, duplicate
corner, or other helper geometry is created.

The deterministic constraint sequence is four endpoint coincidences, four
edge orientations, bottom width, right height, and one direct symmetry between
the lower-left and upper-right corners about the construction point. Centre
placement uses one origin coincidence at `(0,0)`; vertical-axis membership plus
Y distance when only `x` is zero; horizontal-axis membership plus X distance
when only `y` is zero; otherwise signed X and Y distances. FreeCAD 1.1.1
verifies 12 constraints at the origin and 13 for every other branch, zero DoF,
full constraint, and clean solver diagnostics.

Success has the existing envelope and controlled readback shape:

```json
{
  "ok": true,
  "code": "sketch_centered_rectangle_created",
  "message": "Created and verified an axis-aligned centred sketch rectangle.",
  "profile": {
    "type": "centered_rectangle",
    "geometry_indices": [4, 5, 6, 7],
    "reference_geometry_indices": [8],
    "constraint_indices": [10, 11, 12],
    "edges": {"bottom": 4, "right": 5, "top": 6, "left": 7},
    "corners": {
      "lower_left": {"geometry_index": 4, "position": "start"},
      "lower_right": {"geometry_index": 4, "position": "end"},
      "upper_right": {"geometry_index": 5, "position": "end"},
      "upper_left": {"geometry_index": 6, "position": "end"}
    },
    "center": {
      "x": 12.0,
      "y": -7.0,
      "reference": {"geometry_index": 8, "position": "point"}
    },
    "width": 30.0,
    "height": 20.0,
    "closed": true,
    "axis_aligned": true,
    "centered": true,
    "fully_constrained": true
  },
  "sketch": {"...": "existing controlled sketch inspection"},
  "document": {"...": "existing controlled document summary"}
}
```

Creation, recompute, semantic verification, and commit are one atomic
`Create centered sketch rectangle` transaction. Verification covers exact
append ranges and types, construction state, edge/corner coordinates, centre
and diagonal midpoint, symmetry and placement readback, constraint count,
solver diagnostics, and unchanged Body ownership, attachment, MapMode,
placement, document path, and pre-existing content. On failure the appended
constraints, centre point, and four edges are removed; the complete snapshot
and caller-owned transaction state are restored; no history entry remains.

One matching undo removes all four edges, the centre reference, and every new
constraint; one redo restores their order, construction state, mappings, and
fully constrained solver state. A new mutation after undo invalidates redo. A
valid rectangle at the wrong centre should be inspected, matched to `Create
centered sketch rectangle`, undone, and recreated in the same sketch. Saved
files are not written by create/undo/redo, unsaved documents stay pathless, and
Body-owned or supported attached sketches retain their identity and support.
The operation calls neither another MCP tool nor a GUI command. Rotated,
rounded, three-point, construction-edge, and partially constrained rectangles
remain future work.

### Semantic polygon profiles

`create_sketch_equilateral_triangle` and `create_sketch_regular_polygon` are
tools 18 and 19. Both target an existing sketch and use one shared internal
regular-polygon engine; neither invokes another MCP tool or a Sketcher GUI
command. Explicit equilateral-triangle intent selects tool 18. Generic regular
polygon intent, including a regular polygon with three sides, selects tool 19.
Irregular triangles use primitive geometry, while rectangle intent remains with
tools 16 and 17.

The triangle request requires `document_name`, `sketch_name`, positive finite
`circumradius`, and strict `center: {x, y}` values. Its optional
`first_vertex_angle_degrees` defaults to `90.0`. The polygon request adds a
strict integer `side_count` from 3 through 64 and defaults the angle to `0.0`.
All objects reject extra fields, booleans are not numbers, and NaN and infinity
are rejected. Circumradius always means the distance from the centre to every
vertex; it is not an apothem or side length.

Vertex zero lies at the public angle measured from positive sketch X. Positive
angles are counter-clockwise; negative and multi-turn inputs are accepted and
reported modulo 360 in `[0, 360)`. Vertex `i` is
`(cx + r*cos(a+i*360/n), cy + r*sin(a+i*360/n))`. Normal edge `i` runs from
vertex `i` to vertex `(i+1) mod n`, so the returned edge and vertex mappings are
deterministic and counter-clockwise even in a non-empty sketch.

After the N normal edges the adapter appends an explicit construction centre
point and an explicit construction circumcircle. Runtime probes of FreeCAD
1.1.1 established the circle as the stable natural way to express one shared
circumradius dimension while keeping every vertex on that radius; both
reference indices and the circle's meaning are returned, and no helper is
hidden. The deterministic constraints are N closure coincidences, N−1 edge
equalities, N endpoint-on-circumcircle constraints, centre-point-to-circle-centre
coincidence, natural centre placement, one circle radius, and one first-edge
angle. Counts are `3N+3` at the origin and `3N+4` elsewhere.

Success codes are `sketch_equilateral_triangle_created` and
`sketch_regular_polygon_created`. The profile returns normal and reference
indices separately, ordered edge and vertex records, controlled centre and
circumcircle references, requested circumradius, normalized angle, and verified
closed, regular, counter-clockwise, and fully constrained facts. The complete
sketch readback must show zero DoF and no conflicting, redundant, partially
redundant, or malformed constraints before commit.

Owned calls create exactly one `Create sketch equilateral triangle` or `Create
sketch regular polygon` history step. A caller-owned transaction is neither
nested nor committed. Any append, recompute, readback, solver, or semantic
failure restores the complete pre-call sketch and history state; no undo is
needed after such a failed call. Matching undo/redo removes/restores the entire
profile including construction references. A technically valid but wrong
profile should be undone by its exact name and recreated in the same sketch;
the new mutation invalidates the old redo branch. Body ownership, attachment,
MapMode, placement, pre-existing content, and saved/unsaved file state are
preserved. Creation never saves automatically.

Known limits are deliberate: no polygon by side length or apothem, star or
self-intersecting polygon, construction-edge polygon, partial constraint,
profile editing/deletion, persistent profile identity, automatic sketch/Body
creation, or automatic saving is exposed.

### Controlled document history

`get_document_history`, `undo_document`, and `redo_document` are tools 13–15.
They operate on the exact internal `document_name` supplied; they never use the
active document as a substitute and have no GUI command, toolbar item, or menu
entry. Each history mutation moves exactly one current top transaction.

History inspection returns the controlled document summary plus:

```json
{
  "undo_count": 3,
  "redo_count": 1,
  "can_undo": true,
  "can_redo": true,
  "next_undo_name": "Add sketch constraints",
  "next_redo_name": "Add sketch geometry",
  "transaction_active": false,
  "history_available": true
}
```

It does not return complete native stacks, native transaction objects, or
transaction IDs. Transaction names are current-step safety labels, not durable
history identifiers. The controlled transaction names produced by current MCP
model mutations are `Create body`, `Create sketch`, `Add sketch geometry`,
`Add sketch constraints`, `Create sketch rectangle`, and `Create centered
sketch rectangle`, `Create sketch equilateral triangle`, and `Create sketch
regular polygon`.

Undo has this strict input shape; redo uses the same shape:

```json
{
  "document_name": "Model",
  "expected_transaction_name": "Add sketch constraints"
}
```

`expected_transaction_name` is optional, but clients should supply it whenever
the known top label is available. Matching is exact and case-sensitive. A
mismatch, unavailable stack, disabled history, active transaction, re-entrant
undo/redo/rollback, or inconsistent native transition returns a structured
failure without intentionally taking a second history step. There is no
`steps`, `count`, history index, undo-to, redo-to, clear-history, or generic
history-mutation option.

Undo and rollback serve different purposes. A failed atomic MCP mutation should
already have rolled back to zero net mutation; do not call `undo_document`
after that failure because it could remove the preceding valid step. Use undo
when an operation succeeded technically but expressed the wrong design intent.
The normal recovery loop is:

```text
recompute and inspect the successful result
→ inspect document history
→ verify the expected top transaction
→ undo exactly that transaction
→ inspect the restored document or sketch
→ revise the strategy
→ retry in the same sketch or model
```

Prefer correcting the current sketch through controlled undo over abandoning
it, duplicating geometry, or creating a replacement sketch or document for a
recoverable mistake. If the top transaction belongs to an unexpected GUI or
user action, reinspect and ask for direction instead of undoing it. Redo only
when intentionally restoring the most recently undone transaction; any new
model mutation normally invalidates the redo entry.

History mutation is in-memory only. It does not save, reverse a prior save,
restore overwritten files, or change external filesystem state. Saved-file
bytes and timestamps remain untouched until `save_document` is called, and an
unsaved document remains without a file path. In the verified FreeCAD 1.1.1 GUI
runtime, a clean document becomes modified after a committed mutation and stays
modified after both undo and redo; history movement does not infer that the
current in-memory state equals a prior saved state. Undo and redo also do not
recompute. Sketch solver data therefore reports stale after either operation
until an explicit `recompute_document`, followed by fresh inspection.

## Documentation

- [Architecture](docs/architecture.md)
- [Development setup and CI](docs/development.md)

## License

LGPL-2.1-or-later. See [LICENSE](LICENSE).
