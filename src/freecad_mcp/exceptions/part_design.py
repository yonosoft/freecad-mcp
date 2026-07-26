"""Coherent part design exceptions definitions."""

from __future__ import annotations


class BodyCreationError(RuntimeError):
    """Raised when FreeCAD cannot create or initialize a PartDesign::Body."""


class BodyNotFoundError(RuntimeError):
    """Raised when a requested PartDesign::Body is not found in a document."""


class BodyTypeMismatchError(RuntimeError):
    """Raised when an object exists with the requested body name but is not a PartDesign::Body."""


class OriginPlaneNotFoundError(RuntimeError):
    """Raised when a requested origin plane cannot be resolved from a body."""
