from __future__ import annotations

import threading
from pathlib import Path

import pymupdf
import pytest

from docforge_engine.contract import ProcessorTask
from docforge_engine.errors import EngineError
from docforge_engine.registry import EngineRegistry


def execute(action: str, source: Path, output_dir: Path, **options):
    task = ProcessorTask(
        id=f"test-{action}",
        engine="stirling_core" if action in {"protect_pdf", "unlock_pdf"} else "docling_core",
        action=action,
        inputFiles=[str(source)],
        outputDir=str(output_dir),
        options=options,
    )
    return EngineRegistry().execute(task, lambda _: None, threading.Event())


def test_protect_pdf_and_unlock_pdf_use_pymupdf(fixture_dir):
    protected, meta = execute("protect_pdf", fixture_dir["pdf"], fixture_dir["dir"], userPassword="user", ownerPassword="owner")
    assert meta["encryption"] == "AES-256"
    with pymupdf.open(protected[0]) as document:
        assert document.needs_pass
        assert document.authenticate("user") > 0

    unlocked, unlock_meta = execute("unlock_pdf", Path(protected[0]), fixture_dir["dir"], password="user")
    assert unlock_meta["encrypted"] is False
    with pymupdf.open(unlocked[0]) as document:
        assert not document.needs_pass
        assert document.page_count == 3


def test_unlock_pdf_reports_wrong_password(fixture_dir):
    protected, _ = execute("protect_pdf", fixture_dir["pdf"], fixture_dir["dir"], userPassword="correct")
    with pytest.raises(EngineError) as error:
        execute("unlock_pdf", Path(protected[0]), fixture_dir["dir"], password="wrong")
    assert error.value.code == "WRONG_PASSWORD"


def test_security_reports_corrupt_pdf(tmp_path):
    source = tmp_path / "corrupt.pdf"
    source.write_bytes(b"not a PDF")
    with pytest.raises(EngineError) as error:
        execute("protect_pdf", source, tmp_path, userPassword="secret")
    assert error.value.code == "CONVERSION_FAILED"


def test_docling_parser_accepts_only_pdf_or_images(tmp_path):
    source = tmp_path / "notes.txt"
    source.write_text("not a document", encoding="utf-8")
    with pytest.raises(EngineError) as error:
        execute("docling_parse", source, tmp_path, exportFormats=["md"])
    assert error.value.code == "INVALID_TASK"
