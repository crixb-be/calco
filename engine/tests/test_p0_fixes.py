from __future__ import annotations

import subprocess
import threading
from pathlib import Path

import fitz
import pytest

from docforge_engine.contract import ProcessorTask
from docforge_engine.errors import EngineError
from docforge_engine.processors.ffmpeg_bridge import ffmpeg
from docforge_engine.rpc import dispatch
from docforge_engine.util.paths import output_path, release_output_path
from docforge_engine.util.soffice_runner import convert_with_soffice
from docforge_engine.util.thumbnail_generator import ThumbnailService


def make_pdf(path: Path, pages: int) -> Path:
    document = fitz.open()
    for index in range(pages):
        page = document.new_page()
        page.insert_text((72, 100), f"Page {index + 1}")
    document.save(path)
    document.close()
    return path


def test_legacy_page_thumbnails_reject_large_pdf(tmp_path):
    pdf = make_pdf(tmp_path / "large.pdf", 51)
    with pytest.raises(EngineError) as error:
        dispatch("get_pdf_thumbnails", {"source_pdf": str(pdf)})
    assert error.value.code == "INVALID_TASK"
    assert "50" in error.value.message


def test_ffmpeg_cancellation_terminates_process_and_releases_output(tmp_path, monkeypatch):
    source = tmp_path / "input.mov"
    source.write_bytes(b"input")
    task = ProcessorTask(id="ffmpeg-cancel", engine="ffmpeg_bridge", action="convert",
                         inputFiles=[str(source)], outputDir=str(tmp_path), options={})

    class FakeProcess:
        pid = 1234

        def poll(self):
            return None

    killed = []
    monkeypatch.setattr(ffmpeg, "locate_binary", lambda *_: "ffmpeg")
    monkeypatch.setattr(ffmpeg.subprocess, "Popen", lambda *args, **kwargs: FakeProcess())
    monkeypatch.setattr(ffmpeg, "_kill_process_tree", lambda process: killed.append(process))

    class CancelledReporter:
        def check_cancelled(self):
            raise EngineError("CANCELLED", "cancelled")

    with pytest.raises(EngineError) as error:
        ffmpeg.FfmpegProcessor()._run(task, source, "mp4", [], CancelledReporter())
    assert error.value.code == "CANCELLED"
    assert killed
    assert not list(tmp_path.glob("input_convert*"))


def test_soffice_captures_output_to_files_not_pipes(tmp_path, monkeypatch):
    source = tmp_path / "input.docx"
    source.write_bytes(b"docx")
    captured = {}

    class Completed:
        pid = 5678
        returncode = 0

        def poll(self):
            return 0

    def fake_popen(command, **kwargs):
        captured.update(kwargs)
        out_dir = Path(command[command.index("--outdir") + 1])
        (out_dir / "input.pdf").write_bytes(b"%PDF-1.4 fake")
        kwargs["stdout"].write(b"stdout text\n")
        kwargs["stderr"].write(b"stderr text\n")
        return Completed()

    monkeypatch.setattr("docforge_engine.util.soffice_runner.subprocess.Popen", fake_popen)
    result = convert_with_soffice("soffice", source, tmp_path / "out", "pdf")
    assert result.is_file()
    assert captured["stdout"] is not subprocess.PIPE
    assert captured["stderr"] is not subprocess.PIPE


def test_output_path_reserves_names_across_threads(tmp_path):
    task = ProcessorTask(id="names", engine="stirling_core", action="x", inputFiles=[], outputDir=str(tmp_path), options={})
    paths: list[Path] = []
    lock = threading.Lock()

    def reserve():
        path = output_path(task, "same", "convert", ".pdf")
        with lock:
            paths.append(path)

    threads = [threading.Thread(target=reserve) for _ in range(40)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    try:
        assert len(paths) == 40
        assert len({path.resolve() for path in paths}) == 40
        assert all(path.is_file() for path in paths)
    finally:
        for path in paths:
            release_output_path(path)


def test_encrypted_thumbnail_cache_requires_password_each_time(tmp_path):
    source = make_pdf(tmp_path / "plain.pdf", 1)
    protected = tmp_path / "protected.pdf"
    with fitz.open(source) as document:
        document.save(protected, encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="secret", owner_pw="owner")

    service = ThumbnailService(cache_root=tmp_path / "thumbs")
    service.image(str(protected), 0, password="secret")
    with pytest.raises(EngineError) as error:
        service.image(str(protected), 0)
    assert error.value.code == "WRONG_PASSWORD"

    fresh_service = ThumbnailService(cache_root=tmp_path / "thumbs")
    with pytest.raises(EngineError) as fresh_error:
        fresh_service.image(str(protected), 0)
    assert fresh_error.value.code == "WRONG_PASSWORD"


def test_failed_task_leaves_no_empty_placeholder(tmp_path):
    import threading

    import fitz

    from docforge_engine.contract import parse_task
    from docforge_engine.errors import EngineError
    from docforge_engine.registry import EngineRegistry

    source = tmp_path / "in.pdf"
    document = fitz.open()
    document.new_page()
    document.save(source)
    document.close()
    out_dir = tmp_path / "out"
    cancel = threading.Event()
    cancel.set()  # cancelled after output_path() reserved the name, before saving
    task = parse_task({"id": "t", "engine": "stirling_core", "action": "compress_pdf",
                       "inputFiles": [str(source)], "outputDir": str(out_dir), "options": {}})
    try:
        EngineRegistry().execute(task, lambda event: None, cancel)
    except EngineError as exc:
        assert exc.code == "CANCELLED"
    else:
        raise AssertionError("task should have been cancelled")
    assert list(out_dir.iterdir()) == []
