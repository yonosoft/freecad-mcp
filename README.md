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
- twelve typed MCP tools for document creation, inspection, saving,
  recomputation, controlled Part Design body and sketch creation, read-only
  sketch inspection, atomic controlled sketch-geometry addition, and atomic
  controlled sketch-constraint addition;
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
add_sketch_geometry
add_sketch_constraints
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
`point_on_object`, and `symmetric`. Valid geometry or constraints outside those sets are
returned as controlled `unsupported` records rather than failing the entire
sketch.

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
member with no additional fields. Version one supports:

- `horizontal` and `vertical` on line segments;
- `parallel` and `perpendicular` between distinct line segments;
- `equal` between distinct line segments, or between any distinct pair of
  circles and circular arcs;
- `coincident` between distinct geometry-point references, or between one
  geometry point and the native sketch origin;
- `point_on_object` between one geometry point and the native horizontal or
  vertical sketch axis;
- `symmetric` between two distinct geometry points, about the sketch origin,
  either native sketch axis, another distinct geometry point, or a line segment;
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
`coincident` and `point_on_object` contracts. Negative geometry indices,
external geometry, internal geometry, and other reference literals are
rejected. The existing `point_to_origin` distance modes remain unchanged and
do not expose FreeCAD's internal root-point encoding.

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

Use symmetry when the design intent is symmetric. Prefer the sketch origin or
native sketch axes over calculated positive and negative placement dimensions,
and use the smallest natural constraint set. Do not add helper construction
geometry or duplicate symmetry with coordinate, distance, or coincidence
constraints that make the sketch redundant. After explicit recompute, require
no redundant, partially redundant, conflicting, or malformed constraints. The
tool exposes controlled symmetry but does not choose a constraint strategy for
the calling agent.

A centred 30 mm × 20 mm rectangle is representable with four line segments,
four endpoint coincidences, two horizontal constraints, two vertical
constraints, 30 mm and 20 mm whole-line dimensions, and one symmetry constraint
between opposite corners about the origin. Direct FreeCAD 1.1.1 regression
testing confirms that natural 11-constraint set is closed, fully constrained at
zero degrees of freedom, and has no redundant, partially redundant,
conflicting, or malformed constraints. It uses no helper geometry and no signed
corner-coordinate dimensions.

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
constraints are created. Tangent, block, internal alignment,
angle-via-point, B-spline-specific and arbitrary reference constraints;
constraint names, expressions, editing, and deletion; external/internal
geometry references; and arbitrary `Sketcher.Constraint` passthrough remain
unsupported. Controlled axes are accepted only by `point_on_object` and as the
`about` reference of `symmetric`. Supported native symmetry reads back as three
controlled references in `first`, `second`, `about` order; private negative IDs
and native point-position integers are never returned. Existing unsupported
constraints remain inspectable through `get_sketch`; redundancy and conflicts
are assessed only after explicit recompute.

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
