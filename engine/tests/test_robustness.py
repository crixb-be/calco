from __future__ import annotations

import os
import threading
from pathlib import Path

import fitz
import pytest

from docforge_engine.contract import ProcessorTask
from docforge_engine.errors import EngineError
from docforge_engine.registry import EngineRegistry
from docforge_engine.rpc import dispatch


def _run(action: str, source: Path, output_dir: Path, **options):
    task = ProcessorTask(
        id=f"robust-{action}", engine="stirling_core", action=action,
        inputFiles=[str(source)], outputDir=str(output_dir), options=options,
    )
    return EngineRegistry().execute(task, lambda event: None, threading.Event())


def _make_pdf(path: Path, pages: int) -> Path:
    with fitz.open() as document:
        for index in range(pages):
            page = document.new_page()
            page.insert_text((72, 72), f"Page {index + 1}")
        document.save(path)
    return path


def test_corrupt_pdf_has_clean_errors_across_rpc_and_tasks(tmp_path):
    corrupt = tmp_path / "corrupt.pdf"
    corrupt.write_bytes(os.urandom(1024))

    for method, params in (
        ("get_pdf_pages_metadata", {"pdfPath": str(corrupt)}),
        ("get_page_thumbnails", {"pdfPath": str(corrupt), "start": 0, "count": 1}),
    ):
        with pytest.raises(EngineError) as error:
            dispatch(method, params)
        assert error.value.code in {"INVALID_TASK", "CONVERSION_FAILED"}

    for action, inputs in (("compress_pdf", [corrupt]), ("merge", [corrupt, corrupt])):
        task = ProcessorTask(
            id=f"corrupt-{action}", engine="stirling_core", action=action,
            inputFiles=[str(path) for path in inputs], outputDir=str(tmp_path / action), options={},
        )
        with pytest.raises(EngineError) as error:
            EngineRegistry().execute(task, lambda event: None, threading.Event())
        assert error.value.code in {"INVALID_TASK", "CONVERSION_FAILED"}


def test_encrypted_pdf_requires_password_for_rpc_and_stirling(tmp_path):
    plain = _make_pdf(tmp_path / "plain.pdf", 2)
    encrypted = tmp_path / "encrypted.pdf"
    with fitz.open(plain) as document:
        document.save(encrypted, encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="secret", owner_pw="owner")

    for method, params in (
        ("get_pdf_pages_metadata", {"pdfPath": str(encrypted)}),
        ("get_page_thumbnails", {"pdfPath": str(encrypted), "start": 0, "count": 1}),
    ):
        with pytest.raises(EngineError) as error:
            dispatch(method, params)
        assert error.value.code == "WRONG_PASSWORD"

    with pytest.raises(EngineError) as error:
        _run("rotate", encrypted, tmp_path / "rotate")
    assert error.value.code == "WRONG_PASSWORD"


def test_large_pdf_metadata_thumbnails_merge_and_rotate(tmp_path):
    large = _make_pdf(tmp_path / "large.pdf", 1200)

    metadata = dispatch("get_pdf_pages_metadata", {"pdfPath": str(large)})
    assert metadata["pageCount"] == 1200
    thumbnails = dispatch("get_page_thumbnails", {"pdfPath": str(large), "start": 1100, "count": 24, "maxWidth": 160})
    assert [page["index"] for page in thumbnails["pages"]] == list(range(1100, 1124))

    merged, _ = _run("merge", large, tmp_path / "merge")
    assert merged and Path(merged[0]).is_file()
    rotated, _ = _run("rotate", large, tmp_path / "rotate", pages="1200")
    with fitz.open(rotated[0]) as document:
        assert document.page_count == 1200
        assert document[-1].rotation == 90
