"""Pure deterministic sketch topology and profile analysis.

This module deliberately imports no FreeCAD runtime modules.  It consumes the
controlled records produced by :mod:`freecad_mcp.freecad.sketch_inspection` and
is shared by all three public Milestone 17 analysis operations.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from itertools import combinations, pairwise
from typing import Literal

from freecad_mcp.exceptions import InvalidGeometrySelectionError
from freecad_mcp.models import (
    DocumentSummary,
    SketchAnalysisRequestInput,
    SketchAnalysisResult,
    SketchArcGeometry,
    SketchCircleGeometry,
    SketchGeometry,
    SketchInspectionResult,
    SketchLineGeometry,
    SketchOpenVerticesResult,
    SketchPoint2D,
    SketchPointGeometry,
    SketchProfileAnalysisRequestInput,
    SketchProfileValidationResult,
    UnsupportedSketchGeometry,
)

TOPOLOGY_TOLERANCE = 1.0e-7
"""Fixed millimetre tolerance used for endpoint clustering and exact tests."""

NEAR_TOLERANCE = 1.0e-5
"""Conservative warning-only tolerance for near openings and duplicates."""

_POSITION_ORDER = {"start": 0, "end": 1}
_SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}


@dataclass(frozen=True, slots=True)
class _Endpoint:
    geometry_index: int
    position: Literal["start", "end"]
    point: SketchPoint2D


@dataclass(frozen=True, slots=True)
class _Edge:
    index: int
    kind: Literal["line", "arc", "circle"]
    start: SketchPoint2D | None = None
    end: SketchPoint2D | None = None
    center: SketchPoint2D | None = None
    radius: float | None = None
    start_angle: float | None = None
    end_angle: float | None = None
    external: bool = False


@dataclass(slots=True)
class _Vertex:
    number: int
    x: float
    y: float
    members: tuple[_Endpoint, ...]
    degree: int
    component_number: int = -1


@dataclass(frozen=True, slots=True)
class _Component:
    number: int
    geometry_indices: tuple[int, ...]
    vertex_numbers: tuple[int, ...]
    edge_count: int
    open_vertex_count: int
    branch_vertex_count: int
    classification: str
    closed_loop_candidate: bool
    profile_candidate: bool


@dataclass(frozen=True, slots=True)
class _Profile:
    number: int
    component_number: int
    geometry_indices: tuple[int, ...]
    signed_area: float | None
    orientation: str
    witness: SketchPoint2D
    contains: tuple[int, ...] = ()
    contained_by: int | None = None


@dataclass(slots=True)
class _CoreAnalysis:
    sketch: SketchInspectionResult
    document: DocumentSummary
    edges: tuple[_Edge, ...]
    edge_vertices: dict[int, tuple[int, int] | None]
    vertices: tuple[_Vertex, ...]
    components: tuple[_Component, ...]
    profiles: tuple[_Profile, ...]
    topology_findings: tuple[dict[str, object], ...]
    analysis_findings: tuple[dict[str, object], ...]
    participating_count: int
    construction_count: int
    external_count: int
    selected_indices: tuple[int, ...] | None


class _DisjointSet:
    def __init__(self, values: tuple[int, ...]) -> None:
        self.parent = {value: value for value in values}

    def find(self, value: int) -> int:
        parent = self.parent[value]
        if parent != value:
            self.parent[value] = self.find(parent)
        return self.parent[value]

    def union(self, first: int, second: int) -> None:
        first_root = self.find(first)
        second_root = self.find(second)
        if first_root == second_root:
            return
        if first_root < second_root:
            self.parent[second_root] = first_root
        else:
            self.parent[first_root] = second_root


def analyze_sketch(
    sketch: SketchInspectionResult,
    document: DocumentSummary,
    request: SketchAnalysisRequestInput,
    external_geometry: tuple[SketchGeometry, ...] = (),
) -> SketchAnalysisResult:
    """Build the broad health projection from the shared topology engine."""
    core = _build_core(
        sketch,
        document,
        geometry_indices=None,
        include_construction=request.include_construction,
        include_external=request.include_external,
        external_geometry=external_geometry,
    )
    closed_count = sum(component.closed_loop_candidate for component in core.components)
    open_count = sum(component.open_vertex_count > 0 for component in core.components)
    branched_count = sum(component.branch_vertex_count > 0 for component in core.components)
    solver = sketch.solver
    analysis: dict[str, object] = {
        "geometry_count": sketch.geometry_count,
        "participating_geometry_count": core.participating_count,
        "construction_geometry_count": core.construction_count,
        "external_geometry_count": core.external_count,
        "constraint_count": sketch.constraint_count,
        "degrees_of_freedom": solver.degrees_of_freedom,
        "fully_constrained": solver.fully_constrained,
        "solver": {
            "available": solver.available,
            "fresh": solver.fresh,
            "conflicting": _indices(solver.conflicting_constraint_indices),
            "redundant": _indices(solver.redundant_constraint_indices),
            "partially_redundant": _indices(solver.partially_redundant_constraint_indices),
            "malformed": _indices(solver.malformed_constraint_indices),
        },
        "topology": {
            "component_count": len(core.components),
            "closed_component_count": closed_count,
            "open_component_count": open_count,
            "branched_component_count": branched_count,
            "probable_profile_count": len(core.profiles),
            "topology_vertex_count": len(core.vertices),
            "open_vertex_count": sum(vertex.degree == 1 for vertex in core.vertices),
        },
        "components": [_component_dict(item) for item in core.components],
        "findings": list(core.analysis_findings),
        "tolerance": TOPOLOGY_TOLERANCE,
    }
    return SketchAnalysisResult(
        analysis=analysis,
        sketch=_sketch_summary(sketch),
        document=document,
    )


def validate_sketch_profile(
    sketch: SketchInspectionResult,
    document: DocumentSummary,
    request: SketchProfileAnalysisRequestInput,
    external_geometry: tuple[SketchGeometry, ...] = (),
) -> SketchProfileValidationResult:
    """Return the profile-validity projection from the shared topology engine."""
    core = _build_core(
        sketch,
        document,
        geometry_indices=request.geometry_indices,
        include_construction=request.include_construction,
        include_external=request.include_external,
        external_geometry=external_geometry,
    )
    classification, valid = _profile_classification(core)
    validation: dict[str, object] = {
        "valid": valid,
        "classification": classification,
        "profile_count": len(core.profiles),
        "component_count": len(core.components),
        "profiles": [_profile_dict(item) for item in core.profiles],
        "open_vertices": [_open_vertex_dict(item) for item in core.vertices if item.degree == 1],
        "findings": list(core.topology_findings),
        "tolerance": TOPOLOGY_TOLERANCE,
    }
    return SketchProfileValidationResult(
        validation=validation,
        sketch=_sketch_summary(sketch),
        document=document,
    )


def list_sketch_open_vertices(
    sketch: SketchInspectionResult,
    document: DocumentSummary,
    request: SketchProfileAnalysisRequestInput,
    external_geometry: tuple[SketchGeometry, ...] = (),
) -> SketchOpenVerticesResult:
    """Return only degree-one vertices from the shared topology engine."""
    core = _build_core(
        sketch,
        document,
        geometry_indices=request.geometry_indices,
        include_construction=request.include_construction,
        include_external=request.include_external,
        external_geometry=external_geometry,
    )
    open_vertices = tuple(_open_vertex_dict(item) for item in core.vertices if item.degree == 1)
    open_codes = {
        "open_vertices_found",
        "branched_topology",
        "construction_geometry_excluded",
        "external_geometry_excluded",
        "unsupported_geometry",
        "suspected_near_open_gap",
    }
    findings = tuple(item for item in core.topology_findings if str(item["code"]) in open_codes)
    return SketchOpenVerticesResult(
        open_vertices=open_vertices,
        findings=findings,
        sketch=_sketch_summary(sketch),
        document=document,
    )


def _build_core(
    sketch: SketchInspectionResult,
    document: DocumentSummary,
    *,
    geometry_indices: tuple[int, ...] | None,
    include_construction: bool,
    include_external: bool,
    external_geometry: tuple[SketchGeometry, ...],
) -> _CoreAnalysis:
    findings: list[dict[str, object]] = []
    internal_by_index = {item.index: item for item in sketch.geometry}
    if geometry_indices is not None:
        missing = tuple(index for index in geometry_indices if index not in internal_by_index)
        if missing:
            raise InvalidGeometrySelectionError(missing_indices=missing)
        selected = set(geometry_indices)
    else:
        selected = None

    construction_count = sum(item.construction for item in sketch.geometry)
    if construction_count and not include_construction:
        findings.append(
            _finding(
                "info",
                "construction_geometry_excluded",
                f"Excluded {construction_count} construction geometry item(s).",
                tuple(item.index for item in sketch.geometry if item.construction),
            )
        )
    if sketch.external_geometry_count and not include_external:
        findings.append(
            _finding(
                "info",
                "external_geometry_excluded",
                f"Excluded {sketch.external_geometry_count} external geometry item(s).",
            )
        )

    candidates: list[tuple[SketchGeometry, bool]] = []
    for item in sketch.geometry:
        if selected is not None and item.index not in selected:
            continue
        if item.construction and not include_construction:
            continue
        candidates.append((item, False))
    if include_external:
        candidates.extend((item, True) for item in external_geometry)

    edges: list[_Edge] = []
    unsupported: list[int] = []
    points: list[int] = []
    for item, external in candidates:
        if isinstance(item, SketchLineGeometry):
            edges.append(_line_edge(item, external))
        elif isinstance(item, SketchArcGeometry):
            edges.append(_arc_edge(item, external))
        elif isinstance(item, SketchCircleGeometry):
            edges.append(_circle_edge(item, external))
        elif isinstance(item, SketchPointGeometry):
            points.append(item.index)
        elif isinstance(item, UnsupportedSketchGeometry):
            unsupported.append(item.index)

    if points:
        findings.append(
            _finding(
                "info",
                "point_geometry_excluded",
                "Point geometry does not form profile edges.",
                tuple(points),
            )
        )
    if unsupported:
        findings.append(
            _finding(
                "warning",
                "unsupported_geometry",
                "Unsupported geometry was excluded from profile topology.",
                tuple(unsupported),
            )
        )

    edges.sort(key=lambda item: item.index)
    edge_tuple = tuple(edges)
    endpoints = tuple(
        endpoint
        for edge in edge_tuple
        if edge.kind != "circle"
        for endpoint in (
            _Endpoint(edge.index, "start", _required_point(edge.start)),
            _Endpoint(edge.index, "end", _required_point(edge.end)),
        )
    )
    vertices, edge_vertices = _cluster_endpoints(endpoints)
    edge_set = tuple(edge.index for edge in edge_tuple)
    disjoint = _DisjointSet(edge_set)
    edge_by_index = {edge.index: edge for edge in edge_tuple}

    for vertex in vertices:
        incident_geometry = sorted({item.geometry_index for item in vertex.members})
        for first, second in pairwise(incident_geometry):
            disjoint.union(first, second)

    # An endpoint landing in the interior of another bounded edge is a true
    # topological junction.  The traversed edge contributes two half-edges.
    for vertex in vertices:
        point = SketchPoint2D(vertex.x, vertex.y)
        incident_set = {item.geometry_index for item in vertex.members}
        for edge in edge_tuple:
            if edge.index in incident_set or edge.kind == "circle":
                continue
            if _point_on_edge_interior(point, edge):
                vertex.degree += 2
                disjoint.union(min(incident_set), edge.index)
                incident_set.add(edge.index)

    bad_geometry: set[int] = set()
    _detect_degenerate_and_duplicate(edge_tuple, findings, bad_geometry)
    _detect_near_openings(vertices, findings)
    _detect_intersections(
        edge_tuple,
        edge_vertices,
        disjoint,
        findings,
        bad_geometry,
    )

    grouped: dict[int, list[int]] = defaultdict(list)
    for edge in edge_tuple:
        grouped[disjoint.find(edge.index)].append(edge.index)
    groups = sorted((tuple(sorted(values)) for values in grouped.values()), key=lambda x: x)
    components: list[_Component] = []
    geometry_component: dict[int, int] = {}
    for number, geometry in enumerate(groups):
        vertex_numbers = tuple(
            vertex.number
            for vertex in vertices
            if any(member.geometry_index in geometry for member in vertex.members)
            or _vertex_incident_to_geometry(vertex, geometry, edge_by_index)
        )
        for vertex_number in vertex_numbers:
            vertices[vertex_number].component_number = number
        open_count = sum(vertices[item].degree == 1 for item in vertex_numbers)
        branch_count = sum(vertices[item].degree > 2 for item in vertex_numbers)
        contains_circle = any(edge_by_index[index].kind == "circle" for index in geometry)
        component_bad = bool(set(geometry) & bad_geometry)
        simple = (
            (len(geometry) == 1 and contains_circle and not vertex_numbers)
            or (
                not contains_circle
                and bool(vertex_numbers)
                and open_count == 0
                and branch_count == 0
                and len(geometry) == len(vertex_numbers)
                and all(vertices[item].degree == 2 for item in vertex_numbers)
            )
        ) and not component_bad
        if simple:
            classification = "simple_closed_loop"
        elif branch_count:
            classification = "branched_component"
        elif open_count:
            classification = "open_chain"
        elif component_bad:
            classification = "ambiguous_component"
        elif len(geometry) > len(vertex_numbers):
            classification = "multiple_loops"
        else:
            classification = "ambiguous_component"
        component = _Component(
            number=number,
            geometry_indices=geometry,
            vertex_numbers=vertex_numbers,
            edge_count=len(geometry),
            open_vertex_count=open_count,
            branch_vertex_count=branch_count,
            classification=classification,
            closed_loop_candidate=simple,
            profile_candidate=simple,
        )
        components.append(component)
        for index in geometry:
            geometry_component[index] = number

    open_vertices = tuple(vertex.number for vertex in vertices if vertex.degree == 1)
    if open_vertices:
        open_geometries = tuple(
            sorted(
                {
                    member.geometry_index
                    for number in open_vertices
                    for member in vertices[number].members
                }
            )
        )
        findings.append(
            _finding(
                "warning",
                "open_vertices_found",
                f"The sketch contains {len(open_vertices)} open profile vertex/vertices.",
                open_geometries,
                open_vertices,
            )
        )
    branch_vertices = tuple(vertex.number for vertex in vertices if vertex.degree > 2)
    if branch_vertices:
        branch_geometries = tuple(
            sorted(
                {
                    member.geometry_index
                    for number in branch_vertices
                    for member in vertices[number].members
                }
            )
        )
        findings.append(
            _finding(
                "error",
                "branched_topology",
                "One or more topology vertices have degree greater than two.",
                branch_geometries,
                branch_vertices,
            )
        )
    if not edge_tuple:
        findings.append(_finding("info", "empty_sketch", "No profile edges participate."))

    profiles = _build_profiles(tuple(components), edge_by_index, edge_vertices, tuple(vertices))
    profiles = _apply_containment(profiles, edge_by_index, edge_vertices)
    if len(profiles) > 1:
        findings.append(
            _finding(
                "info",
                "multiple_profile_components",
                f"The sketch contains {len(profiles)} probable closed profiles.",
                tuple(index for profile in profiles for index in profile.geometry_indices),
            )
        )

    topology_findings = _sorted_findings(findings)
    analysis_findings = list(topology_findings)
    _append_solver_findings(sketch, analysis_findings)
    return _CoreAnalysis(
        sketch=sketch,
        document=document,
        edges=edge_tuple,
        edge_vertices=edge_vertices,
        vertices=tuple(vertices),
        components=tuple(components),
        profiles=profiles,
        topology_findings=topology_findings,
        analysis_findings=_sorted_findings(analysis_findings),
        participating_count=len(edge_tuple),
        construction_count=construction_count,
        external_count=sketch.external_geometry_count,
        selected_indices=geometry_indices,
    )


def _line_edge(item: SketchLineGeometry, external: bool) -> _Edge:
    return _Edge(item.index, "line", start=item.start, end=item.end, external=external)


def _arc_edge(item: SketchArcGeometry, external: bool) -> _Edge:
    return _Edge(
        item.index,
        "arc",
        start=item.start,
        end=item.end,
        center=item.center,
        radius=item.radius,
        start_angle=math.radians(item.start_angle_degrees),
        end_angle=math.radians(item.end_angle_degrees),
        external=external,
    )


def _circle_edge(item: SketchCircleGeometry, external: bool) -> _Edge:
    return _Edge(
        item.index,
        "circle",
        center=item.center,
        radius=item.radius,
        external=external,
    )


def _cluster_endpoints(
    endpoints: tuple[_Endpoint, ...],
) -> tuple[list[_Vertex], dict[int, tuple[int, int] | None]]:
    ordered = sorted(
        endpoints,
        key=lambda item: (
            item.point.x,
            item.point.y,
            item.geometry_index,
            _POSITION_ORDER[item.position],
        ),
    )
    parent = list(range(len(ordered)))

    def find(value: int) -> int:
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    def union(first: int, second: int) -> None:
        first_root = find(first)
        second_root = find(second)
        if first_root != second_root:
            parent[max(first_root, second_root)] = min(first_root, second_root)

    for first in range(len(ordered)):
        for second in range(first + 1, len(ordered)):
            if ordered[second].point.x - ordered[first].point.x > TOPOLOGY_TOLERANCE:
                break
            if _distance(ordered[first].point, ordered[second].point) <= TOPOLOGY_TOLERANCE:
                union(first, second)

    grouped: dict[int, list[_Endpoint]] = defaultdict(list)
    for index, endpoint in enumerate(ordered):
        grouped[find(index)].append(endpoint)
    raw_clusters: list[tuple[float, float, tuple[_Endpoint, ...]]] = []
    for members in grouped.values():
        stable_members = tuple(
            sorted(
                members,
                key=lambda item: (item.geometry_index, _POSITION_ORDER[item.position]),
            )
        )
        raw_clusters.append(
            (
                sum(item.point.x for item in stable_members) / len(stable_members),
                sum(item.point.y for item in stable_members) / len(stable_members),
                stable_members,
            )
        )
    raw_clusters.sort(
        key=lambda item: (
            item[0],
            item[1],
            item[2][0].geometry_index,
            _POSITION_ORDER[item[2][0].position],
        )
    )
    vertices = [
        _Vertex(number, x, y, members, len(members))
        for number, (x, y, members) in enumerate(raw_clusters)
    ]
    memberships: dict[tuple[int, str], int] = {}
    for vertex in vertices:
        for member in vertex.members:
            memberships[(member.geometry_index, member.position)] = vertex.number
    edge_vertices: dict[int, tuple[int, int] | None] = {}
    for endpoint in endpoints:
        if endpoint.geometry_index in edge_vertices:
            continue
        edge_vertices[endpoint.geometry_index] = (
            memberships[(endpoint.geometry_index, "start")],
            memberships[(endpoint.geometry_index, "end")],
        )
    return vertices, edge_vertices


def _detect_degenerate_and_duplicate(
    edges: tuple[_Edge, ...],
    findings: list[dict[str, object]],
    bad_geometry: set[int],
) -> None:
    for edge in edges:
        zero = (
            edge.kind == "line"
            and _distance(_required_point(edge.start), _required_point(edge.end))
            <= TOPOLOGY_TOLERANCE
        )
        if edge.kind == "arc":
            zero = _arc_sweep(edge) * _required_radius(edge) <= TOPOLOGY_TOLERANCE
        if zero:
            bad_geometry.add(edge.index)
            findings.append(
                _finding(
                    "error",
                    "zero_length_geometry",
                    "A participating geometry item has zero or negligible length.",
                    (edge.index,),
                )
            )

    for first, second in combinations(edges, 2):
        if _duplicate(first, second, TOPOLOGY_TOLERANCE):
            bad_geometry.update((first.index, second.index))
            findings.append(
                _finding(
                    "error",
                    "duplicate_geometry",
                    "Two participating geometry items are exact duplicates.",
                    (first.index, second.index),
                )
            )
        elif _duplicate(first, second, NEAR_TOLERANCE):
            findings.append(
                _finding(
                    "warning",
                    "suspected_near_duplicate",
                    "Two geometry items are nearly coincident.",
                    (first.index, second.index),
                )
            )
        elif _overlap(first, second):
            bad_geometry.update((first.index, second.index))
            findings.append(
                _finding(
                    "warning",
                    "suspected_overlap",
                    "Two participating geometry items overlap along a non-zero interval.",
                    (first.index, second.index),
                )
            )


def _detect_near_openings(vertices: list[_Vertex], findings: list[dict[str, object]]) -> None:
    open_vertices = [item for item in vertices if item.degree == 1]
    warned: set[tuple[int, int]] = set()
    for first, second in combinations(open_vertices, 2):
        distance = math.hypot(first.x - second.x, first.y - second.y)
        if TOPOLOGY_TOLERANCE < distance <= NEAR_TOLERANCE:
            pair = (first.number, second.number)
            if pair in warned:
                continue
            warned.add(pair)
            findings.append(
                _finding(
                    "warning",
                    "suspected_near_open_gap",
                    "Two open vertices are separated by a small gap above the topology tolerance.",
                    tuple(
                        sorted(
                            {
                                member.geometry_index
                                for vertex in (first, second)
                                for member in vertex.members
                            }
                        )
                    ),
                    pair,
                )
            )


def _detect_intersections(
    edges: tuple[_Edge, ...],
    edge_vertices: dict[int, tuple[int, int] | None],
    disjoint: _DisjointSet,
    findings: list[dict[str, object]],
    bad_geometry: set[int],
) -> None:
    reported: set[tuple[str, int, int]] = set()
    for first, second in combinations(edges, 2):
        intersections = _curve_intersections(first, second)
        for point, tangent in intersections:
            first_endpoint = _endpoint_match(first, point)
            second_endpoint = _endpoint_match(second, point)
            if first_endpoint is not None and second_endpoint is not None:
                first_vertices = edge_vertices.get(first.index)
                second_vertices = edge_vertices.get(second.index)
                if first_vertices is not None and second_vertices is not None:
                    first_vertex = first_vertices[0 if first_endpoint == "start" else 1]
                    second_vertex = second_vertices[0 if second_endpoint == "start" else 1]
                    if first_vertex == second_vertex:
                        continue
            disjoint.union(first.index, second.index)
            # Endpoint-on-interior contacts are represented as topology junctions
            # and become branch findings through degree counting.
            if (first_endpoint is None) != (second_endpoint is None):
                continue
            code = "tangent_touch" if tangent else "self_intersection"
            key = (code, first.index, second.index)
            if key in reported:
                continue
            reported.add(key)
            bad_geometry.update((first.index, second.index))
            findings.append(
                _finding(
                    "warning" if tangent else "error",
                    code,
                    (
                        "Two profile elements touch tangentially away from a shared endpoint."
                        if tangent
                        else "Two profile elements intersect away from a shared endpoint."
                    ),
                    (first.index, second.index),
                )
            )


def _curve_intersections(first: _Edge, second: _Edge) -> tuple[tuple[SketchPoint2D, bool], ...]:
    if first.kind == "line" and second.kind == "line":
        value = _line_line_intersection(first, second)
        return () if value is None else ((value, False),)
    if first.kind == "line":
        return _line_round_intersections(first, second)
    if second.kind == "line":
        return _line_round_intersections(second, first)
    return _round_round_intersections(first, second)


def _line_line_intersection(first: _Edge, second: _Edge) -> SketchPoint2D | None:
    p = _required_point(first.start)
    p2 = _required_point(first.end)
    q = _required_point(second.start)
    q2 = _required_point(second.end)
    r = (p2.x - p.x, p2.y - p.y)
    s = (q2.x - q.x, q2.y - q.y)
    denominator = _cross(r, s)
    q_minus_p = (q.x - p.x, q.y - p.y)
    if abs(denominator) <= TOPOLOGY_TOLERANCE:
        return None
    t = _cross(q_minus_p, s) / denominator
    u = _cross(q_minus_p, r) / denominator
    parameter_tolerance = TOPOLOGY_TOLERANCE / max(math.hypot(*r), 1.0)
    if -parameter_tolerance <= t <= 1.0 + parameter_tolerance and (
        -parameter_tolerance <= u <= 1.0 + parameter_tolerance
    ):
        return SketchPoint2D(p.x + t * r[0], p.y + t * r[1])
    return None


def _line_round_intersections(
    line: _Edge, rounded: _Edge
) -> tuple[tuple[SketchPoint2D, bool], ...]:
    start = _required_point(line.start)
    end = _required_point(line.end)
    center = _required_point(rounded.center)
    radius = _required_radius(rounded)
    dx = end.x - start.x
    dy = end.y - start.y
    fx = start.x - center.x
    fy = start.y - center.y
    a = dx * dx + dy * dy
    if a <= TOPOLOGY_TOLERANCE**2:
        return ()
    b = 2.0 * (fx * dx + fy * dy)
    c = fx * fx + fy * fy - radius * radius
    discriminant = b * b - 4.0 * a * c
    scale = max(a * radius * radius, 1.0)
    if discriminant < -TOPOLOGY_TOLERANCE * scale:
        return ()
    tangent = abs(discriminant) <= TOPOLOGY_TOLERANCE * scale
    root = math.sqrt(max(0.0, discriminant))
    parameters = ((-b - root) / (2.0 * a), (-b + root) / (2.0 * a))
    result: list[tuple[SketchPoint2D, bool]] = []
    for parameter in parameters:
        if not -TOPOLOGY_TOLERANCE <= parameter <= 1.0 + TOPOLOGY_TOLERANCE:
            continue
        point = SketchPoint2D(start.x + parameter * dx, start.y + parameter * dy)
        if rounded.kind == "arc" and not _point_on_arc(point, rounded):
            continue
        if not any(_distance(point, previous[0]) <= TOPOLOGY_TOLERANCE for previous in result):
            result.append((point, tangent))
    return tuple(result)


def _round_round_intersections(
    first: _Edge, second: _Edge
) -> tuple[tuple[SketchPoint2D, bool], ...]:
    first_center = _required_point(first.center)
    second_center = _required_point(second.center)
    first_radius = _required_radius(first)
    second_radius = _required_radius(second)
    distance = _distance(first_center, second_center)
    if distance <= TOPOLOGY_TOLERANCE:
        return ()
    if distance > first_radius + second_radius + TOPOLOGY_TOLERANCE:
        return ()
    if distance < abs(first_radius - second_radius) - TOPOLOGY_TOLERANCE:
        return ()
    a = (first_radius**2 - second_radius**2 + distance**2) / (2.0 * distance)
    h_squared = first_radius**2 - a**2
    if h_squared < -TOPOLOGY_TOLERANCE:
        return ()
    h = math.sqrt(max(0.0, h_squared))
    ux = (second_center.x - first_center.x) / distance
    uy = (second_center.y - first_center.y) / distance
    base_x = first_center.x + a * ux
    base_y = first_center.y + a * uy
    tangent = h <= TOPOLOGY_TOLERANCE
    candidates = (
        SketchPoint2D(base_x + h * -uy, base_y + h * ux),
        SketchPoint2D(base_x - h * -uy, base_y - h * ux),
    )
    result: list[tuple[SketchPoint2D, bool]] = []
    for point in candidates:
        if first.kind == "arc" and not _point_on_arc(point, first):
            continue
        if second.kind == "arc" and not _point_on_arc(point, second):
            continue
        if not any(_distance(point, previous[0]) <= TOPOLOGY_TOLERANCE for previous in result):
            result.append((point, tangent))
    return tuple(result)


def _duplicate(first: _Edge, second: _Edge, tolerance: float) -> bool:
    if first.kind != second.kind:
        return False
    if first.kind == "line":
        first_start = _required_point(first.start)
        first_end = _required_point(first.end)
        second_start = _required_point(second.start)
        second_end = _required_point(second.end)
        return (
            _distance(first_start, second_start) <= tolerance
            and _distance(first_end, second_end) <= tolerance
        ) or (
            _distance(first_start, second_end) <= tolerance
            and _distance(first_end, second_start) <= tolerance
        )
    if _distance(_required_point(first.center), _required_point(second.center)) > tolerance:
        return False
    if abs(_required_radius(first) - _required_radius(second)) > tolerance:
        return False
    if first.kind == "circle":
        return True
    return (
        _distance(_required_point(first.start), _required_point(second.start)) <= tolerance
        and _distance(_required_point(first.end), _required_point(second.end)) <= tolerance
        and abs(_arc_sweep(first) - _arc_sweep(second)) <= tolerance
    )


def _overlap(first: _Edge, second: _Edge) -> bool:
    if first.kind == second.kind == "line":
        a = _required_point(first.start)
        b = _required_point(first.end)
        c = _required_point(second.start)
        d = _required_point(second.end)
        direction = (b.x - a.x, b.y - a.y)
        if abs(_cross(direction, (c.x - a.x, c.y - a.y))) > TOPOLOGY_TOLERANCE:
            return False
        if abs(_cross(direction, (d.x - a.x, d.y - a.y))) > TOPOLOGY_TOLERANCE:
            return False
        use_x = abs(direction[0]) >= abs(direction[1])
        first_interval = sorted((a.x, b.x) if use_x else (a.y, b.y))
        second_interval = sorted((c.x, d.x) if use_x else (c.y, d.y))
        overlap = min(first_interval[1], second_interval[1]) - max(
            first_interval[0], second_interval[0]
        )
        return overlap > TOPOLOGY_TOLERANCE
    if first.kind == second.kind == "arc":
        if (
            _distance(_required_point(first.center), _required_point(second.center))
            > TOPOLOGY_TOLERANCE
            or abs(_required_radius(first) - _required_radius(second)) > TOPOLOGY_TOLERANCE
        ):
            return False
        first_mid = _arc_point(first, _required_angle(first.start_angle) + _arc_sweep(first) / 2)
        second_mid = _arc_point(
            second, _required_angle(second.start_angle) + _arc_sweep(second) / 2
        )
        return _point_on_arc(first_mid, second) or _point_on_arc(second_mid, first)
    return False


def _point_on_edge_interior(point: SketchPoint2D, edge: _Edge) -> bool:
    if edge.kind == "line":
        start = _required_point(edge.start)
        end = _required_point(edge.end)
        if min(_distance(point, start), _distance(point, end)) <= NEAR_TOLERANCE:
            return False
        direction = (end.x - start.x, end.y - start.y)
        length_squared = direction[0] ** 2 + direction[1] ** 2
        if length_squared <= TOPOLOGY_TOLERANCE**2:
            return False
        cross = abs(_cross(direction, (point.x - start.x, point.y - start.y)))
        if cross > TOPOLOGY_TOLERANCE * math.sqrt(length_squared):
            return False
        parameter = (
            (point.x - start.x) * direction[0] + (point.y - start.y) * direction[1]
        ) / length_squared
        return TOPOLOGY_TOLERANCE < parameter < 1.0 - TOPOLOGY_TOLERANCE
    if edge.kind == "arc" and _point_on_arc(point, edge):
        return (
            min(
                _distance(point, _required_point(edge.start)),
                _distance(point, _required_point(edge.end)),
            )
            > NEAR_TOLERANCE
        )
    if edge.kind == "circle":
        center = _required_point(edge.center)
        return abs(_distance(point, center) - _required_radius(edge)) <= TOPOLOGY_TOLERANCE
    return False


def _vertex_incident_to_geometry(
    vertex: _Vertex, geometry: tuple[int, ...], edge_by_index: dict[int, _Edge]
) -> bool:
    point = SketchPoint2D(vertex.x, vertex.y)
    return any(_point_on_edge_interior(point, edge_by_index[index]) for index in geometry)


def _build_profiles(
    components: tuple[_Component, ...],
    edge_by_index: dict[int, _Edge],
    edge_vertices: dict[int, tuple[int, int] | None],
    vertices: tuple[_Vertex, ...],
) -> tuple[_Profile, ...]:
    profiles: list[_Profile] = []
    for component in components:
        if not component.profile_candidate:
            continue
        edge = edge_by_index[component.geometry_indices[0]]
        if len(component.geometry_indices) == 1 and edge.kind == "circle":
            center = _required_point(edge.center)
            radius = _required_radius(edge)
            profiles.append(
                _Profile(
                    number=len(profiles),
                    component_number=component.number,
                    geometry_indices=component.geometry_indices,
                    signed_area=math.pi * radius * radius,
                    orientation="counter_clockwise",
                    witness=SketchPoint2D(center.x + radius, center.y),
                )
            )
            continue
        traversal = _loop_traversal(component, edge_vertices)
        area = 0.0
        for geometry_index, forward in traversal:
            item = edge_by_index[geometry_index]
            if item.kind == "line":
                start = _required_point(item.start if forward else item.end)
                end = _required_point(item.end if forward else item.start)
                area += 0.5 * (start.x * end.y - end.x * start.y)
            elif item.kind == "arc":
                contribution = _arc_area_contribution(item)
                area += contribution if forward else -contribution
        orientation = (
            "counter_clockwise"
            if area > TOPOLOGY_TOLERANCE
            else "clockwise"
            if area < -TOPOLOGY_TOLERANCE
            else "unknown"
        )
        first_vertex = vertices[component.vertex_numbers[0]]
        profiles.append(
            _Profile(
                number=len(profiles),
                component_number=component.number,
                geometry_indices=component.geometry_indices,
                signed_area=area if orientation != "unknown" else None,
                orientation=orientation,
                witness=SketchPoint2D(first_vertex.x, first_vertex.y),
            )
        )
    return tuple(profiles)


def _loop_traversal(
    component: _Component, edge_vertices: dict[int, tuple[int, int] | None]
) -> tuple[tuple[int, bool], ...]:
    adjacency: dict[int, list[int]] = defaultdict(list)
    for geometry_index in component.geometry_indices:
        pair = edge_vertices[geometry_index]
        if pair is None:
            continue
        adjacency[pair[0]].append(geometry_index)
        adjacency[pair[1]].append(geometry_index)
    current_vertex = min(component.vertex_numbers)
    starting_vertex = current_vertex
    previous_edge: int | None = None
    traversal: list[tuple[int, bool]] = []
    while len(traversal) < len(component.geometry_indices):
        choices = sorted(item for item in adjacency[current_vertex] if item != previous_edge)
        if not choices:
            break
        geometry_index = choices[0]
        pair = edge_vertices[geometry_index]
        assert pair is not None
        forward = current_vertex == pair[0]
        next_vertex = pair[1] if forward else pair[0]
        traversal.append((geometry_index, forward))
        previous_edge = geometry_index
        current_vertex = next_vertex
        if current_vertex == starting_vertex:
            break
    return tuple(traversal)


def _arc_area_contribution(edge: _Edge) -> float:
    center = _required_point(edge.center)
    radius = _required_radius(edge)
    start = _required_angle(edge.start_angle)
    end = start + _arc_sweep(edge)
    return 0.5 * (
        radius * center.x * (math.sin(end) - math.sin(start))
        - radius * center.y * (math.cos(end) - math.cos(start))
        + radius * radius * (end - start)
    )


def _apply_containment(
    profiles: tuple[_Profile, ...],
    edge_by_index: dict[int, _Edge],
    edge_vertices: dict[int, tuple[int, int] | None],
) -> tuple[_Profile, ...]:
    containers: dict[int, list[int]] = defaultdict(list)
    for child, parent in combinations(profiles, 2):
        if _point_in_profile(child.witness, parent, edge_by_index):
            containers[child.number].append(parent.number)
        elif _point_in_profile(parent.witness, child, edge_by_index):
            containers[parent.number].append(child.number)
    result: list[_Profile] = []
    for profile in profiles:
        parents = containers.get(profile.number, [])
        immediate = None
        if parents:
            immediate = min(
                parents,
                key=lambda number: abs(profiles[number].signed_area or math.inf),
            )
        children = tuple(
            item.number
            for item in profiles
            if profile.number in containers.get(item.number, [])
            and (
                not containers.get(item.number)
                or min(
                    containers[item.number],
                    key=lambda number: abs(profiles[number].signed_area or math.inf),
                )
                == profile.number
            )
        )
        result.append(
            _Profile(
                number=profile.number,
                component_number=profile.component_number,
                geometry_indices=profile.geometry_indices,
                signed_area=profile.signed_area,
                orientation=profile.orientation,
                witness=profile.witness,
                contains=children,
                contained_by=immediate,
            )
        )
    return tuple(result)


def _point_in_profile(
    point: SketchPoint2D, profile: _Profile, edge_by_index: dict[int, _Edge]
) -> bool:
    if len(profile.geometry_indices) == 1:
        edge = edge_by_index[profile.geometry_indices[0]]
        if edge.kind == "circle":
            return _distance(point, _required_point(edge.center)) < (
                _required_radius(edge) - TOPOLOGY_TOLERANCE
            )
    # Shift the ray off exact vertices deterministically to avoid double counts.
    ray_y = point.y + 17.0 * TOPOLOGY_TOLERANCE
    crossings = 0
    for index in profile.geometry_indices:
        edge = edge_by_index[index]
        if edge.kind == "line":
            start = _required_point(edge.start)
            end = _required_point(edge.end)
            if (start.y > ray_y) == (end.y > ray_y):
                continue
            x = start.x + (ray_y - start.y) * (end.x - start.x) / (end.y - start.y)
            crossings += x > point.x
        elif edge.kind in {"arc", "circle"}:
            center = _required_point(edge.center)
            radius = _required_radius(edge)
            sine = (ray_y - center.y) / radius
            if not -1.0 < sine < 1.0:
                continue
            base = math.asin(sine)
            for angle in (base, math.pi - base):
                candidate = SketchPoint2D(
                    center.x + radius * math.cos(angle),
                    ray_y,
                )
                if candidate.x <= point.x:
                    continue
                if edge.kind == "arc" and not _angle_on_arc(angle, edge):
                    continue
                crossings += 1
    return crossings % 2 == 1


def _profile_classification(core: _CoreAnalysis) -> tuple[str, bool]:
    codes = {str(item["code"]) for item in core.topology_findings}
    if "unsupported_geometry" in codes:
        return "unsupported_geometry", False
    if not core.edges:
        return "empty", False
    if "self_intersection" in codes:
        return "self_intersecting_profile", False
    if "branched_topology" in codes:
        return "branched_profile", False
    if "open_vertices_found" in codes:
        return "open_profile", False
    if codes & {
        "duplicate_geometry",
        "zero_length_geometry",
        "suspected_overlap",
        "tangent_touch",
    }:
        return "ambiguous_profile", False
    if len(core.profiles) != len(core.components):
        return "ambiguous_profile", False
    if any(profile.contained_by is not None for profile in core.profiles):
        return "nested_profiles", True
    if len(core.profiles) == 1:
        return "single_closed_profile", True
    return "multiple_disjoint_profiles", True


def _append_solver_findings(
    sketch: SketchInspectionResult, findings: list[dict[str, object]]
) -> None:
    solver = sketch.solver
    if not solver.available:
        findings.append(
            _finding(
                "info",
                "solver_diagnostics_unavailable",
                "Solver diagnostics are unavailable.",
            )
        )
        return
    if not solver.fresh:
        findings.append(
            _finding(
                "info",
                "solver_diagnostics_stale",
                "Cached solver diagnostics are not fresh; analysis did not recompute the sketch.",
            )
        )
        return
    mapping = (
        (solver.conflicting_constraint_indices, "solver_conflicts", "conflicting"),
        (solver.redundant_constraint_indices, "solver_redundancies", "redundant"),
        (
            solver.partially_redundant_constraint_indices,
            "solver_partial_redundancies",
            "partially redundant",
        ),
        (solver.malformed_constraint_indices, "malformed_constraints", "malformed"),
    )
    for indices, code, label in mapping:
        if indices:
            findings.append(
                _finding(
                    "error" if code in {"solver_conflicts", "malformed_constraints"} else "warning",
                    code,
                    f"The solver reports {len(indices)} {label} constraint(s).",
                    constraint_indices=indices,
                )
            )
    if solver.fully_constrained is False:
        findings.append(
            _finding(
                "warning",
                "underconstrained_sketch",
                "The solver reports that the sketch is underconstrained.",
            )
        )


def _finding(
    severity: Literal["info", "warning", "error"],
    code: str,
    message: str,
    geometry_indices: tuple[int, ...] = (),
    topology_vertex_numbers: tuple[int, ...] = (),
    *,
    constraint_indices: tuple[int, ...] = (),
) -> dict[str, object]:
    result: dict[str, object] = {
        "severity": severity,
        "code": code,
        "message": message,
        "geometry_indices": list(sorted(set(geometry_indices))),
        "topology_vertex_numbers": list(sorted(set(topology_vertex_numbers))),
    }
    if constraint_indices:
        result["constraint_indices"] = list(constraint_indices)
    return result


def _sorted_findings(
    findings: list[dict[str, object]],
) -> tuple[dict[str, object], ...]:
    deduplicated: dict[tuple[object, ...], dict[str, object]] = {}
    for item in findings:
        key: tuple[object, ...] = (
            item["code"],
            tuple(item["geometry_indices"]),  # type: ignore[arg-type]
            tuple(item["topology_vertex_numbers"]),  # type: ignore[arg-type]
        )
        deduplicated[key] = item
    return tuple(
        sorted(
            deduplicated.values(),
            key=lambda item: (
                _SEVERITY_ORDER[str(item["severity"])],
                str(item["code"]),
                tuple(item["geometry_indices"]),  # type: ignore[arg-type]
                tuple(item["topology_vertex_numbers"]),  # type: ignore[arg-type]
            ),
        )
    )


def _component_dict(item: _Component) -> dict[str, object]:
    return {
        "component_number": item.number,
        "geometry_indices": list(item.geometry_indices),
        "topology_vertex_numbers": list(item.vertex_numbers),
        "edge_count": item.edge_count,
        "vertex_count": len(item.vertex_numbers),
        "open_vertex_count": item.open_vertex_count,
        "branch_vertex_count": item.branch_vertex_count,
        "classification": item.classification,
        "closed_loop_candidate": item.closed_loop_candidate,
        "profile_candidate": item.profile_candidate,
    }


def _profile_dict(item: _Profile) -> dict[str, object]:
    return {
        "profile_number": item.number,
        "geometry_indices": list(item.geometry_indices),
        "component_number": item.component_number,
        "closed": True,
        "simple": True,
        "orientation": item.orientation,
        "signed_area": item.signed_area,
        "contains_profile_numbers": list(item.contains),
        "contained_by_profile_number": item.contained_by,
    }


def _open_vertex_dict(item: _Vertex) -> dict[str, object]:
    return {
        "topology_vertex_number": item.number,
        "x": item.x,
        "y": item.y,
        "degree": item.degree,
        "status": "open",
        "component_number": item.component_number,
        "members": [
            {
                "geometry_index": member.geometry_index,
                "position": member.position,
                "x": member.point.x,
                "y": member.point.y,
            }
            for member in item.members
        ],
    }


def _sketch_summary(sketch: SketchInspectionResult) -> dict[str, object]:
    return {
        "name": sketch.name,
        "label": sketch.label,
        "body_name": sketch.body_name,
        "visibility": sketch.visibility,
        "map_mode": sketch.map_mode,
        "attachment": None if sketch.attachment is None else sketch.attachment.to_dict(),
        "placement": None if sketch.placement is None else sketch.placement.to_dict(),
        "geometry_count": sketch.geometry_count,
        "external_geometry_count": sketch.external_geometry_count,
        "constraint_count": sketch.constraint_count,
    }


def _indices(value: tuple[int, ...] | None) -> list[int] | None:
    return None if value is None else list(value)


def _endpoint_match(edge: _Edge, point: SketchPoint2D) -> Literal["start", "end"] | None:
    if edge.kind == "circle":
        return None
    if _distance(point, _required_point(edge.start)) <= TOPOLOGY_TOLERANCE:
        return "start"
    if _distance(point, _required_point(edge.end)) <= TOPOLOGY_TOLERANCE:
        return "end"
    return None


def _point_on_arc(point: SketchPoint2D, edge: _Edge) -> bool:
    center = _required_point(edge.center)
    radius = _required_radius(edge)
    if abs(_distance(point, center) - radius) > TOPOLOGY_TOLERANCE:
        return False
    return _angle_on_arc(math.atan2(point.y - center.y, point.x - center.x), edge)


def _angle_on_arc(angle: float, edge: _Edge) -> bool:
    start = _normalize_angle(_required_angle(edge.start_angle))
    delta = (_normalize_angle(angle) - start) % math.tau
    return delta <= _arc_sweep(edge) + TOPOLOGY_TOLERANCE


def _arc_sweep(edge: _Edge) -> float:
    start = _required_angle(edge.start_angle)
    end = _required_angle(edge.end_angle)
    sweep = (end - start) % math.tau
    if sweep <= TOPOLOGY_TOLERANCE and abs(end - start) > TOPOLOGY_TOLERANCE:
        return math.tau
    return sweep


def _arc_point(edge: _Edge, angle: float) -> SketchPoint2D:
    center = _required_point(edge.center)
    radius = _required_radius(edge)
    return SketchPoint2D(
        center.x + radius * math.cos(angle),
        center.y + radius * math.sin(angle),
    )


def _normalize_angle(value: float) -> float:
    return value % math.tau


def _distance(first: SketchPoint2D, second: SketchPoint2D) -> float:
    return math.hypot(first.x - second.x, first.y - second.y)


def _cross(first: tuple[float, float], second: tuple[float, float]) -> float:
    return first[0] * second[1] - first[1] * second[0]


def _required_point(value: SketchPoint2D | None) -> SketchPoint2D:
    assert value is not None
    return value


def _required_radius(value: _Edge | float | None) -> float:
    actual = value.radius if isinstance(value, _Edge) else value
    assert actual is not None
    return actual


def _required_angle(value: float | None) -> float:
    assert value is not None
    return value


__all__ = [
    "NEAR_TOLERANCE",
    "TOPOLOGY_TOLERANCE",
    "analyze_sketch",
    "list_sketch_open_vertices",
    "validate_sketch_profile",
]
