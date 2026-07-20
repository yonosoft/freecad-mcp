"""Isolated FreeCAD 1.1 capability probes for sketch external operands.

The coordinator launches one disposable FreeCAD process per case.  Native
negative GeoIds exist only inside workers and are never part of a public MCP
contract.  A worker crash is therefore contained and reported by the parent.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import math
import os
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FREECAD_PYTHON = Path(r"C:\Program Files\FreeCAD 1.1\bin\python.exe")


@dataclass(frozen=True, slots=True)
class ProbeCase:
    name: str
    variant: str
    mode: str
    operand_roles: str
    operand_pattern: str
    internal_geometry: tuple[str, ...]
    external_geometry: tuple[str, ...]
    native_type: str
    native_args: tuple[str | int | float, ...]
    point_positions: str = "not_applicable"
    source_kind: str = "sketch_geometry"


def _case(
    name: str,
    variant: str,
    mode: str,
    roles: str,
    pattern: str,
    internal: tuple[str, ...],
    external: tuple[str, ...],
    native_type: str,
    *native_args: str | int | float,
    point_positions: str = "not_applicable",
    source_kind: str = "sketch_geometry",
) -> ProbeCase:
    return ProbeCase(
        name,
        variant,
        mode,
        roles,
        pattern,
        internal,
        external,
        native_type,
        native_args,
        point_positions,
        source_kind,
    )


def _cases() -> tuple[ProbeCase, ...]:
    cases: list[ProbeCase] = [
        # Internal/internal parity covers every discriminator and every existing mode.
        _case(
            "ii_horizontal",
            "horizontal",
            "whole_geometry",
            "geometry",
            "internal",
            ("line",),
            (),
            "Horizontal",
            "i0",
        ),
        _case(
            "ii_vertical",
            "vertical",
            "whole_geometry",
            "geometry",
            "internal",
            ("line",),
            (),
            "Vertical",
            "i0",
        ),
        _case(
            "ii_horizontal_points",
            "horizontal_points",
            "point/point",
            "first/second",
            "internal/internal",
            ("line", "line"),
            (),
            "Horizontal",
            "i0",
            2,
            "i1",
            1,
            point_positions="end/start",
        ),
        _case(
            "ii_vertical_points",
            "vertical_points",
            "point/point",
            "first/second",
            "internal/internal",
            ("line", "line"),
            (),
            "Vertical",
            "i0",
            2,
            "i1",
            1,
            point_positions="end/start",
        ),
        _case(
            "ii_parallel",
            "parallel",
            "geometry/geometry",
            "first/second",
            "internal/internal",
            ("line", "line"),
            (),
            "Parallel",
            "i0",
            "i1",
        ),
        _case(
            "ii_perpendicular",
            "perpendicular",
            "geometry/geometry",
            "first/second",
            "internal/internal",
            ("line", "line"),
            (),
            "Perpendicular",
            "i0",
            "i1",
        ),
        _case(
            "ii_equal",
            "equal",
            "geometry/geometry",
            "first/second",
            "internal/internal",
            ("line", "line"),
            (),
            "Equal",
            "i0",
            "i1",
        ),
        _case(
            "ii_coincident",
            "coincident",
            "point/point",
            "first/second",
            "internal/internal",
            ("line", "line"),
            (),
            "Coincident",
            "i0",
            2,
            "i1",
            1,
            point_positions="end/start",
        ),
        _case(
            "ii_point_on_object",
            "point_on_object",
            "point/object",
            "first/second",
            "internal/internal",
            ("point", "circle"),
            (),
            "PointOnObject",
            "i0",
            1,
            "i1",
            point_positions="point/object",
        ),
        _case(
            "ii_symmetric_origin",
            "symmetric",
            "point/point/about_origin",
            "first/second/about",
            "internal/internal/origin",
            ("point", "point"),
            (),
            "Symmetric",
            "i0",
            1,
            "i1",
            1,
            -1,
            1,
            point_positions="point/point/origin",
        ),
        _case(
            "ii_tangent",
            "tangent",
            "geometry/geometry",
            "first/second",
            "internal/internal",
            ("circle", "line"),
            (),
            "Tangent",
            "i0",
            "i1",
        ),
        _case(
            "ii_distance_line_length",
            "distance",
            "line_length",
            "geometry/value",
            "internal/value",
            ("line",),
            (),
            "Distance",
            "i0",
            6.0,
        ),
        _case(
            "ii_distance_point_origin",
            "distance",
            "point_to_origin",
            "point/origin/value",
            "internal/origin/value",
            ("point",),
            (),
            "Distance",
            "i0",
            1,
            -1,
            1,
            4.0,
            point_positions="point/origin",
        ),
        _case(
            "ii_distance_between_points",
            "distance",
            "between_points",
            "first/second/value",
            "internal/internal/value",
            ("point", "point"),
            (),
            "Distance",
            "i0",
            1,
            "i1",
            1,
            4.0,
            point_positions="point/point",
        ),
        _case(
            "ii_distance_x_point_origin",
            "distance_x",
            "point_to_origin",
            "point/origin/value",
            "internal/origin/value",
            ("point",),
            (),
            "DistanceX",
            "i0",
            1,
            2.0,
            point_positions="point/origin",
        ),
        _case(
            "ii_distance_x_between_points",
            "distance_x",
            "between_points",
            "first/second/value",
            "internal/internal/value",
            ("point", "point"),
            (),
            "DistanceX",
            "i0",
            1,
            "i1",
            1,
            2.0,
            point_positions="point/point",
        ),
        _case(
            "ii_distance_y_point_origin",
            "distance_y",
            "point_to_origin",
            "point/origin/value",
            "internal/origin/value",
            ("point",),
            (),
            "DistanceY",
            "i0",
            1,
            2.0,
            point_positions="point/origin",
        ),
        _case(
            "ii_distance_y_between_points",
            "distance_y",
            "between_points",
            "first/second/value",
            "internal/internal/value",
            ("point", "point"),
            (),
            "DistanceY",
            "i0",
            1,
            "i1",
            1,
            2.0,
            point_positions="point/point",
        ),
        _case(
            "ii_radius",
            "radius",
            "whole_geometry",
            "geometry/value",
            "internal/value",
            ("circle",),
            (),
            "Radius",
            "i0",
            3.0,
        ),
        _case(
            "ii_diameter",
            "diameter",
            "whole_geometry",
            "geometry/value",
            "internal/value",
            ("circle",),
            (),
            "Diameter",
            "i0",
            6.0,
        ),
        _case(
            "ii_angle_line",
            "angle",
            "line_angle",
            "geometry/value",
            "internal/value",
            ("line",),
            (),
            "Angle",
            "i0",
            math.radians(30.0),
        ),
        _case(
            "ii_angle_between",
            "angle",
            "between_lines",
            "first/second/value",
            "internal/internal/value",
            ("line", "line"),
            (),
            "Angle",
            "i0",
            "i1",
            math.radians(60.0),
        ),
        # Unary external and point-to-origin cases probe read-only driving behavior.
        _case(
            "e_horizontal",
            "horizontal",
            "whole_geometry",
            "geometry",
            "external",
            (),
            ("line",),
            "Horizontal",
            "e0",
        ),
        _case(
            "e_vertical",
            "vertical",
            "whole_geometry",
            "geometry",
            "external",
            (),
            ("line",),
            "Vertical",
            "e0",
        ),
        _case(
            "e_distance_line_length",
            "distance",
            "line_length",
            "geometry/value",
            "external/value",
            (),
            ("line",),
            "Distance",
            "e0",
            6.0,
        ),
        _case(
            "e_distance_point_origin",
            "distance",
            "point_to_origin",
            "point/origin/value",
            "external/origin/value",
            (),
            ("line",),
            "Distance",
            "e0",
            1,
            -1,
            1,
            4.0,
            point_positions="start/origin",
        ),
        _case(
            "e_distance_x_point_origin",
            "distance_x",
            "point_to_origin",
            "point/origin/value",
            "external/origin/value",
            (),
            ("line",),
            "DistanceX",
            "e0",
            1,
            2.0,
            point_positions="start/origin",
        ),
        _case(
            "e_distance_y_point_origin",
            "distance_y",
            "point_to_origin",
            "point/origin/value",
            "external/origin/value",
            (),
            ("line",),
            "DistanceY",
            "e0",
            1,
            2.0,
            point_positions="start/origin",
        ),
        _case(
            "e_radius",
            "radius",
            "whole_geometry",
            "geometry/value",
            "external/value",
            (),
            ("circle",),
            "Radius",
            "e0",
            3.0,
        ),
        _case(
            "e_diameter",
            "diameter",
            "whole_geometry",
            "geometry/value",
            "external/value",
            (),
            ("circle",),
            "Diameter",
            "e0",
            6.0,
        ),
        _case(
            "e_angle_line",
            "angle",
            "line_angle",
            "geometry/value",
            "external/value",
            (),
            ("line",),
            "Angle",
            "e0",
            math.radians(30.0),
        ),
    ]

    binary_specs = (
        ("horizontal_points", "point/point", "Horizontal", (2, 1), "end/start"),
        ("vertical_points", "point/point", "Vertical", (2, 1), "end/start"),
        ("parallel", "geometry/geometry", "Parallel", (), "not_applicable"),
        ("perpendicular", "geometry/geometry", "Perpendicular", (), "not_applicable"),
        ("equal", "geometry/geometry", "Equal", (), "not_applicable"),
        ("coincident", "point/point", "Coincident", (2, 1), "end/start"),
        ("tangent", "geometry/geometry", "Tangent", (), "not_applicable"),
        ("distance", "between_points", "Distance", (2, 1, 4.0), "end/start"),
        ("distance_x", "between_points", "DistanceX", (2, 1, 2.0), "end/start"),
        ("distance_y", "between_points", "DistanceY", (2, 1, 2.0), "end/start"),
        ("angle", "between_lines", "Angle", (math.radians(45.0),), "not_applicable"),
    )
    for variant, mode, native_type, extras, point_positions in binary_specs:
        geometry_type = "circle" if variant == "tangent" else "line"
        for suffix, pattern, first, second, internal, external in (
            ("ie", "internal/external", "i0", "e0", (geometry_type,), (geometry_type,)),
            ("ei", "external/internal", "e0", "i0", (geometry_type,), (geometry_type,)),
            ("ee", "external/external", "e0", "e1", (), (geometry_type, geometry_type)),
        ):
            if variant in {
                "horizontal_points",
                "vertical_points",
                "coincident",
                "distance",
                "distance_x",
                "distance_y",
            }:
                args: tuple[str | int | float, ...] = (first, extras[0], second, *extras[1:])
            elif variant == "angle":
                args = (first, second, *extras)
            else:
                args = (first, second)
            cases.append(
                _case(
                    f"{suffix}_{variant}_{mode}",
                    variant,
                    mode,
                    "first/second"
                    + (
                        "/value"
                        if variant in {"distance", "distance_x", "distance_y", "angle"}
                        else ""
                    ),
                    pattern,
                    internal,
                    external,
                    native_type,
                    *args,
                    point_positions=point_positions,
                )
            )

    # Point-on-object direction, target-type, and selector coverage.
    for target_type in ("line", "circle", "arc"):
        cases.extend(
            (
                _case(
                    f"ie_point_on_{target_type}",
                    "point_on_object",
                    "point/object",
                    "first/second",
                    "internal/external",
                    ("point",),
                    (target_type,),
                    "PointOnObject",
                    "i0",
                    1,
                    "e0",
                    point_positions="point/object",
                ),
                _case(
                    f"ei_point_on_{target_type}",
                    "point_on_object",
                    "point/object",
                    "first/second",
                    "external/internal",
                    (target_type,),
                    ("line",),
                    "PointOnObject",
                    "e0",
                    1,
                    "i0",
                    point_positions="start/object",
                ),
            )
        )
    cases.append(
        _case(
            "ee_point_on_object",
            "point_on_object",
            "point/object",
            "first/second",
            "external/external",
            (),
            ("line", "circle"),
            "PointOnObject",
            "e0",
            1,
            "e1",
            point_positions="start/object",
        )
    )

    # Point selectors on mixed operands, including an object vertex projection.
    cases.extend(
        (
            _case(
                "ie_coincident_start_end",
                "coincident",
                "point/point",
                "first/second",
                "internal/external",
                ("line",),
                ("line",),
                "Coincident",
                "i0",
                1,
                "e0",
                2,
                point_positions="start/end",
            ),
            _case(
                "ie_coincident_arc_center",
                "coincident",
                "point/point",
                "first/second",
                "internal/external",
                ("arc",),
                ("circle",),
                "Coincident",
                "i0",
                3,
                "e0",
                3,
                point_positions="center/center",
            ),
            _case(
                "ie_coincident_external_arc_center",
                "coincident",
                "point/point",
                "first/second",
                "internal/external",
                ("circle",),
                ("arc",),
                "Coincident",
                "i0",
                3,
                "e0",
                3,
                point_positions="center/center",
            ),
            _case(
                "ie_coincident_arc_end",
                "coincident",
                "point/point",
                "first/second",
                "internal/external",
                ("arc",),
                ("arc",),
                "Coincident",
                "i0",
                2,
                "e0",
                1,
                point_positions="end/start",
            ),
            _case(
                "ie_coincident_external_vertex",
                "coincident",
                "point/point",
                "first/second",
                "internal/external",
                ("point",),
                ("point",),
                "Coincident",
                "i0",
                1,
                "e0",
                1,
                point_positions="point/point",
                source_kind="object_vertex",
            ),
            _case(
                "ie_point_on_object_edge",
                "point_on_object",
                "point/object",
                "first/second",
                "internal/external",
                ("point",),
                ("line",),
                "PointOnObject",
                "i0",
                1,
                "e0",
                point_positions="point/object",
                source_kind="object_edge",
            ),
            _case(
                "ei_external_vertex_on_circle",
                "point_on_object",
                "point/object",
                "first/second",
                "external/internal",
                ("circle",),
                ("point",),
                "PointOnObject",
                "e0",
                1,
                "i0",
                point_positions="point/object",
                source_kind="object_vertex",
            ),
        )
    )

    # Geometry-pair coverage for Equal and Tangent.
    for first_type, second_type in (
        ("circle", "circle"),
        ("circle", "arc"),
        ("arc", "circle"),
        ("arc", "arc"),
    ):
        cases.append(
            _case(
                f"ie_equal_{first_type}_{second_type}",
                "equal",
                "geometry/geometry",
                "first/second",
                "internal/external",
                (first_type,),
                (second_type,),
                "Equal",
                "i0",
                "e0",
            )
        )
    for first_type, second_type in (
        ("circle", "line"),
        ("line", "circle"),
        ("arc", "line"),
        ("line", "arc"),
        ("circle", "circle"),
        ("circle", "arc"),
        ("arc", "circle"),
        ("arc", "arc"),
    ):
        cases.append(
            _case(
                f"ie_tangent_{first_type}_{second_type}",
                "tangent",
                "geometry/geometry",
                "first/second",
                "internal/external",
                (first_type,),
                (second_type,),
                "Tangent",
                "i0",
                "e0",
            )
        )
        cases.append(
            _case(
                f"ei_tangent_external_{second_type}_internal_{first_type}",
                "tangent",
                "geometry/geometry",
                "first/second",
                "external/internal",
                (first_type,),
                (second_type,),
                "Tangent",
                "e0",
                "i0",
            )
        )

    # Symmetry role permutations: first/second are point roles; about is fixed,
    # a point, or a line.  External-only combinations remain explicitly probed.
    cases.extend(
        (
            _case(
                "ie_symmetric_about_origin",
                "symmetric",
                "points_about_origin",
                "first/second/about",
                "internal/external/origin",
                ("point",),
                ("line",),
                "Symmetric",
                "i0",
                1,
                "e0",
                1,
                -1,
                1,
                point_positions="point/start/origin",
            ),
            _case(
                "ei_symmetric_about_origin",
                "symmetric",
                "points_about_origin",
                "first/second/about",
                "external/internal/origin",
                ("point",),
                ("line",),
                "Symmetric",
                "e0",
                1,
                "i0",
                1,
                -1,
                1,
                point_positions="start/point/origin",
            ),
            _case(
                "ee_symmetric_about_origin",
                "symmetric",
                "points_about_origin",
                "first/second/about",
                "external/external/origin",
                (),
                ("line", "line"),
                "Symmetric",
                "e0",
                1,
                "e1",
                1,
                -1,
                1,
                point_positions="start/start/origin",
            ),
            _case(
                "ie_symmetric_about_h_axis",
                "symmetric",
                "points_about_axis",
                "first/second/about",
                "internal/external/axis",
                ("point",),
                ("line",),
                "Symmetric",
                "i0",
                1,
                "e0",
                1,
                -1,
                point_positions="point/start/horizontal_axis",
            ),
            _case(
                "ie_symmetric_about_internal_point",
                "symmetric",
                "points_about_point",
                "first/second/about",
                "internal/external/internal",
                ("point", "point"),
                ("line",),
                "Symmetric",
                "i0",
                1,
                "e0",
                1,
                "i1",
                1,
                point_positions="point/start/point",
            ),
            _case(
                "ii_symmetric_about_external_point",
                "symmetric",
                "points_about_point",
                "first/second/about",
                "internal/internal/external",
                ("point", "point"),
                ("line",),
                "Symmetric",
                "i0",
                1,
                "i1",
                1,
                "e0",
                1,
                point_positions="point/point/start",
            ),
            _case(
                "ie_symmetric_about_internal_line",
                "symmetric",
                "points_about_line",
                "first/second/about",
                "internal/external/internal",
                ("point", "line"),
                ("line",),
                "Symmetric",
                "i0",
                1,
                "e0",
                1,
                "i1",
                point_positions="point/start/line",
            ),
            _case(
                "ii_symmetric_about_external_line",
                "symmetric",
                "points_about_line",
                "first/second/about",
                "internal/internal/external",
                ("point", "point"),
                ("line",),
                "Symmetric",
                "i0",
                1,
                "i1",
                1,
                "e0",
                point_positions="point/point/line",
            ),
            _case(
                "ei_symmetric_about_internal_point",
                "symmetric",
                "points_about_point",
                "first/second/about",
                "external/internal/internal",
                ("point", "point"),
                ("line",),
                "Symmetric",
                "e0",
                1,
                "i0",
                1,
                "i1",
                1,
                point_positions="start/point/point",
            ),
            _case(
                "ie_symmetric_about_external_point",
                "symmetric",
                "points_about_point",
                "first/second/about",
                "internal/external/external",
                ("point",),
                ("line", "line"),
                "Symmetric",
                "i0",
                1,
                "e0",
                1,
                "e1",
                1,
                point_positions="point/start/start",
            ),
            _case(
                "ei_symmetric_about_external_point",
                "symmetric",
                "points_about_point",
                "first/second/about",
                "external/internal/external",
                ("point",),
                ("line", "line"),
                "Symmetric",
                "e0",
                1,
                "i0",
                1,
                "e1",
                1,
                point_positions="start/point/start",
            ),
            _case(
                "ee_symmetric_about_internal_point",
                "symmetric",
                "points_about_point",
                "first/second/about",
                "external/external/internal",
                ("point",),
                ("line", "line"),
                "Symmetric",
                "e0",
                1,
                "e1",
                1,
                "i0",
                1,
                point_positions="start/start/point",
            ),
            _case(
                "ei_symmetric_about_internal_line",
                "symmetric",
                "points_about_line",
                "first/second/about",
                "external/internal/internal",
                ("point", "line"),
                ("line",),
                "Symmetric",
                "e0",
                1,
                "i0",
                1,
                "i1",
                point_positions="start/point/line",
            ),
            _case(
                "ie_symmetric_about_external_line",
                "symmetric",
                "points_about_line",
                "first/second/about",
                "internal/external/external",
                ("point",),
                ("line", "line"),
                "Symmetric",
                "i0",
                1,
                "e0",
                1,
                "e1",
                point_positions="point/start/line",
            ),
            _case(
                "ei_symmetric_about_external_line",
                "symmetric",
                "points_about_line",
                "first/second/about",
                "external/internal/external",
                ("point",),
                ("line", "line"),
                "Symmetric",
                "e0",
                1,
                "i0",
                1,
                "e1",
                point_positions="start/point/line",
            ),
            _case(
                "ee_symmetric_about_internal_line",
                "symmetric",
                "points_about_line",
                "first/second/about",
                "external/external/internal",
                ("line",),
                ("line", "line"),
                "Symmetric",
                "e0",
                1,
                "e1",
                1,
                "i0",
                point_positions="start/start/line",
            ),
        )
    )

    # Stale native GeoIds are deliberately probed in isolated workers.  These
    # are not public operand cases; they establish which validation paths must
    # never reach Sketcher after a mapping becomes broken or stale.
    stale_specs: tuple[
        tuple[str, str, tuple[str, ...], str, tuple[str | int | float, ...]], ...
    ] = (
        ("horizontal", "whole_geometry", (), "Horizontal", ("e0",)),
        ("vertical", "whole_geometry", (), "Vertical", ("e0",)),
        ("horizontal_points", "point/point", ("line",), "Horizontal", ("i0", 1, "e0", 1)),
        ("vertical_points", "point/point", ("line",), "Vertical", ("i0", 1, "e0", 1)),
        ("parallel", "geometry/geometry", ("line",), "Parallel", ("i0", "e0")),
        ("perpendicular", "geometry/geometry", ("line",), "Perpendicular", ("i0", "e0")),
        ("equal", "geometry/geometry", ("line",), "Equal", ("i0", "e0")),
        ("coincident", "point/point", ("line",), "Coincident", ("i0", 1, "e0", 1)),
        ("point_on_object", "point/object", ("point",), "PointOnObject", ("i0", 1, "e0")),
        ("symmetric", "points_about_origin", ("point",), "Symmetric", ("i0", 1, "e0", 1, -1, 1)),
        ("tangent", "geometry/geometry", ("circle",), "Tangent", ("i0", "e0")),
        ("distance", "line_length", (), "Distance", ("e0", 6.0)),
        ("distance", "point_to_origin", (), "Distance", ("e0", 1, -1, 1, 4.0)),
        ("distance", "between_points", ("point",), "Distance", ("i0", 1, "e0", 1, 4.0)),
        ("distance_x", "point_to_origin", (), "DistanceX", ("e0", 1, 2.0)),
        ("distance_x", "between_points", ("point",), "DistanceX", ("i0", 1, "e0", 1, 2.0)),
        ("distance_y", "point_to_origin", (), "DistanceY", ("e0", 1, 2.0)),
        ("distance_y", "between_points", ("point",), "DistanceY", ("i0", 1, "e0", 1, 2.0)),
        ("radius", "whole_geometry", (), "Radius", ("e0", 3.0)),
        ("diameter", "whole_geometry", (), "Diameter", ("e0", 6.0)),
        ("angle", "line_angle", (), "Angle", ("e0", math.radians(30.0))),
        ("angle", "between_lines", ("line",), "Angle", ("i0", "e0", math.radians(45.0))),
    )
    for number, (variant, mode, internal, native_type, native_args) in enumerate(stale_specs, 1):
        cases.append(
            _case(
                f"stale_{number:02d}_{variant}_{mode}",
                variant,
                mode,
                "stale_external_reference",
                "stale_external",
                internal,
                (),
                native_type,
                *native_args,
            )
        )

    cases.extend(
        (
            _case(
                "invalid_external_line_center",
                "coincident",
                "point/point",
                "first/second",
                "internal/external",
                ("point",),
                ("line",),
                "Coincident",
                "i0",
                1,
                "e0",
                3,
                point_positions="point/invalid_center",
            ),
            _case(
                "invalid_external_circle_start",
                "coincident",
                "point/point",
                "first/second",
                "internal/external",
                ("point",),
                ("circle",),
                "Coincident",
                "i0",
                1,
                "e0",
                1,
                point_positions="point/invalid_start",
            ),
            _case(
                "invalid_external_vertex_end",
                "coincident",
                "point/point",
                "first/second",
                "internal/external",
                ("point",),
                ("point",),
                "Coincident",
                "i0",
                1,
                "e0",
                2,
                point_positions="point/invalid_end",
                source_kind="object_vertex",
            ),
            _case(
                "invalid_parallel_line_circle",
                "parallel",
                "geometry/geometry",
                "first/second",
                "internal/external",
                ("line",),
                ("circle",),
                "Parallel",
                "i0",
                "e0",
            ),
            _case(
                "invalid_equal_line_circle",
                "equal",
                "geometry/geometry",
                "first/second",
                "internal/external",
                ("line",),
                ("circle",),
                "Equal",
                "i0",
                "e0",
            ),
            _case(
                "invalid_tangent_line_line",
                "tangent",
                "geometry/geometry",
                "first/second",
                "internal/external",
                ("line",),
                ("line",),
                "Tangent",
                "i0",
                "e0",
            ),
            _case(
                "invalid_point_on_vertex",
                "point_on_object",
                "point/object",
                "first/second",
                "internal/external",
                ("point",),
                ("point",),
                "PointOnObject",
                "i0",
                1,
                "e0",
                point_positions="point/invalid_object",
                source_kind="object_vertex",
            ),
            _case(
                "invalid_symmetric_about_circle",
                "symmetric",
                "points_about_line",
                "first/second/about",
                "internal/internal/external",
                ("point", "point"),
                ("circle",),
                "Symmetric",
                "i0",
                1,
                "i1",
                1,
                "e0",
                point_positions="point/point/invalid_line",
            ),
        )
    )
    return tuple(cases)


CASES = {case.name: case for case in _cases()}


def _resolve_arg(value: str | int | float) -> int | float:
    if isinstance(value, str) and value.startswith("i"):
        return int(value[1:])
    if isinstance(value, str) and value.startswith("e"):
        return -3 - int(value[1:])
    if isinstance(value, str):
        raise ValueError(value)
    return value


def _geometry(part: Any, app: Any, kind: str, index: int, *, external: bool) -> Any:
    offset = float(index) * 2.0
    if kind == "line":
        if external:
            return part.LineSegment(app.Vector(-5 + offset, 0, 0), app.Vector(5 + offset, 0, 0))
        return part.LineSegment(app.Vector(1 + offset, 2, 0), app.Vector(5 + offset, 3, 0))
    if kind == "circle":
        return part.Circle(
            app.Vector(offset, 0 if external else 3, 0), app.Vector(0, 0, 1), 5 if external else 2
        )
    if kind == "arc":
        circle = part.Circle(
            app.Vector(offset, 0 if external else 3, 0), app.Vector(0, 0, 1), 5 if external else 2
        )
        return part.ArcOfCircle(circle, 0.15, 2.8)
    if kind == "point":
        return part.Point(app.Vector(offset if external else 1 + offset, 0 if external else 3, 0))
    raise ValueError(kind)


def _signature(item: Any) -> tuple[object, ...]:
    if hasattr(item, "StartPoint"):
        return (
            "line",
            float(item.StartPoint.x),
            float(item.StartPoint.y),
            float(item.EndPoint.x),
            float(item.EndPoint.y),
        )
    if hasattr(item, "FirstParameter"):
        return (
            "arc",
            float(item.Center.x),
            float(item.Center.y),
            float(item.Radius),
            float(item.FirstParameter),
            float(item.LastParameter),
        )
    if hasattr(item, "Center"):
        return ("circle", float(item.Center.x), float(item.Center.y), float(item.Radius))
    return ("point", float(item.X), float(item.Y))


def _constraint_state(constraint: Any) -> dict[str, object]:
    return {
        "type": str(constraint.Type),
        "first": int(constraint.First),
        "first_pos": int(constraint.FirstPos),
        "second": int(constraint.Second),
        "second_pos": int(constraint.SecondPos),
        "third": int(constraint.Third),
        "third_pos": int(constraint.ThirdPos),
        "value": float(constraint.Value),
        "driving": bool(constraint.Driving),
        "active": bool(constraint.IsActive),
    }


def _source_signature(source: Any, case: ProbeCase) -> tuple[object, ...]:
    if case.source_kind == "sketch_geometry":
        return tuple(_signature(item) for item in source.Geometry)
    if case.source_kind == "object_edge":
        edge = source.Shape.getElement("Edge1")
        vertices = tuple(edge.Vertexes)
        return (
            "object_edge",
            tuple(
                (float(vertex.Point.x), float(vertex.Point.y), float(vertex.Point.z))
                for vertex in vertices
            ),
        )
    vertex = source.Shape.getElement("Vertex1")
    return ("object_vertex", float(vertex.Point.x), float(vertex.Point.y), float(vertex.Point.z))


def _solver_state(sketch: Any) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, attribute in (("degrees_of_freedom", "getSolverDoF"), ("solve_return", "solve")):
        try:
            result[key] = int(getattr(sketch, attribute)())
        except Exception as exc:
            result[key] = f"unreadable:{type(exc).__name__}"
    for key, attribute in (
        ("fully_constrained", "FullyConstrained"),
        ("solver_messages", "SolverMessages"),
    ):
        try:
            result[key] = getattr(sketch, attribute)
        except Exception:
            result[key] = None
    return result


def _mutate_source(source: Any, case: ProbeCase, part: Any, app: Any) -> None:
    if case.source_kind == "object_edge":
        source.Shape = part.makeLine(app.Vector(-5, 1, 0), app.Vector(5, 1, 0))
        return
    if case.source_kind == "object_vertex":
        source.Shape = part.Vertex(app.Vector(1, 1, 0))
        return
    kind = case.external_geometry[0]
    position = 1 if kind in {"line", "arc"} else 3
    source.moveGeometry(0, position, app.Vector(-4, 1, 0), False)


def _worker(case: ProbeCase) -> dict[str, object]:
    import FreeCAD as App  # type: ignore[import-not-found]
    import Part  # type: ignore[import-not-found]
    import Sketcher  # type: ignore[import-not-found]

    document = App.newDocument("M21Probe")
    document.UndoMode = 1
    source: Any
    target: Any
    try:
        if case.source_kind == "sketch_geometry":
            source = document.addObject("Sketcher::SketchObject", "Source")
            for index, kind in enumerate(case.external_geometry):
                source.addGeometry(_geometry(Part, App, kind, index, external=True), False)
        else:
            source = document.addObject("PartDesign::Feature", "Source")
            if case.source_kind == "object_edge":
                source.Shape = Part.makeLine(App.Vector(-5, 0, 0), App.Vector(5, 0, 0))
            else:
                source.Shape = Part.Vertex(App.Vector(0, 0, 0))

        document.recompute()

        target = document.addObject("Sketcher::SketchObject", "Target")
        for index, kind in enumerate(case.internal_geometry):
            target.addGeometry(_geometry(Part, App, kind, index, external=False), False)
        for index, _kind in enumerate(case.external_geometry):
            subelement = "Vertex1" if case.source_kind == "object_vertex" else f"Edge{index + 1}"
            target.addExternal(source.Name, subelement)
        document.recompute()
        document.clearUndos()

        source_before = _source_signature(source, case)
        internal_before = tuple(_signature(item) for item in target.Geometry)
        external_before = tuple(_signature(item) for item in target.ExternalGeo[2:])
        mapping_before = tuple(
            (str(item[0].Name), tuple(item[1])) for item in target.ExternalGeometry
        )

        document.openTransaction("M21 isolated probe")
        constructor = Sketcher.Constraint(
            case.native_type, *(_resolve_arg(arg) for arg in case.native_args)
        )
        assigned = target.addConstraint(constructor)
        document.recompute()
        document.commitTransaction()
        constraints_after = tuple(_constraint_state(item) for item in target.Constraints)
        result: dict[str, object] = {
            "case": asdict(case),
            "freecad_version": ".".join(App.Version()[:3]),
            "native_status": "accepted",
            "assigned_index": int(assigned),
            "constraints_after": constraints_after,
            "solver_after": _solver_state(target),
            "source_unchanged": source_before == _source_signature(source, case),
            "internal_moved": internal_before
            != tuple(_signature(item) for item in target.Geometry),
            "external_mapping_unchanged": mapping_before
            == tuple((str(item[0].Name), tuple(item[1])) for item in target.ExternalGeometry),
        }

        document.undo()
        document.recompute()
        result["undo"] = {
            "constraint_count": int(target.ConstraintCount),
            "source_preserved": source_before == _source_signature(source, case),
        }
        document.redo()
        document.recompute()
        result["redo"] = {
            "constraint_count": int(target.ConstraintCount),
            "constraint_type": str(target.Constraints[0].Type) if target.ConstraintCount else None,
        }

        with tempfile.TemporaryDirectory(prefix="freecad-m21-probe-") as directory:
            path = str(Path(directory) / "probe.FCStd")
            document.saveAs(path)
            App.closeDocument(document.Name)
            document = App.openDocument(path)
            source = document.getObject("Source")
            target = document.getObject("Target")
            result["save_reopen"] = {
                "constraint_count": int(target.ConstraintCount),
                "constraint_type": str(target.Constraints[0].Type)
                if target.ConstraintCount
                else None,
                "external_count": max(0, len(tuple(target.ExternalGeo)) - 2),
            }
            if not case.external_geometry:
                result["source_change"] = {"attempted": False, "reason": "internal_only"}
                result["initial_external_projection_count"] = len(external_before)
                return result
            projection_before_change = tuple(_signature(item) for item in target.ExternalGeo[2:])
            internal_before_change = tuple(_signature(item) for item in target.Geometry)
            try:
                _mutate_source(source, case, Part, App)
                document.recompute()
                result["source_change"] = {
                    "attempted": True,
                    "projection_changed": projection_before_change
                    != tuple(_signature(item) for item in target.ExternalGeo[2:]),
                    "internal_changed": internal_before_change
                    != tuple(_signature(item) for item in target.Geometry),
                    "constraint_survived": int(target.ConstraintCount) == 1,
                    "solver": _solver_state(target),
                }
            except Exception as exc:
                result["source_change"] = {
                    "attempted": True,
                    "error": f"{type(exc).__name__}:{exc}",
                }
        result["initial_external_projection_count"] = len(external_before)
        return result
    except Exception as exc:
        with contextlib.suppress(Exception):
            document.abortTransaction()
        return {
            "case": asdict(case),
            "freecad_version": ".".join(App.Version()[:3]),
            "native_status": "exception",
            "exception_type": type(exc).__name__,
            "exception": str(exc),
        }
    finally:
        try:
            if App.getDocument("M21Probe") is not None:
                App.closeDocument("M21Probe")
        except Exception:
            pass


def _coordinator(args: argparse.Namespace) -> int:
    executable = Path(args.freecad_python)
    results: list[dict[str, object]] = []
    selected = tuple(CASES.values()) if not args.case else tuple(CASES[name] for name in args.case)
    for number, case in enumerate(selected, 1):
        completed = subprocess.run(
            [str(executable), str(Path(__file__).resolve()), "--worker", case.name],
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            text=True,
            timeout=args.timeout,
            check=False,
            env={**os.environ, "PYTHONPATH": str(REPOSITORY_ROOT / "src")},
        )
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError:
            payload = {
                "case": asdict(case),
                "native_status": "process_failure",
                "exit_code": completed.returncode,
                "stdout": completed.stdout[-2000:],
                "stderr": completed.stderr[-2000:],
            }
        payload["process_exit_code"] = completed.returncode
        results.append(payload)
        print(
            f"[{number:03d}/{len(selected):03d}] {case.name}: {payload.get('native_status')}",
            file=sys.stderr,
            flush=True,
        )
    report = {
        "probe_count": len(results),
        "accepted": sum(item.get("native_status") == "accepted" for item in results),
        "exceptions": sum(item.get("native_status") == "exception" for item in results),
        "process_failures": sum(item.get("native_status") == "process_failure" for item in results),
        "results": results,
    }
    serialized = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        Path(args.output).write_text(serialized + "\n", encoding="utf-8")
        print(
            json.dumps(
                {
                    key: report[key]
                    for key in ("probe_count", "accepted", "exceptions", "process_failures")
                },
                sort_keys=True,
            )
        )
    else:
        print(serialized)
    return 0 if report["process_failures"] == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", choices=tuple(CASES))
    parser.add_argument("--case", action="append", choices=tuple(CASES))
    parser.add_argument("--freecad-python", default=str(DEFAULT_FREECAD_PYTHON))
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--output")
    args = parser.parse_args()
    if args.worker:
        print(json.dumps(_worker(CASES[args.worker]), sort_keys=True))
        return 0
    return _coordinator(args)


if __name__ == "__main__":
    raise SystemExit(main())
