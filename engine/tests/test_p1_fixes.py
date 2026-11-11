from __future__ import annotations

import json
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from docforge_engine.__main__ import MAX_FRAME_BYTES, MAX_PENDING_RPCS, Sidecar
from docforge_engine.errors import EngineError
from docforge_engine.rpc import dispatch
from docforge_engine.storage import history_manager
from docforge_engine.storage.history_manager import HistoryManager
from docforge_engine.processors.docling_core import parse


def test_docling_parse_uses_custom_artifacts_path(fixture_dir, tmp_path, monkeypatch):
    custom = tmp_path / "custom-models"
    seen: dict[str, Path] = {}

    class FakePipeline:
        def __init__(self):
            self.artifacts_path = None
            self.do_ocr = False
            self.do_table_structure = False

    class FakeFormatOption:
        def __init__(self, pipeline_options):
            self.pipeline_options = pipeline_options

    class FakeDocument:
        pages = {}

        def export_to_markdown(self):
            return "# fake"

    class FakeResult:
        document = FakeDocument()

    class FakeConverter:
        def __init__(self, format_options=None):
            if format_options:
                option = next(iter(format_options.values()))
                seen["pipeline"] = option.pipeline_options.artifacts_path

        def convert(self, source, **kwargs):
            return FakeResult()

    class FakeInputFormat:
        PDF = "pdf"

    monkeypatch.setattr(parse, "_load_docling", lambda: (FakeConverter, FakeFormatOption, FakePipeline, FakeInputFormat))
    monkeypatch.setattr(parse.DoclingProcessor, "_ensure_models", staticmethod(lambda reporter, groups, start, end, artifacts: seen.update(models=artifacts)))

    from docforge_engine.contract import ProcessorTask

    processor_task = ProcessorTask(
        id="docling-custom", engine="docling_core", action="docling_parse",
        inputFiles=[str(fixture_dir["pdf"])], outputDir=str(tmp_path),
        options={"artifactsPath": str(custom), "exportFormats": ["md"], "tableMode": "none"},
    )
    outputs, _ = parse.DoclingProcessor().execute("docling_parse", processor_task, type("Reporter", (), {
        "report": lambda self, *args: None,
        "log": lambda self, *args: None,
        "check_cancelled": lambda self: None,
    })())
    assert Path(seen["models"]) == custom.resolve()
    assert seen["pipeline"] == str(custom.resolve())
    assert Path(outputs[0]).is_file()


def test_history_rpc_and_sidecar_share_singleton(monkeypatch, tmp_path):
    manager = HistoryManager(tmp_path / "history.json")
    monkeypatch.setattr(history_manager, "_manager", manager)
    sidecar = object.__new__(Sidecar)
    sidecar.history = history_manager.get_history_manager()
    assert sidecar.history is history_manager.get_history_manager()
    sidecar.history.record(task_id="one", task_type="test", source_name="a", target_path="b", status="success", duration_ms=1)
    assert dispatch("get_history", {})["records"][0]["id"] == "one"
    dispatch("clear_history", {})
    assert sidecar.history.list() == []


def test_encrypted_thumbnail_render_never_writes_disk_cache(tmp_path):
    import fitz

    source = tmp_path / "plain.pdf"
    with fitz.open() as document:
        document.new_page()
        document.save(source)
    encrypted = tmp_path / "encrypted.pdf"
    with fitz.open(source) as document:
        document.save(encrypted, encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="secret", owner_pw="owner")

    from docforge_engine.util.thumbnail_generator import ThumbnailService

    cache = tmp_path / "cache"
    service = ThumbnailService(cache_root=cache)
    service.image(str(encrypted), 0, password="secret")
    assert not cache.exists() or not any(cache.rglob("*"))


def test_rpc_rejects_oversized_frame_and_keeps_reading(tmp_path):
    oversized = b"{" + b"x" * MAX_FRAME_BYTES + b"}\n"
    payload = oversized + json.dumps({"type": "health"}).encode() + b"\n"
    process = subprocess.run([sys.executable, "-m", "docforge_engine", "serve"], input=payload,
                             capture_output=True, timeout=30)
    events = [json.loads(line) for line in process.stdout.splitlines() if line.strip()]
    assert any(event.get("message") == "Frame too large" for event in events)
    assert any(event.get("type") == "health" for event in events)


def test_rpc_cancel_suppresses_running_result_and_cancels_queued_work(monkeypatch):
    started = threading.Event()
    release = threading.Event()
    calls: list[str] = []

    def fake_dispatch(method, params):
        calls.append(method)
        started.set()
        release.wait(5)
        return {"method": method}

    monkeypatch.setattr("docforge_engine.rpc.dispatch", fake_dispatch)
    sidecar = object.__new__(Sidecar)
    sidecar.rpc_pool = ThreadPoolExecutor(max_workers=1)
    sidecar.rpc_lock = threading.Lock()
    sidecar.pending_rpcs = {}
    sidecar.running_rpcs = set()
    sidecar.cancelled_rpcs = set()
    emitted: list[dict] = []
    sidecar.emit = emitted.append
    try:
        sidecar.submit_rpc("running", "slow", {})
        assert started.wait(2)
        sidecar.submit_rpc("queued", "queued", {})
        sidecar.cancel_rpc("queued")
        assert emitted[-1]["error"]["code"] == "CANCELLED"
        sidecar.cancel_rpc("running")
        release.set()
        sidecar.rpc_pool.shutdown(wait=True)
        assert not any(event.get("rpcId") == "running" and event.get("ok") is True for event in emitted)
        assert calls == ["slow"]
    finally:
        release.set()
        sidecar.rpc_pool.shutdown(wait=True)


def test_rpc_queue_replies_busy_after_64_pending(monkeypatch):
    release = threading.Event()

    def fake_dispatch(method, params):
        release.wait(5)
        return {}

    monkeypatch.setattr("docforge_engine.rpc.dispatch", fake_dispatch)
    sidecar = object.__new__(Sidecar)
    sidecar.rpc_pool = ThreadPoolExecutor(max_workers=1)
    sidecar.rpc_lock = threading.Lock()
    sidecar.pending_rpcs = {}
    sidecar.running_rpcs = set()
    sidecar.cancelled_rpcs = set()
    emitted: list[dict] = []
    sidecar.emit = emitted.append
    try:
        for index in range(MAX_PENDING_RPCS):
            sidecar.submit_rpc(str(index), "slow", {})
        sidecar.submit_rpc("busy", "slow", {})
        assert emitted[-1]["rpcId"] == "busy"
        assert emitted[-1]["error"]["code"] == "BUSY"
    finally:
        release.set()
        sidecar.rpc_pool.shutdown(wait=True)


def test_rpc_file_policy_caps_reads_and_export_extensions(tmp_path):
    source = tmp_path / "large.md"
    with source.open("wb") as handle:
        handle.seek(50 * 1024 * 1024)
        handle.write(b"x")
    with pytest.raises(EngineError) as too_large:
        dispatch("read_text_file", {"path": str(source), "maxBytes": 100 * 1024 * 1024})
    assert too_large.value.code == "INVALID_TASK"

    bad_source = tmp_path / "source.bin"
    bad_source.write_bytes(b"x")
    with pytest.raises(EngineError) as bad_extension:
        dispatch("export_file", {"sourcePath": str(bad_source), "targetPath": str(tmp_path / "copy.bin")})
    assert bad_extension.value.code == "INVALID_TASK"

    with pytest.raises(EngineError) as mismatch:
        dispatch("export_file", {"sourcePath": str(source), "targetPath": str(tmp_path / "copy.txt")})
    assert mismatch.value.code == "INVALID_TASK"

    engine_target = Path(__file__).resolve().parents[1] / "blocked.md"
    with pytest.raises(EngineError) as forbidden:
        dispatch("export_file", {"sourcePath": str(source), "targetPath": str(engine_target)})
    assert forbidden.value.code == "INVALID_TASK"
