"""Finite public language for dimensional sketch-constraint expressions."""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Literal, TypeAlias, cast

Dimension = Literal["dimensionless", "length", "angle"]

MAX_EXPRESSION_LENGTH = 512
MAX_IDENTIFIER_LENGTH = 64
CONSTRAINT_IDENTIFIER_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_NUMBER_PATTERN = re.compile(r"(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?")
_IDENTIFIER_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


class ConstraintExpressionError(ValueError):
    """Base error carrying a deterministic public reason."""

    def __init__(self, reason: str, *, position: int | None = None) -> None:
        self.reason = reason
        self.position = position
        super().__init__(reason)


class ConstraintExpressionSyntaxError(ConstraintExpressionError):
    """Raised when input is not in the finite grammar."""


class ConstraintExpressionSemanticError(ConstraintExpressionError):
    """Raised when a parsed expression violates dimensional rules."""


@dataclass(frozen=True, slots=True, order=True)
class ConstraintReference:
    """One same-sketch or same-document named scalar source."""

    sketch_name: str | None
    constraint_name: str

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {"constraint_name": self.constraint_name}
        if self.sketch_name is not None:
            result["sketch_name"] = self.sketch_name
        return result


@dataclass(frozen=True, slots=True)
class _Number:
    value: str
    unit: Literal["mm", "deg"] | None


@dataclass(frozen=True, slots=True)
class _Reference:
    value: ConstraintReference


@dataclass(frozen=True, slots=True)
class _Unary:
    operator: Literal["+", "-"]
    operand: _Node


@dataclass(frozen=True, slots=True)
class _Binary:
    operator: Literal["+", "-", "*", "/"]
    left: _Node
    right: _Node


@dataclass(frozen=True, slots=True)
class _Function:
    name: Literal["sqrt"]
    argument: _Node


_Node: TypeAlias = _Number | _Reference | _Unary | _Binary | _Function


@dataclass(frozen=True, slots=True)
class ParsedConstraintExpression:
    """Parsed, canonical public expression independent of FreeCAD."""

    root: _Node
    canonical: str
    references: tuple[ConstraintReference, ...]

    def infer_dimension(
        self,
        resolver: Callable[[ConstraintReference], Dimension],
    ) -> Dimension:
        """Infer and validate dimensions using resolved source dimensions."""
        dimension = _infer_dimension(self.root, resolver)
        _validate_constant_domains(self.root)
        return dimension


@dataclass(frozen=True, slots=True)
class _Token:
    kind: Literal["number", "identifier", "symbol", "end"]
    value: str
    position: int


def validate_constraint_identifier(value: str) -> bool:
    """Return whether ``value`` is one controlled public identifier."""
    return (
        0 < len(value) <= MAX_IDENTIFIER_LENGTH
        and CONSTRAINT_IDENTIFIER_PATTERN.fullmatch(value) is not None
    )


def parse_constraint_expression(
    value: str,
    *,
    allow_native_leading_dot: bool = False,
) -> ParsedConstraintExpression:
    """Parse one public expression and return deterministic canonical form."""
    if not isinstance(value, str):
        raise ConstraintExpressionSyntaxError("expression_must_be_string")
    if not value.strip():
        raise ConstraintExpressionSyntaxError("empty_expression")
    if len(value) > MAX_EXPRESSION_LENGTH:
        raise ConstraintExpressionSyntaxError("expression_too_long")
    parser = _Parser(_tokenize(value), allow_native_leading_dot=allow_native_leading_dot)
    root = parser.parse()
    references = tuple(
        sorted(
            set(_references(root)),
            key=lambda item: (item.sketch_name or "", item.constraint_name),
        )
    )
    return ParsedConstraintExpression(
        root=root,
        canonical=_format(root),
        references=references,
    )


def _tokenize(value: str) -> tuple[_Token, ...]:
    tokens: list[_Token] = []
    position = 0
    while position < len(value):
        character = value[position]
        if character.isspace():
            position += 1
            continue
        number = _NUMBER_PATTERN.match(value, position)
        if number is not None:
            tokens.append(_Token("number", number.group(0), position))
            position = number.end()
            continue
        identifier = _IDENTIFIER_PATTERN.match(value, position)
        if identifier is not None:
            token_value = identifier.group(0)
            if len(token_value) > MAX_IDENTIFIER_LENGTH:
                raise ConstraintExpressionSyntaxError("identifier_too_long", position=position)
            tokens.append(_Token("identifier", token_value, position))
            position = identifier.end()
            continue
        if character in "+-*/().":
            tokens.append(_Token("symbol", character, position))
            position += 1
            continue
        raise ConstraintExpressionSyntaxError("unsupported_token", position=position)
    tokens.append(_Token("end", "", len(value)))
    return tuple(tokens)


class _Parser:
    def __init__(
        self,
        tokens: tuple[_Token, ...],
        *,
        allow_native_leading_dot: bool,
    ) -> None:
        self._tokens = tokens
        self._index = 0
        self._allow_native_leading_dot = allow_native_leading_dot

    @property
    def current(self) -> _Token:
        return self._tokens[self._index]

    def parse(self) -> _Node:
        result = self._additive()
        if self.current.kind != "end":
            raise ConstraintExpressionSyntaxError(
                "unexpected_token", position=self.current.position
            )
        return result

    def _additive(self) -> _Node:
        result = self._multiplicative()
        while self.current.value in {"+", "-"}:
            operator = cast(Literal["+", "-"], self._take().value)
            result = _Binary(operator, result, self._multiplicative())
        return result

    def _multiplicative(self) -> _Node:
        result = self._unary()
        while self.current.value in {"*", "/"}:
            operator = cast(Literal["*", "/"], self._take().value)
            result = _Binary(operator, result, self._unary())
        return result

    def _unary(self) -> _Node:
        if self.current.value in {"+", "-"}:
            operator = cast(Literal["+", "-"], self._take().value)
            return _Unary(operator, self._unary())
        return self._primary()

    def _primary(self) -> _Node:
        token = self.current
        if token.kind == "number":
            self._take()
            number = _canonical_number(token.value, token.position)
            unit: Literal["mm", "deg"] | None = None
            if self.current.kind == "identifier" and self.current.value in {"mm", "deg"}:
                raw_unit = self._take().value
                unit = "mm" if raw_unit == "mm" else "deg"
            return _Number(number, unit)
        if token.value == "(":
            self._take()
            result = self._additive()
            self._expect(")")
            return result
        if token.value == ".":
            # FreeCAD canonicalizes same-sketch references with a leading dot.
            # Accept it for controlled native readback but never emit it publicly.
            if not self._allow_native_leading_dot:
                raise ConstraintExpressionSyntaxError(
                    "unsupported_property_path", position=token.position
                )
            self._take()
            if self.current.value != "Constraints":
                raise ConstraintExpressionSyntaxError(
                    "unsupported_property_path", position=token.position
                )
            return self._reference(None)
        if token.kind != "identifier":
            raise ConstraintExpressionSyntaxError("expected_operand", position=token.position)
        identifier = self._take().value
        if self.current.value == "(":
            if identifier != "sqrt":
                raise ConstraintExpressionSyntaxError(
                    "unsupported_function", position=token.position
                )
            self._take()
            argument = self._additive()
            self._expect(")")
            return _Function("sqrt", argument)
        if identifier == "Constraints":
            return self._reference(None, consumed_constraints=True)
        if self.current.value != ".":
            raise ConstraintExpressionSyntaxError("unsupported_identifier", position=token.position)
        self._take()
        if self.current.value != "Constraints":
            raise ConstraintExpressionSyntaxError(
                "unsupported_property_path", position=self.current.position
            )
        return self._reference(identifier)

    def _reference(
        self,
        sketch_name: str | None,
        *,
        consumed_constraints: bool = False,
    ) -> _Node:
        if not consumed_constraints:
            constraints = self._take()
            if constraints.value != "Constraints":
                raise ConstraintExpressionSyntaxError(
                    "malformed_reference", position=constraints.position
                )
        self._expect(".")
        name = self._take()
        if name.kind != "identifier" or not validate_constraint_identifier(name.value):
            raise ConstraintExpressionSyntaxError("malformed_reference", position=name.position)
        return _Reference(ConstraintReference(sketch_name, name.value))

    def _expect(self, value: str) -> None:
        if self.current.value != value:
            raise ConstraintExpressionSyntaxError(
                "unexpected_token", position=self.current.position
            )
        self._take()

    def _take(self) -> _Token:
        result = self.current
        self._index += 1
        return result


def _canonical_number(value: str, position: int) -> str:
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise ConstraintExpressionSyntaxError("invalid_number", position=position) from exc
    if not number.is_finite():
        raise ConstraintExpressionSyntaxError("non_finite_number", position=position)
    if number == 0:
        return "0"
    normalized = number.normalize()
    adjusted = normalized.adjusted()
    if -6 <= adjusted <= 15:
        return format(normalized, "f")
    coefficient, exponent = format(normalized, "E").split("E", 1)
    return f"{coefficient}e{int(exponent)}"


def _references(node: _Node) -> tuple[ConstraintReference, ...]:
    if isinstance(node, _Reference):
        return (node.value,)
    if isinstance(node, _Unary):
        return _references(node.operand)
    if isinstance(node, _Binary):
        return (*_references(node.left), *_references(node.right))
    if isinstance(node, _Function):
        return _references(node.argument)
    return ()


def _precedence(node: _Node) -> int:
    if isinstance(node, _Binary):
        return 1 if node.operator in {"+", "-"} else 2
    if isinstance(node, _Unary):
        return 3
    return 4


def _format(node: _Node, parent_precedence: int = 0, *, right: bool = False) -> str:
    if isinstance(node, _Number):
        return node.value if node.unit is None else f"{node.value} {node.unit}"
    if isinstance(node, _Reference):
        prefix = "" if node.value.sketch_name is None else f"{node.value.sketch_name}."
        return f"{prefix}Constraints.{node.value.constraint_name}"
    if isinstance(node, _Function):
        return f"sqrt({_format(node.argument)})"
    if isinstance(node, _Unary):
        rendered = f"{node.operator}{_format(node.operand, _precedence(node))}"
    else:
        precedence = _precedence(node)
        left = _format(node.left, precedence)
        right_precedence = precedence + (1 if node.operator in {"-", "/"} else 0)
        rendered_right = _format(node.right, right_precedence, right=True)
        rendered = f"{left} {node.operator} {rendered_right}"
    precedence = _precedence(node)
    if precedence < parent_precedence or (right and precedence == parent_precedence):
        return f"({rendered})"
    return rendered


def _infer_dimension(
    node: _Node,
    resolver: Callable[[ConstraintReference], Dimension],
) -> Dimension:
    if isinstance(node, _Number):
        if node.unit == "mm":
            return "length"
        if node.unit == "deg":
            return "angle"
        return "dimensionless"
    if isinstance(node, _Reference):
        return resolver(node.value)
    if isinstance(node, _Unary):
        return _infer_dimension(node.operand, resolver)
    if isinstance(node, _Function):
        argument = _infer_dimension(node.argument, resolver)
        if argument != "dimensionless":
            raise ConstraintExpressionSemanticError("sqrt_requires_dimensionless")
        return "dimensionless"
    left = _infer_dimension(node.left, resolver)
    right = _infer_dimension(node.right, resolver)
    if node.operator in {"+", "-"}:
        if left != right:
            raise ConstraintExpressionSemanticError("addition_dimension_mismatch")
        return left
    if node.operator == "*":
        if left == "dimensionless":
            return right
        if right == "dimensionless":
            return left
        raise ConstraintExpressionSemanticError("multiplication_dimension_unsupported")
    if right == "dimensionless":
        return left
    if left == right:
        return "dimensionless"
    raise ConstraintExpressionSemanticError("division_dimension_unsupported")


def _constant_value(node: _Node) -> float | None:
    if isinstance(node, _Number):
        if node.unit is not None:
            return None
        return float(Decimal(node.value))
    if isinstance(node, _Reference):
        return None
    if isinstance(node, _Unary):
        value = _constant_value(node.operand)
        if value is None:
            return None
        return value if node.operator == "+" else -value
    if isinstance(node, _Function):
        value = _constant_value(node.argument)
        if value is None:
            return None
        if value < 0.0:
            raise ConstraintExpressionSemanticError("sqrt_domain_error")
        return math.sqrt(value)
    left = _constant_value(node.left)
    right = _constant_value(node.right)
    if left is None or right is None:
        return None
    if node.operator == "+":
        return left + right
    if node.operator == "-":
        return left - right
    if node.operator == "*":
        return left * right
    if right == 0.0:
        raise ConstraintExpressionSemanticError("division_by_zero")
    return left / right


def _validate_constant_domains(node: _Node) -> None:
    if isinstance(node, _Unary):
        _validate_constant_domains(node.operand)
    elif isinstance(node, _Function):
        _constant_value(node)
        _validate_constant_domains(node.argument)
    elif isinstance(node, _Binary):
        if node.operator == "/" and _constant_value(node.right) == 0.0:
            raise ConstraintExpressionSemanticError("division_by_zero")
        _validate_constant_domains(node.left)
        _validate_constant_domains(node.right)


__all__ = [
    "CONSTRAINT_IDENTIFIER_PATTERN",
    "MAX_EXPRESSION_LENGTH",
    "MAX_IDENTIFIER_LENGTH",
    "ConstraintExpressionError",
    "ConstraintExpressionSemanticError",
    "ConstraintExpressionSyntaxError",
    "ConstraintReference",
    "Dimension",
    "ParsedConstraintExpression",
    "parse_constraint_expression",
    "validate_constraint_identifier",
]
