from __future__ import annotations

import threading
from pathlib import Path

import fitz
import pytest

from docforge_engine.contract import ProcessorTask
from docforge_engine.processors.docling_core.parse import html_to_markdown
from docforge_engine.registry import EngineRegistry


def run_markdown(source: Path, output_dir: Path):
    task = ProcessorTask(id="markdown", engine="docling_core", action="to_markdown", inputFiles=[str(source)], outputDir=str(output_dir), options={})
    return EngineRegistry().execute(task, lambda event: None, threading.Event())


def test_txt_to_markdown(tmp_path):
    source = tmp_path / "notes.txt"
    source.write_bytes(b"line 1\r\nline 2\rline 3")
    outputs, _ = run_markdown(source, tmp_path)
    assert Path(outputs[0]).read_text(encoding="utf-8") == "line 1\nline 2\nline 3"


def test_html_fallback_converter():
    markdown = html_to_markdown("<style>x{}</style><h1>Título</h1><p>Hola <strong>mundo</strong>.</p><ul><li>Uno</li></ul><table><tr><th>A</th><th>B</th></tr><tr><td>1</td><td>2</td></tr></table>")
    assert "# Título" in markdown
    assert "Hola **mundo**." in markdown
    assert "| A | B |" in markdown and "| 1 | 2 |" in markdown
    assert "x{}" not in markdown


def test_pdf_to_markdown(tmp_path):
    pytest.importorskip("pymupdf4llm")
    source = tmp_path / "tiny.pdf"
    with fitz.open() as document:
        page = document.new_page()
        page.insert_text((72, 72), "Tiny PDF")
        document.save(source)
    outputs, _ = run_markdown(source, tmp_path)
    assert "Tiny PDF" in Path(outputs[0]).read_text(encoding="utf-8")


def test_markdown_output_uses_plain_name(tmp_path):
    source = tmp_path / "informe.txt"
    source.write_text("hola", encoding="utf-8")
    first, _ = run_markdown(source, tmp_path / "out")
    second, _ = run_markdown(source, tmp_path / "out")
    assert Path(first[0]).name == "informe.md"
    assert Path(second[0]).name == "informe_2.md"
