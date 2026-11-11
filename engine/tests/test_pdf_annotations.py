from __future__ import annotations

import threading
from pathlib import Path

import fitz
import pytest

from docforge_engine.contract import ProcessorTask
from docforge_engine.errors import EngineError
from docforge_engine.registry import EngineRegistry


def make_pdf(path: Path) -> Path:
    with fitz.open() as document:
        for index in range(2):
            page = document.new_page(width=400, height=500)
            page.insert_text((40, 60), f"Original {index + 1}")
        document.save(path)
    return path


def run_annotations(source: Path, output_dir: Path, annotations):
    task = ProcessorTask(id="annotations", engine="stirling_core", action="apply_annotations", inputFiles=[str(source)], outputDir=str(output_dir), options={"annotations": annotations})
    return EngineRegistry().execute(task, lambda event: None, threading.Event())


def test_apply_pdf_annotations(tmp_path):
    source = make_pdf(tmp_path / "source.pdf")
    outputs, meta = run_annotations(source, tmp_path, [
        {"id": "text", "page": 0, "kind": "text", "x": 50, "y": 80, "text": "Added", "size": 16, "color": "#112233"},
        {"id": "ink", "page": 0, "kind": "ink", "points": [[20, 100], [80, 120]], "color": "#ff0000", "width": 3},
        {"id": "highlight", "page": 1, "kind": "highlight", "x": 30, "y": 90, "w": 120, "h": 24, "color": "#facc15"},
    ])
    assert meta["annotations"] == 3
    with fitz.open(outputs[0]) as document:
        assert document.page_count == 2
        assert "Added" in document[0].get_text()


def test_apply_pdf_annotations_rejects_invalid_page(tmp_path):
    source = make_pdf(tmp_path / "source.pdf")
    with pytest.raises(EngineError) as error:
        run_annotations(source, tmp_path, [{"id": "bad", "page": 2, "kind": "text", "x": 1, "y": 1, "text": "x", "size": 10, "color": "#000000"}])
    assert error.value.code == "INVALID_TASK"
