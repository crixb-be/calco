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


def make_png(path: Path) -> Path:
    pixmap = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 8, 8), False)
    pixmap.clear_with(0x3366CC)
    pixmap.save(path)
    return path


def run_annotations(source: Path, output_dir: Path, annotations):
    task = ProcessorTask(id="annotations", engine="stirling_core", action="apply_annotations", inputFiles=[str(source)], outputDir=str(output_dir), options={"annotations": annotations})
    return EngineRegistry().execute(task, lambda event: None, threading.Event())


def test_apply_pdf_annotations(tmp_path):
    source = make_pdf(tmp_path / "source.pdf")
    image = make_png(tmp_path / "stamp.png")
    outputs, meta = run_annotations(source, tmp_path, [
        {"id": "text", "page": 0, "kind": "text", "x": 50, "y": 80, "text": "Added", "font": "helv", "bold": True, "size": 16, "color": "#112233"},
        {"id": "ink", "page": 0, "kind": "ink", "points": [[20, 100], [80, 120]], "color": "#ff0000", "width": 3},
        {"id": "highlight", "page": 1, "kind": "highlight", "x": 30, "y": 90, "w": 120, "h": 24, "color": "#facc15"},
        {"id": "rect", "page": 0, "kind": "rect", "x": 120, "y": 140, "w": 60, "h": 30, "color": "#00aa00", "width": 2},
        {"id": "line", "page": 1, "kind": "line", "x1": 20, "y1": 160, "x2": 180, "y2": 180, "color": "#0000ff", "width": 2},
        {"id": "image", "page": 1, "kind": "image", "x": 220, "y": 220, "w": 40, "h": 40, "path": str(image.resolve())},
    ])
    assert meta["annotations"] == 6
    with fitz.open(outputs[0]) as document:
        assert document.page_count == 2
        assert "Added" in document[0].get_text()
        spans = [span for block in document[0].get_text("dict")["blocks"] for line in block.get("lines", []) for span in line.get("spans", [])]
        assert any(span["text"] == "Added" and "Bold" in span["font"] for span in spans)
        assert document[0].get_drawings()
        assert document[1].get_images()


def test_apply_pdf_annotations_image_on_rotated_page(tmp_path):
    source = tmp_path / "rotated.pdf"
    image = make_png(tmp_path / "rotated.png")
    with fitz.open() as document:
        page = document.new_page(width=400, height=500)
        page.set_rotation(90)
        document.save(source)
    outputs, _ = run_annotations(source, tmp_path, [{"id": "image", "page": 0, "kind": "image", "x": 30, "y": 40, "w": 80, "h": 50, "path": str(image.resolve())}])
    with fitz.open(outputs[0]) as document:
        page = document[0]
        assert page.rotation == 90
        images = page.get_images(full=True)
        assert images
        rects = page.get_image_rects(images[-1][0])
        assert rects
        corners = [fitz.Point(30, 40), fitz.Point(110, 40), fitz.Point(110, 90), fitz.Point(30, 90)]
        derotated = [point * page.derotation_matrix for point in corners]
        expected = fitz.Rect(min(point.x for point in derotated), min(point.y for point in derotated), max(point.x for point in derotated), max(point.y for point in derotated))
        assert expected.contains(rects[0])


def test_apply_pdf_annotations_shapes_and_italic_text(tmp_path):
    source = make_pdf(tmp_path / "source.pdf")
    outputs, meta = run_annotations(source, tmp_path, [
        {"id": "rect-fill", "page": 0, "kind": "rect", "x": 30, "y": 180, "w": 70, "h": 35, "color": "#2563eb", "fill": "#bfdbfe", "width": 3},
        {"id": "ellipse-fill", "page": 0, "kind": "ellipse", "x": 130, "y": 180, "w": 80, "h": 40, "color": "#16a34a", "fill": "#bbf7d0", "width": 2},
        {"id": "arrow", "page": 0, "kind": "arrow", "x1": 40, "y1": 260, "x2": 180, "y2": 300, "color": "#dc2626", "width": 3},
        {"id": "italic", "page": 0, "kind": "text", "x": 40, "y": 340, "text": "Italic text", "font": "helv", "bold": False, "italic": True, "size": 14, "color": "#111827"},
        {"id": "bold-italic", "page": 0, "kind": "text", "x": 40, "y": 370, "text": "Bold italic text", "font": "tiro", "bold": True, "italic": True, "size": 14, "color": "#111827"},
    ])
    assert meta["annotations"] == 5
    with fitz.open(outputs[0]) as document:
        page = document[0]
        text = page.get_text()
        assert "Italic text" in text
        assert "Bold italic text" in text
        drawings = page.get_drawings()
        assert any(drawing.get("fill") for drawing in drawings)
        assert len(drawings) >= 3


def test_apply_pdf_annotations_old_style_payload_without_new_fields(tmp_path):
    source = make_pdf(tmp_path / "source.pdf")
    outputs, _ = run_annotations(source, tmp_path, [{"id": "old-text", "page": 0, "kind": "text", "x": 50, "y": 100, "text": "Old payload", "font": "helv", "bold": False, "size": 12, "color": "#111111"}, {"id": "old-rect", "page": 0, "kind": "rect", "x": 50, "y": 120, "w": 40, "h": 20, "color": "#111111", "width": 1}])
    with fitz.open(outputs[0]) as document:
        assert "Old payload" in document[0].get_text()
        assert document[0].get_drawings()


def test_apply_pdf_annotations_rejects_invalid_image_path(tmp_path):
    source = make_pdf(tmp_path / "source.pdf")
    with pytest.raises(EngineError) as error:
        run_annotations(source, tmp_path, [{"id": "image", "page": 0, "kind": "image", "x": 1, "y": 1, "w": 20, "h": 20, "path": str((tmp_path / "missing.png").resolve())}])
    assert error.value.code == "INVALID_TASK"


def test_apply_pdf_annotations_rejects_invalid_page(tmp_path):
    source = make_pdf(tmp_path / "source.pdf")
    with pytest.raises(EngineError) as error:
        run_annotations(source, tmp_path, [{"id": "bad", "page": 2, "kind": "text", "x": 1, "y": 1, "text": "x", "size": 10, "color": "#000000"}])
    assert error.value.code == "INVALID_TASK"
