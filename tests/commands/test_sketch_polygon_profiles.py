from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import replace
from typing import Literal, TypeVar

import pytest
from pydantic import ValidationError

from freecad_mcp.commands.sketch_polygon import (
    CreateSketchEquilateralTriangleHandler,
    CreateSketchRegularPolygonHandler,
)
from freecad_mcp.core.result import CommandResult
from freecad_mcp.exceptions import (
    DocumentNotFoundError,
    SketchPolygonCreationError,
    SketchPolygonRollbackError,
    SketchPolygonVerificationError,
)
from freecad_mcp.freecad.sketch_polygon_profile import (
    PolygonProfileVerificationError,
    normalize_polygon_angle,
    polygon_constraint_count,
    polygon_constraint_inputs,
    polygon_geometry_inputs,
    polygon_vertex_coordinates,
    verify_polygon_geometry,
)
from freecad_mcp.models import (
    MAX_REGULAR_POLYGON_SIDE_COUNT,
    DocumentSummary,
    SketchCenterPointInput,
    SketchCircleGeometry,
    SketchEquilateralTriangleRequestInput,
    SketchInspectionResult,
    SketchLineGeometry,
    SketchPoint2D,
    SketchPointGeometry,
    SketchPolygonCircumcircleReference,
    SketchPolygonCreationResult,
    SketchPolygonEdge,
    SketchPolygonProfile,
    SketchPolygonVertex,
    SketchPolygonVertexReference,
    SketchProfileCenter,
    SketchProfilePointReference,
    SketchRegularPolygonRequestInput,
    SketchSemanticPolygonRequest,
    SketchSolverData,
)
from freecad_mcp.validation import (
    validate_create_sketch_equilateral_triangle_request,
    validate_create_sketch_regular_polygon_request,
)

T = TypeVar("T")


class Dispatcher:
    def call(self, operation: Callable[[], T]) -> T:
        return operation()


class Adapter:
    def __init__(self, outcome: Exception | None = None) -> None:
        self.outcome = outcome
        self.calls: list[SketchSemanticPolygonRequest] = []

    def create_sketch_polygon(
        self, request: SketchSemanticPolygonRequest
    ) -> SketchPolygonCreationResult:
        self.calls.append(request)
        if self.outcome is not None:
            raise self.outcome
        return _result(request)


def _semantic_request(
    *,
    side_count: int = 6,
    x: float = 0.0,
    y: float = 0.0,
    radius: float = 20.0,
    angle: float = 0.0,
    profile_type: Literal["equilateral_triangle", "regular_polygon"] = "regular_polygon",
) -> SketchSemanticPolygonRequest:
    return SketchSemanticPolygonRequest(
        document_name="Model",
        sketch_name="BaseSketch",
        side_count=side_count,
        circumradius=radius,
        center=SketchCenterPointInput(x=x, y=y),
        first_vertex_angle_degrees=angle,
        profile_type=profile_type,
    )


def _result(request: SketchSemanticPolygonRequest) -> SketchPolygonCreationResult:
    geometry_indices = tuple(range(request.side_count))
    center_index = request.side_count
    circle_index = center_index + 1
    vertices = polygon_vertex_coordinates(request)
    profile = SketchPolygonProfile(
        type=request.profile_type,
        side_count=request.side_count,
        geometry_indices=geometry_indices,
        reference_geometry_indices=(center_index, circle_index),
        constraint_indices=tuple(range(polygon_constraint_count(request))),
        edges=tuple(
            SketchPolygonEdge(index, index, index, (index + 1) % request.side_count)
            for index in geometry_indices
        ),
        vertices=tuple(
            SketchPolygonVertex(
                index,
                point[0],
                point[1],
                SketchPolygonVertexReference(index, "start"),
            )
            for index, point in enumerate(vertices)
        ),
        center=SketchProfileCenter(
            float(request.center.x),
            float(request.center.y),
            SketchProfilePointReference(center_index),
        ),
        circumcircle_reference=SketchPolygonCircumcircleReference(circle_index),
        circumradius=request.circumradius,
        first_vertex_angle_degrees=normalize_polygon_angle(request.first_vertex_angle_degrees),
    )
    sketch = SketchInspectionResult(
        name=request.sketch_name,
        label=request.sketch_name,
        body_name=None,
        visibility=True,
        map_mode="deactivated",
        attachment=None,
        placement=None,
        geometry_count=request.side_count + 2,
        external_geometry_count=0,
        constraint_count=polygon_constraint_count(request),
        geometry=(),
        constraints=(),
        solver=SketchSolverData(
            available=True,
            fresh=True,
            degrees_of_freedom=0,
            fully_constrained=True,
            conflicting_constraint_indices=(),
            redundant_constraint_indices=(),
            partially_redundant_constraint_indices=(),
            malformed_constraint_indices=(),
        ),
    )
    document = DocumentSummary("Model", "Model", None, True, True, 1)
    return SketchPolygonCreationResult(profile, sketch, document)


@pytest.mark.parametrize(
    ("x", "y", "radius", "angle"),
    [
        (0, 0, 20, 90),
        (12, -7, 15, 30),
        (0.0, 0.0, 20.0, -30.0),
        (0.0, 0.0, 20.0, 390.0),
    ],
)
def test_triangle_validation_accepts_finite_numeric_requests(
    x: float, y: float, radius: float, angle: float
) -> None:
    result = validate_create_sketch_equilateral_triangle_request(
        "Model", "BaseSketch", radius, {"x": x, "y": y}, angle
    )

    assert isinstance(result, SketchEquilateralTriangleRequestInput)
    assert result.first_vertex_angle_degrees == angle


def test_triangle_validation_applies_upright_default() -> None:
    result = validate_create_sketch_equilateral_triangle_request(
        "Model", "BaseSketch", 20.0, {"x": 0.0, "y": 0.0}
    )

    assert isinstance(result, SketchEquilateralTriangleRequestInput)
    assert result.first_vertex_angle_degrees == 90.0


@pytest.mark.parametrize("value", [0.0, -1.0, True, math.nan, math.inf, -math.inf])
def test_triangle_validation_rejects_invalid_circumradius(value: object) -> None:
    result = validate_create_sketch_equilateral_triangle_request(
        "Model", "BaseSketch", value, {"x": 0.0, "y": 0.0}
    )

    assert isinstance(result, CommandResult)
    assert result.code == "invalid_triangle_parameters"


@pytest.mark.parametrize(
    "center",
    [None, {}, {"x": 0.0}, {"x": True, "y": 0.0}, {"x": 0.0, "y": math.inf}],
)
def test_triangle_validation_rejects_invalid_center(center: object) -> None:
    result = validate_create_sketch_equilateral_triangle_request(
        "Model", "BaseSketch", 20.0, center
    )

    assert isinstance(result, CommandResult)
    assert result.code == "invalid_triangle_parameters"


@pytest.mark.parametrize("value", [True, math.nan, math.inf, -math.inf])
def test_triangle_validation_rejects_invalid_angle(value: object) -> None:
    result = validate_create_sketch_equilateral_triangle_request(
        "Model", "BaseSketch", 20.0, {"x": 0.0, "y": 0.0}, value
    )

    assert isinstance(result, CommandResult)
    assert result.code == "invalid_triangle_parameters"


@pytest.mark.parametrize("side_count", [3, 4, 5, 6, 12, MAX_REGULAR_POLYGON_SIDE_COUNT])
def test_polygon_validation_accepts_supported_side_counts(side_count: int) -> None:
    result = validate_create_sketch_regular_polygon_request(
        "Model", "BaseSketch", side_count, 20.0, {"x": 10.0, "y": -5.0}, -30.0
    )

    assert isinstance(result, SketchRegularPolygonRequestInput)
    assert result.side_count == side_count


@pytest.mark.parametrize("side_count", [2, MAX_REGULAR_POLYGON_SIDE_COUNT + 1, True, 3.0, 3.5])
def test_polygon_validation_rejects_invalid_side_counts(side_count: object) -> None:
    result = validate_create_sketch_regular_polygon_request(
        "Model", "BaseSketch", side_count, 20.0, {"x": 0.0, "y": 0.0}
    )

    assert isinstance(result, CommandResult)
    assert result.code == "invalid_polygon_parameters"


@pytest.mark.parametrize("name", ["", " ", "bad-name", 1])
def test_polygon_validation_preserves_controlled_name_policy(name: object) -> None:
    result = validate_create_sketch_regular_polygon_request(
        name, "BaseSketch", 6, 20.0, {"x": 0.0, "y": 0.0}
    )

    assert isinstance(result, CommandResult)
    assert result.code == "validation_error"


def test_polygon_public_models_forbid_extra_fields_at_every_level() -> None:
    for model in (SketchEquilateralTriangleRequestInput, SketchRegularPolygonRequestInput):
        schema = model.model_json_schema()
        assert schema["additionalProperties"] is False
        assert schema["$defs"]["SketchCenterPointInput"]["additionalProperties"] is False

    with pytest.raises(ValidationError):
        SketchEquilateralTriangleRequestInput.model_validate(
            {
                "document_name": "Model",
                "sketch_name": "Sketch",
                "circumradius": 20.0,
                "center": {"x": 0.0, "y": 0.0, "z": 0.0},
                "side_count": 3,
            }
        )
    with pytest.raises(ValidationError):
        SketchRegularPolygonRequestInput.model_validate(
            {
                "document_name": "Model",
                "sketch_name": "Sketch",
                "side_count": 6,
                "circumradius": 20.0,
                "center": {"x": 0.0, "y": 0.0},
                "placement": {},
            }
        )


@pytest.mark.parametrize(
    ("value", "expected"),
    [(0.0, 0.0), (-30.0, 330.0), (390.0, 30.0), (720.0, 0.0)],
)
def test_polygon_angle_normalization_policy(value: float, expected: float) -> None:
    assert normalize_polygon_angle(value) == expected


@pytest.mark.parametrize(
    ("polygon_request", "expected_first"),
    [
        (_semantic_request(side_count=3, angle=90.0), (0.0, 20.0)),
        (_semantic_request(side_count=4, angle=45.0), (math.sqrt(200.0), math.sqrt(200.0))),
        (_semantic_request(side_count=6, x=10.0, y=-5.0), (30.0, -5.0)),
    ],
)
def test_polygon_vertices_follow_requested_counter_clockwise_formula(
    polygon_request: SketchSemanticPolygonRequest, expected_first: tuple[float, float]
) -> None:
    vertices = polygon_vertex_coordinates(polygon_request)

    assert len(vertices) == polygon_request.side_count
    assert vertices[0] == pytest.approx(expected_first)
    signed_area = sum(
        vertices[index][0] * vertices[(index + 1) % polygon_request.side_count][1]
        - vertices[(index + 1) % polygon_request.side_count][0] * vertices[index][1]
        for index in range(polygon_request.side_count)
    )
    assert signed_area > 0.0


def test_polygon_geometry_appends_edges_center_then_explicit_circumcircle() -> None:
    request = _semantic_request(side_count=5, x=12.0, y=-7.0, angle=30.0)
    inputs = polygon_geometry_inputs(request)

    assert [item.type for item in inputs] == [
        "line_segment",
        "line_segment",
        "line_segment",
        "line_segment",
        "line_segment",
        "point",
        "circle",
    ]
    assert [item.construction for item in inputs] == [False] * 5 + [True, True]


@pytest.mark.parametrize(
    ("x", "y", "placement_types", "expected_count"),
    [
        (0.0, 0.0, ["coincident"], 21),
        (0.0, 5.0, ["point_on_object", "distance_y"], 22),
        (5.0, 0.0, ["point_on_object", "distance_x"], 22),
        (5.0, -7.0, ["distance_x", "distance_y"], 22),
    ],
)
def test_polygon_constraints_have_exact_natural_order_and_formula(
    x: float, y: float, placement_types: list[str], expected_count: int
) -> None:
    request = _semantic_request(side_count=6, x=x, y=y)
    constraints = polygon_constraint_inputs(request, 10)

    assert [item.type for item in constraints] == [
        *(["coincident"] * 6),
        *(["equal"] * 5),
        *(["point_on_object"] * 6),
        "coincident",
        *placement_types,
        "radius",
        "angle",
    ]
    assert len(constraints) == expected_count == polygon_constraint_count(request)


def test_triangle_handler_forces_three_sides_in_shared_protocol() -> None:
    adapter = Adapter()
    handler = CreateSketchEquilateralTriangleHandler(adapter, Dispatcher())

    result = handler.execute("Model", "BaseSketch", 20.0, {"x": 0.0, "y": 0.0})

    assert result.code == "sketch_equilateral_triangle_created"
    assert len(adapter.calls) == 1
    assert adapter.calls[0].side_count == 3
    assert adapter.calls[0].profile_type == "equilateral_triangle"
    assert adapter.calls[0].first_vertex_angle_degrees == 90.0


def test_polygon_handler_preserves_requested_side_count_in_shared_protocol() -> None:
    adapter = Adapter()
    handler = CreateSketchRegularPolygonHandler(adapter, Dispatcher())

    result = handler.execute("Model", "BaseSketch", 12, 20.0, {"x": 10.0, "y": -5.0})

    assert result.code == "sketch_regular_polygon_created"
    assert len(adapter.calls) == 1
    assert adapter.calls[0].side_count == 12
    assert adapter.calls[0].profile_type == "regular_polygon"


@pytest.mark.parametrize(
    ("failure", "expected_code"),
    [
        (DocumentNotFoundError(), "document_not_found"),
        (
            SketchPolygonCreationError(phase="geometry", reason="geometry_add_failed"),
            "polygon_geometry_creation_failed",
        ),
        (
            SketchPolygonCreationError(phase="reference", reason="reference_add_failed"),
            "polygon_reference_creation_failed",
        ),
        (
            SketchPolygonCreationError(phase="constraint", reason="constraint_add_failed"),
            "polygon_constraint_creation_failed",
        ),
        (SketchPolygonVerificationError("open_polygon"), "polygon_verification_failed"),
        (SketchPolygonRollbackError("rollback_failed"), "polygon_rollback_failed"),
    ],
)
def test_polygon_handler_maps_controlled_shared_failures(
    failure: Exception, expected_code: str
) -> None:
    handler = CreateSketchRegularPolygonHandler(Adapter(failure), Dispatcher())

    result = handler.execute("Model", "BaseSketch", 6, 20.0, {"x": 0.0, "y": 0.0})

    assert result.code == expected_code


def test_triangle_verification_keeps_triangle_specific_failure_code() -> None:
    handler = CreateSketchEquilateralTriangleHandler(
        Adapter(SketchPolygonVerificationError("triangle_unequal_sides")), Dispatcher()
    )

    result = handler.execute("Model", "BaseSketch", 20.0, {"x": 0.0, "y": 0.0})

    assert result.code == "triangle_verification_failed"
    assert result.data["side_count"] == 3


def test_polygon_profile_serialization_is_controlled_and_deterministic() -> None:
    data = _result(_semantic_request(side_count=3, angle=-30.0)).profile.to_dict()

    assert data["type"] == "regular_polygon"
    assert data["side_count"] == 3
    assert data["geometry_indices"] == [0, 1, 2]
    assert data["reference_geometry_indices"] == [3, 4]
    assert data["first_vertex_angle_degrees"] == 330.0
    assert data["circumcircle_reference"] == {
        "geometry_index": 4,
        "type": "circle",
        "construction": True,
    }
    assert data["edges"][2]["end_vertex"] == 0  # type: ignore[index]
    assert data["vertices"][0]["reference"] == {  # type: ignore[index]
        "geometry_index": 0,
        "position": "start",
    }


def _controlled_polygon_geometry(
    polygon_request: SketchSemanticPolygonRequest,
) -> tuple[SketchLineGeometry | SketchPointGeometry | SketchCircleGeometry, ...]:
    vertices = polygon_vertex_coordinates(polygon_request)
    edges = tuple(
        SketchLineGeometry(
            index=index,
            construction=False,
            start=SketchPoint2D(*vertices[index]),
            end=SketchPoint2D(*vertices[(index + 1) % polygon_request.side_count]),
        )
        for index in range(polygon_request.side_count)
    )
    center = SketchPoint2D(float(polygon_request.center.x), float(polygon_request.center.y))
    return (
        *edges,
        SketchPointGeometry(polygon_request.side_count, True, center),
        SketchCircleGeometry(
            polygon_request.side_count + 1,
            True,
            center,
            polygon_request.circumradius,
        ),
    )


@pytest.mark.parametrize("side_count", [3, 4, 5, 6, 12, MAX_REGULAR_POLYGON_SIDE_COUNT])
def test_semantic_polygon_verifier_accepts_all_product_sizes(side_count: int) -> None:
    polygon_request = _semantic_request(side_count=side_count, x=12.0, y=-7.0, angle=-30.0)
    geometry = _controlled_polygon_geometry(polygon_request)

    edges, center, circle = verify_polygon_geometry(
        request=polygon_request,
        geometry=geometry,
        geometry_indices=tuple(range(side_count)),
        center_index=side_count,
        circle_index=side_count + 1,
    )

    assert len(edges) == side_count
    assert center.construction is True
    assert circle.construction is True


@pytest.mark.parametrize(
    ("case", "expected_reason"),
    [
        ("side_count", "polygon_side_count_mismatch"),
        ("index_order", "polygon_geometry_order_mismatch"),
        ("wrong_edge_type", "polygon_geometry_type_mismatch"),
        ("construction_edge", "polygon_edge_state_mismatch"),
        ("open_chain", "polygon_vertex_mapping_mismatch"),
        ("wrong_vertex", "polygon_vertex_mapping_mismatch"),
        ("wrong_center_type", "polygon_center_type_mismatch"),
        ("center_not_construction", "polygon_center_state_mismatch"),
        ("wrong_center", "polygon_center_coordinate_mismatch"),
        ("wrong_circle_type", "polygon_circumcircle_type_mismatch"),
        ("circle_not_construction", "polygon_circumcircle_state_mismatch"),
        ("wrong_circle_center", "polygon_circumcircle_center_mismatch"),
        ("wrong_circle_radius", "polygon_circumcircle_radius_mismatch"),
    ],
)
def test_semantic_polygon_verifier_rejects_controlled_corruption(
    case: str, expected_reason: str
) -> None:
    polygon_request = _semantic_request(side_count=5, x=12.0, y=-7.0, angle=30.0)
    geometry = list(_controlled_polygon_geometry(polygon_request))
    geometry_indices = tuple(range(5))
    center_index = 5
    circle_index = 6

    if case == "side_count":
        geometry_indices = geometry_indices[:-1]
    elif case == "index_order":
        geometry_indices = (0, 1, 2, 4, 3)
    elif case == "wrong_edge_type":
        geometry[2] = SketchPointGeometry(2, False, SketchPoint2D(0.0, 0.0))
    elif case == "construction_edge":
        edge = geometry[2]
        assert isinstance(edge, SketchLineGeometry)
        geometry[2] = replace(edge, construction=True)
    elif case in {"open_chain", "wrong_vertex"}:
        edge = geometry[2]
        assert isinstance(edge, SketchLineGeometry)
        geometry[2] = replace(edge, start=SketchPoint2D(edge.start.x + 1.0, edge.start.y))
    elif case == "wrong_center_type":
        geometry[5] = SketchCircleGeometry(5, True, SketchPoint2D(12.0, -7.0), 20.0)
    elif case == "center_not_construction":
        center = geometry[5]
        assert isinstance(center, SketchPointGeometry)
        geometry[5] = replace(center, construction=False)
    elif case == "wrong_center":
        center = geometry[5]
        assert isinstance(center, SketchPointGeometry)
        geometry[5] = replace(center, point=SketchPoint2D(13.0, -7.0))
    elif case == "wrong_circle_type":
        geometry[6] = SketchPointGeometry(6, True, SketchPoint2D(12.0, -7.0))
    else:
        circle = geometry[6]
        assert isinstance(circle, SketchCircleGeometry)
        if case == "circle_not_construction":
            geometry[6] = replace(circle, construction=False)
        elif case == "wrong_circle_center":
            geometry[6] = replace(circle, center=SketchPoint2D(13.0, -7.0))
        else:
            geometry[6] = replace(circle, radius=19.0)

    with pytest.raises(PolygonProfileVerificationError) as raised:
        verify_polygon_geometry(
            request=polygon_request,
            geometry=tuple(geometry),
            geometry_indices=geometry_indices,
            center_index=center_index,
            circle_index=circle_index,
        )

    assert raised.value.reason == expected_reason


def test_triangle_semantic_verifier_rejects_non_three_side_profile() -> None:
    polygon_request = _semantic_request(
        side_count=4,
        angle=45.0,
        profile_type="equilateral_triangle",
    )

    with pytest.raises(PolygonProfileVerificationError, match="triangle_side_count_mismatch"):
        verify_polygon_geometry(
            request=polygon_request,
            geometry=_controlled_polygon_geometry(polygon_request),
            geometry_indices=(0, 1, 2, 3),
            center_index=4,
            circle_index=5,
        )
