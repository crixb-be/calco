from __future__ import annotations

from pathlib import Path

from ...errors import EngineError
from ...util.paths import require_inputs


def pymupdf_module():
    try:
        import pymupdf
        return pymupdf
    except ImportError as exc:
        raise EngineError("DEPENDENCY_MISSING", "PyMuPDF is required for PDF actions", str(exc)) from exc


def open_pdf(pymupdf, path: Path):
    """Open an unencrypted PDF and normalize PyMuPDF failures for task callers."""
    try:
        document = pymupdf.open(str(path))
    except Exception as exc:
        raise EngineError("CONVERSION_FAILED", f"No se pudo abrir el PDF: {path.name}", str(exc)) from exc
    if document.needs_pass:
        document.close()
        raise EngineError("WRONG_PASSWORD", f"El PDF está protegido con contraseña: {path.name}")
    return document


# Backwards-compatible name for existing processors. It returns pymupdf and does not
# import the deprecated ``fitz`` package name.
fitz_module = pymupdf_module


def pikepdf_module():
    try:
        import pikepdf
        return pikepdf
    except ImportError as exc:
        raise EngineError("DEPENDENCY_MISSING", "pikepdf is required for PDF security actions", str(exc)) from exc


def one_input(task) -> Path:
    paths = require_inputs(task)
    if len(paths) != 1:
        raise EngineError("INVALID_TASK", "This action accepts exactly one input PDF")
    return paths[0]
