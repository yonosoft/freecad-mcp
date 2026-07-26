"""Coherent document validation definitions."""

from __future__ import annotations

from freecad_mcp.core.result import CommandResult
from freecad_mcp.validation.common import (
    _INTERNAL_NAME_PATTERN,
    _INTERNAL_NAME_RULE,
    _validate_object_name,
    _validate_optional_label,
)


def validate_document_reference(name: object) -> CommandResult | None:
    """Validate an internal document name used for lookup or saving."""
    if not isinstance(name, str):
        return CommandResult.failure(
            code="validation_error",
            message="Document name must be a non-empty string.",
            data={"field": "name", "actual_type": type(name).__name__},
        )
    if not name.strip():
        return CommandResult.failure(
            code="validation_error",
            message="Document name must not be empty or whitespace.",
            data={"field": "name"},
        )
    if _INTERNAL_NAME_PATTERN.fullmatch(name) is None:
        return CommandResult.failure(
            code="validation_error",
            message="Document name does not satisfy the MCP document-name policy.",
            data={"field": "name", "name": name, "rule": _INTERNAL_NAME_RULE},
        )
    return None


def validate_document_history_request(
    document_name: object,
    expected_transaction_name: object | None = None,
) -> CommandResult | None:
    """Validate one history inspection or mutation request."""
    document_error = validate_document_reference(document_name)
    if document_error is not None:
        return document_error
    if expected_transaction_name is None:
        return None
    if not isinstance(expected_transaction_name, str):
        return CommandResult.failure(
            code="validation_error",
            message="Expected transaction name must be a non-empty string when supplied.",
            data={
                "field": "expected_transaction_name",
                "actual_type": type(expected_transaction_name).__name__,
            },
        )
    if not expected_transaction_name.strip():
        return CommandResult.failure(
            code="validation_error",
            message="Expected transaction name must not be empty or whitespace.",
            data={"field": "expected_transaction_name"},
        )
    return None


def validate_object_reference(document_name: object, object_name: object) -> CommandResult | None:
    """Validate document- and object-name arguments used for object lookup."""
    doc_error = validate_document_reference(document_name)
    if doc_error is not None:
        return doc_error
    return _validate_object_name(object_name, field="object_name", subject="Object")


def validate_create_document_request(name: object, label: object | None) -> CommandResult | None:
    """Validate create-document arguments without changing its error contract."""
    if name is None:
        return CommandResult.failure(
            code="name_required",
            message="Document name is required.",
            data={"field": "name"},
        )
    if not isinstance(name, str):
        return CommandResult.failure(
            code="invalid_name_type",
            message="Document name must be a string.",
            data={"field": "name", "actual_type": type(name).__name__},
        )
    if not name.strip():
        return CommandResult.failure(
            code="name_required",
            message="Document name must not be empty or whitespace.",
            data={"field": "name"},
        )
    if _INTERNAL_NAME_PATTERN.fullmatch(name) is None:
        return CommandResult.failure(
            code="invalid_document_name",
            message="Document name does not satisfy the MCP document-name policy.",
            data={"field": "name", "name": name, "rule": _INTERNAL_NAME_RULE},
        )
    return _validate_optional_label(label, subject="Document", code="invalid_label_type")
