"""Portable save-document validation, safety policy, and dispatch."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from freecad_mcp.core.result import CommandResult
from freecad_mcp.exceptions import (
    DispatchError,
    DocumentNotFoundError,
    DocumentSaveError,
    FileAlreadyExistsError,
    FilePathRequiredError,
    FileSystemCheckError,
    FreeCADDocumentError,
    InvalidFilePathError,
    ParentDirectoryNotFoundError,
)
from freecad_mcp.models import DocumentSummary
from freecad_mcp.protocols import Dispatcher, DocumentAdapter
from freecad_mcp.validation import validate_document_reference

_FREECAD_EXTENSION = ".FCStd"


@dataclass(frozen=True, slots=True)
class SaveDocumentHandler:
    """Validate save requests and execute reads and writes on FreeCAD's main thread."""

    adapter: DocumentAdapter
    dispatcher: Dispatcher

    def execute(
        self,
        name: object,
        file_path: object | None = None,
        overwrite: object = False,
    ) -> CommandResult:
        """Save in place or save as a protected, normalized FCStd destination."""
        validation_error = validate_document_reference(name)
        if validation_error is not None:
            return validation_error
        if not isinstance(overwrite, bool):
            return CommandResult.failure(
                code="validation_error",
                message="Overwrite must be a boolean.",
                data={"field": "overwrite", "actual_type": type(overwrite).__name__},
            )

        try:
            requested_path = _normalize_requested_path(file_path)
        except InvalidFilePathError as exc:
            return CommandResult.failure(
                code="invalid_file_path",
                message="The requested FreeCAD file path is invalid.",
                data={"file_path": file_path, "reason": str(exc)},
            )

        assert isinstance(name, str)
        try:
            document = self.dispatcher.call(
                lambda: self._save_on_main_thread(name, requested_path, overwrite)
            )
        except DocumentNotFoundError:
            return CommandResult.failure(
                code="document_not_found",
                message="The requested FreeCAD document is not open.",
                data={"name": name},
            )
        except FilePathRequiredError:
            return CommandResult.failure(
                code="file_path_required",
                message="An unsaved document requires a file path.",
                data={"name": name},
            )
        except InvalidFilePathError as exc:
            return CommandResult.failure(
                code="invalid_file_path",
                message="The requested FreeCAD file path is invalid.",
                data={"file_path": str(requested_path), "reason": str(exc)},
            )
        except ParentDirectoryNotFoundError:
            return CommandResult.failure(
                code="parent_directory_not_found",
                message="The destination parent directory does not exist.",
                data={"file_path": str(requested_path)},
            )
        except FileAlreadyExistsError:
            return CommandResult.failure(
                code="file_already_exists",
                message="The destination file already exists.",
                data={"file_path": str(requested_path)},
            )
        except (DocumentSaveError, FileSystemCheckError) as exc:
            return CommandResult.failure(
                code="save_failed",
                message="FreeCAD could not save the document.",
                data={"name": name, "reason": str(exc)},
            )
        except DispatchError as exc:
            return CommandResult.failure(
                code="freecad_error",
                message="FreeCAD could not access the document for saving.",
                data={"name": name, **exc.details()},
            )
        except FreeCADDocumentError as exc:
            return CommandResult.failure(
                code="freecad_error",
                message="FreeCAD could not access the document for saving.",
                data={"name": name, "reason": str(exc)},
            )
        except Exception as exc:
            return CommandResult.failure(
                code="internal_error",
                message="An unexpected error occurred while saving the document.",
                data={"name": name, "reason": str(exc)},
            )

        return CommandResult.success(
            code="document_saved",
            message="FreeCAD document saved.",
            data={"document": document.to_dict()},
        )

    def _save_on_main_thread(
        self,
        name: str,
        requested_path: Path | None,
        overwrite: bool,
    ) -> DocumentSummary:
        current = self.adapter.get_document(name)
        save_as_path = _select_save_as_path(current, requested_path, overwrite)
        return self.adapter.save_document(
            name,
            str(save_as_path) if save_as_path is not None else None,
        )


def _normalize_requested_path(file_path: object | None) -> Path | None:
    if file_path is None:
        return None
    if not isinstance(file_path, str):
        raise InvalidFilePathError("File path must be a string when supplied.")
    if not file_path.strip():
        raise InvalidFilePathError("File path must not be empty or whitespace.")
    if "\x00" in file_path:
        raise InvalidFilePathError("File path must not contain a null character.")

    try:
        raw_path = Path(file_path).expanduser()
        if raw_path.name in {"", ".", ".."}:
            raise InvalidFilePathError("File path must identify a file.")
        if not raw_path.suffix:
            raw_path = raw_path.with_suffix(_FREECAD_EXTENSION)
        elif raw_path.suffix.casefold() != _FREECAD_EXTENSION.casefold():
            raise InvalidFilePathError("File path must use the .FCStd extension.")
        else:
            raw_path = raw_path.with_suffix(_FREECAD_EXTENSION)
        return raw_path.resolve(strict=False)
    except InvalidFilePathError:
        raise
    except (OSError, RuntimeError, ValueError) as exc:
        raise InvalidFilePathError(str(exc)) from exc


def _select_save_as_path(
    current: DocumentSummary,
    requested_path: Path | None,
    overwrite: bool,
) -> Path | None:
    if requested_path is None:
        if current.file_path is None:
            raise FilePathRequiredError(current.name)
        return None

    if (
        current.file_path is not None
        and _normalize_current_path(current.file_path) == requested_path
    ):
        return None

    try:
        if not requested_path.parent.is_dir():
            raise ParentDirectoryNotFoundError(str(requested_path))
        if requested_path.exists():
            if requested_path.is_dir():
                raise InvalidFilePathError("The destination path identifies a directory.")
            if not overwrite:
                raise FileAlreadyExistsError(str(requested_path))
    except (
        ParentDirectoryNotFoundError,
        InvalidFilePathError,
        FileAlreadyExistsError,
    ):
        raise
    except OSError as exc:
        raise FileSystemCheckError(str(exc)) from exc
    return requested_path


def _normalize_current_path(file_path: str) -> Path:
    try:
        return Path(file_path).expanduser().resolve(strict=False)
    except (OSError, RuntimeError, ValueError) as exc:
        raise DocumentSaveError(f"Could not normalize FreeCAD's current file path: {exc}") from exc


__all__ = [
    "FileAlreadyExistsError",
    "FilePathRequiredError",
    "FileSystemCheckError",
    "InvalidFilePathError",
    "ParentDirectoryNotFoundError",
    "SaveDocumentHandler",
]
