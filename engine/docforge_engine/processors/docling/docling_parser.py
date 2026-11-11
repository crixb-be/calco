"""Structured document extraction facade used by DocForge Desktop.

The implementation is lazy: importing DocForge never imports the optional Docling
stack, while the action still supports PDF and image inputs when the extra is installed.
"""
from __future__ import annotations

from pathlib import Path

from ...base import action
from ..docling_core.parse import DoclingProcessor


SUPPORTED_INPUTS = frozenset({".pdf", ".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp"})
SUPPORTED_EXPORTS = ("md", "json", "html", "doctags")


class DoclingParser(DoclingProcessor):
    """Public processor name; actions and streaming progress come from DoclingProcessor."""

    engine_name = "docling_core"

    @action()
    def docling_parse(self, task, reporter):
        for raw in task.inputFiles:
            if Path(raw).suffix.lower() not in SUPPORTED_INPUTS:
                from ...errors import EngineError

                raise EngineError("INVALID_TASK", f"Docling solo acepta PDF o imágenes: {Path(raw).suffix}")
        return super().docling_parse(task, reporter)
