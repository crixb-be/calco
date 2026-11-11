from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import fitz
import openpyxl
import pytest

from docforge_engine.contract import ProcessorTask
from docforge_engine.errors import EngineError
from docforge_engine.registry import EngineRegistry


def run_action(registry, engine, action, inputs, output_dir, **options):
    task = ProcessorTask(id=f"{engine}-{action}", engine=engine, action=action, inputFiles=[str(p) for p in inputs], outputDir=str(output_dir), options=options)
    events = []
    outputs, meta = registry.execute(task, events.append, __import__("threading").Event())
    return [Path(p) for p in outputs], meta, events


def test_organize_edit_and_convert_actions(fixture_dir):
    r = EngineRegistry()
    pdf = fixture_dir["pdf"]
    out, _, _ = run_action(r, "stirling_core", "merge", [pdf, pdf], fixture_dir["dir"])
    assert len(out) == 1 and len(fitz.open(out[0])) == 6
    split, _, _ = run_action(r, "stirling_core", "split", [pdf], fixture_dir["dir"], mode="single", pages="1,3")
    assert len(split) == 2
    rotated, _, _ = run_action(r, "stirling_core", "rotate", [pdf], fixture_dir["dir"], angle=90, pages="1")
    assert fitz.open(rotated[0])[0].rotation == 90
    cropped, _, _ = run_action(r, "stirling_core", "crop", [pdf], fixture_dir["dir"], margins={"left": 10, "top": 10, "right": 10, "bottom": 10})
    assert fitz.open(cropped[0])[0].rect.width == 592
    deleted, _, _ = run_action(r, "stirling_core", "delete_pages", [pdf], fixture_dir["dir"], pages="2")
    assert len(fitz.open(deleted[0])) == 2
    nup, _, _ = run_action(r, "stirling_core", "nup", [pdf], fixture_dir["dir"], perSheet=2)
    assert len(fitz.open(nup[0])) == 2
    redacted, _, _ = run_action(r, "stirling_core", "redact", [pdf], fixture_dir["dir"], terms=["secret@example.com"])
    assert "secret@example.com" not in "".join(page.get_text() for page in fitz.open(redacted[0]))
    numbered, _, _ = run_action(r, "stirling_core", "page_numbers", [pdf], fixture_dir["dir"], format="{n}/{total}")
    assert "1/3" in fitz.open(numbered[0])[0].get_text()
    watermarked, _, _ = run_action(r, "stirling_core", "watermark", [pdf], fixture_dir["dir"], text="DRAFT", opacity=0.2)
    assert watermarked[0].exists()
    flattened, _, _ = run_action(r, "stirling_core", "flatten", [pdf], fixture_dir["dir"])
    assert flattened[0].exists()


def test_security_actions_and_wrong_password(fixture_dir):
    r = EngineRegistry()
    pdf = fixture_dir["pdf"]
    sanitized, _, _ = run_action(r, "stirling_core", "sanitize", [pdf], fixture_dir["dir"], removeMetadata=True, removeLinks=True, removeJs=True, removeAttachments=True, removeXmp=True)
    assert sanitized[0].exists()
    protected, _, _ = run_action(r, "stirling_core", "protect", [pdf], fixture_dir["dir"], userPassword="secret", ownerPassword="owner")
    with pytest.raises(EngineError) as error:
        run_action(r, "stirling_core", "unprotect", protected, fixture_dir["dir"], password="wrong")
    assert error.value.code == "WRONG_PASSWORD"
    unprotected, _, _ = run_action(r, "stirling_core", "unprotect", protected, fixture_dir["dir"], password="secret")
    assert not fitz.open(unprotected[0]).needs_pass


def test_conversion_actions(fixture_dir):
    r = EngineRegistry()
    pdf = fixture_dir["pdf"]
    images, _, _ = run_action(r, "stirling_core", "pdf_to_images", [pdf], fixture_dir["dir"], dpi=72, format="png", pages="1-2")
    assert len(images) == 2
    extracted, _, _ = run_action(r, "stirling_core", "extract_images", [pdf], fixture_dir["dir"], minSize=1)
    assert extracted
    image_pdf, _, _ = run_action(r, "stirling_core", "images_to_pdf", images, fixture_dir["dir"], pageSize="A4", margin=10)
    assert len(fitz.open(image_pdf[0])) == 2
    html, _, _ = run_action(r, "stirling_core", "pdf_to_html", [pdf], fixture_dir["dir"])
    assert "Page 1" in html[0].read_text(encoding="utf-8")
    xlsx, _, _ = run_action(r, "office_bridge", "pdf_to_xlsx", [pdf], fixture_dir["dir"])
    assert openpyxl.load_workbook(xlsx[0]).worksheets


def test_nondestructive_naming_and_bridge_errors(fixture_dir, monkeypatch):
    r = EngineRegistry()
    pdf = fixture_dir["pdf"]
    first, _, _ = run_action(r, "stirling_core", "pdf_to_html", [pdf], fixture_dir["dir"])
    second, _, _ = run_action(r, "stirling_core", "pdf_to_html", [pdf], fixture_dir["dir"])
    assert first[0] != second[0]
    monkeypatch.setattr("docforge_engine.processors.office_bridge.soffice.locate_binary", lambda *_: None)
    with pytest.raises(EngineError) as office_error:
        run_action(r, "office_bridge", "office_to_pdf", [pdf], fixture_dir["dir"])
    assert office_error.value.code == "BINARY_NOT_FOUND"
    monkeypatch.setattr("docforge_engine.processors.ffmpeg_bridge.ffmpeg.locate_binary", lambda *_: None)
    with pytest.raises(EngineError) as ffmpeg_error:
        run_action(r, "ffmpeg_bridge", "convert", [pdf], fixture_dir["dir"], container="mp4")
    assert ffmpeg_error.value.code == "BINARY_NOT_FOUND"


def test_docling_dependency_error(fixture_dir, monkeypatch):
    from docforge_engine.processors.docling_core import parse

    def missing():
        raise EngineError("DEPENDENCY_MISSING", "Docling missing")

    monkeypatch.setattr(parse, "_load_docling", missing)
    with pytest.raises(EngineError) as error:
        run_action(EngineRegistry(), "docling_core", "docling_parse", [fixture_dir["pdf"]], fixture_dir["dir"])
    assert error.value.code == "DEPENDENCY_MISSING"


def test_ndjson_serve_round_trip(fixture_dir):
    task = {"id": "health-1", "engine": "stirling_core", "action": "pdf_to_html", "inputFiles": [str(fixture_dir["pdf"])], "outputDir": str(fixture_dir["dir"])}
    process = subprocess.Popen([sys.executable, "-m", "docforge_engine", "serve"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    assert process.stdin and process.stdout
    process.stdin.write(json.dumps({"type": "health"}) + "\n")
    process.stdin.write(json.dumps(task) + "\n")
    process.stdin.close()
    lines = [json.loads(line) for line in process.stdout if line.strip()]
    process.wait(timeout=30)
    assert any(line.get("type") == "health" for line in lines)
    assert any(line.get("type") == "result" and line.get("id") == "health-1" for line in lines)
