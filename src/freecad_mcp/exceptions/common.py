"""Coherent common exceptions definitions."""

from __future__ import annotations


class DispatchError(RuntimeError):
    """Raised when work cannot be delivered to the target thread."""

    def details(self) -> dict[str, object]:
        """Return fields suitable for a structured command failure."""
        return {"reason": str(self)}


class DispatchTimeoutError(DispatchError):
    """Raised when target-thread work does not finish before the deadline."""

    def __init__(self, *, cancelled_before_start: bool) -> None:
        self.cancelled_before_start = cancelled_before_start
        self.operation_may_complete = not cancelled_before_start
        if cancelled_before_start:
            outcome = "The queued operation was cancelled before it started."
        else:
            outcome = (
                "The operation started before cancellation and cannot be interrupted safely; "
                "it may already have completed or may still complete."
            )
        super().__init__(f"Timed out waiting for the FreeCAD main thread. {outcome}")

    def details(self) -> dict[str, object]:
        """Return timeout and cancellation state for command results."""
        return {
            "reason": str(self),
            "timed_out": True,
            "cancelled_before_start": self.cancelled_before_start,
            "operation_may_complete": self.operation_may_complete,
        }
