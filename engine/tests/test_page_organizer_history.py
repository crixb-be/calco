from __future__ import annotations

import base64
import json
import threading
from pathlib import Path

import pymupdf

from docforge_engine.contract import ProcessorTask
from docforge_engine.registry import EngineRegistry
from docforge_engine.rpc import dispatch
from docforge_engine.storage.history_manager import HistoryManager


def run_organizer(action: str, source: Path, output_dir: Path, **options):
    task = ProcessorTask(
        id=f"organizer-{action}", engine="stirling_core", action=action,
        inputFiles=[str(source)], outputDir=str(output_dir), options=options,
    )
    events = []
    return EngineRegistry().execute(task, events.append, threading.Event()), events


def test_get_pdf_thumbnails_rpc_returns_72dpi_pages(fixture_dir):
    result = dispatch("get_pdf_thumbnails", {"source_pdf": str(fixture_dir["pdf"])})
    assert result["dpi"] == 72
    assert len(result["pages"]) == 3
    first = result["pages"][0]
    assert first["page_index"] == 0 and first["page_number"] == 1 and first["rotation"] == 0
    assert base64.b64decode(first["thumbnail"].split(",", 1)[1])[:4] == b"\x89PNG"


def test_apply_page_layout_reorders_rotates_and_excludes_pages(fixture_dir):
    (outputs, meta), events = run_organizer(
        "apply_page_layout", fixture_dir["pdf"], fixture_dir["dir"],
        source_pdf=str(fixture_dir["pdf"]),
        pages=[{"page_index": 2, "rotation": 90}, {"page_index": 0, "rotation": 0}],
    )
    assert meta["pages"] == 2 and events[-1]["percent"] == 100
    with pymupdf.open(outputs[0]) as document:
        assert document.page_count == 2
        assert "Page 3" in document[0].get_text()
        assert document[0].rotation == 90


def test_history_manager_persists_and_caps_records(tmp_path):
    path = tmp_path / "data" / "history.json"
    manager = HistoryManager(path)
    for index in range(105):
        manager.record(task_id=str(index), task_type="test", source_name="a.pdf", target_path="b.pdf", status="success", duration_ms=index)
    records = HistoryManager(path).list()
    assert len(records) == 100
    assert records[0]["id"] == "5" and records[-1]["id"] == "104"
    json.loads(path.read_text(encoding="utf-8"))
