from __future__ import annotations

import pytest

from freecad_mcp.constraint_expression_language import (
    ConstraintExpressionSemanticError,
    ConstraintExpressionSyntaxError,
    ConstraintReference,
    parse_constraint_expression,
    validate_constraint_identifier,
)


@pytest.mark.parametrize(
    ("expression", "canonical"),
    [
        (
            " SourceSketch.Constraints.SideLength/(2*sqrt(3)) ",
            "SourceSketch.Constraints.SideLength / (2 * sqrt(3))",
        ),
        ("Constraints.Width+2 mm", "Constraints.Width + 2 mm"),
        ("-(1.5000e1 mm)", "-15 mm"),
        ("1 mm*(2+3)", "1 mm * (2 + 3)"),
    ],
)
def test_expression_parser_canonicalizes_supported_grammar(
    expression: str,
    canonical: str,
) -> None:
    assert parse_constraint_expression(expression).canonical == canonical


def test_native_readback_can_explicitly_accept_leading_dot() -> None:
    parsed = parse_constraint_expression(
        ".Constraints.Width / 2",
        allow_native_leading_dot=True,
    )

    assert parsed.canonical == "Constraints.Width / 2"


def test_expression_parser_extracts_sorted_unique_references() -> None:
    parsed = parse_constraint_expression(
        "B.Constraints.Height + Constraints.Width + B.Constraints.Height"
    )

    assert parsed.references == (
        ConstraintReference(None, "Width"),
        ConstraintReference("B", "Height"),
    )


@pytest.mark.parametrize(
    "expression",
    [
        "",
        "(",
        "sqrt()",
        "sin(1)",
        "Spreadsheet.Width",
        "Doc#Sketch.Constraints.Width",
        ".Constraints.Width",
        "Sketch.Label.Width",
        "Constraints[0]",
        "'text'",
        "2 ^ 3",
        "2 ** 3",
        "__import__(x)",
    ],
)
def test_expression_parser_rejects_unapproved_constructs(expression: str) -> None:
    with pytest.raises(ConstraintExpressionSyntaxError):
        parse_constraint_expression(expression)


def test_dimension_inference_accepts_product_story_formula() -> None:
    parsed = parse_constraint_expression("SourceSketch.Constraints.SideLength / (2 * sqrt(3))")

    assert parsed.infer_dimension(lambda _reference: "length") == "length"


@pytest.mark.parametrize(
    ("expression", "reason"),
    [
        ("7", "expected_root_checked_by_adapter"),
        ("7 mm + 2 deg", "addition_dimension_mismatch"),
        ("7 mm * 2 mm", "multiplication_dimension_unsupported"),
        ("sqrt(4 mm)", "sqrt_requires_dimensionless"),
        ("7 mm / (2 - 2)", "division_by_zero"),
        ("7 mm / sqrt(-1)", "sqrt_domain_error"),
    ],
)
def test_dimension_inference_rejects_invalid_arithmetic(
    expression: str,
    reason: str,
) -> None:
    parsed = parse_constraint_expression(expression)
    if reason == "expected_root_checked_by_adapter":
        assert parsed.infer_dimension(lambda _reference: "length") == "dimensionless"
        return
    with pytest.raises(ConstraintExpressionSemanticError) as captured:
        parsed.infer_dimension(lambda _reference: "length")
    assert captured.value.reason == reason


@pytest.mark.parametrize("value", ["SideLength", "_width", "a1", "A" * 64])
def test_constraint_identifier_policy_accepts_controlled_names(value: str) -> None:
    assert validate_constraint_identifier(value)


@pytest.mark.parametrize(
    "value",
    ["", "1width", "with space", "with.dot", "ΔLength", "A" * 65],
)
def test_constraint_identifier_policy_rejects_native_permissiveness(value: str) -> None:
    assert not validate_constraint_identifier(value)
