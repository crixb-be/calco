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
