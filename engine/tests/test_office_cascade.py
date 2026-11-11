from __future__ import annotations

import threading
import subprocess
import sys
from pathlib import Path

import pytest

from docforge_engine.contract import ProcessorTask
from docforge_engine.errors import EngineError
from docforge_engine.util import binaries, office_engines
from docforge_engine.util.office_com import OfficeComError


class Reporter:
    def __init__(self):
        self.cancel = threading.Event()
        self.logs = []
        self.progress = []

    def log(self, message, level="info"):
        self.logs.append((level, message))

    def report(self, percent, message=None):
        self.progress.append((percent, message))

    def check_cancelled(self):
        if self.cancel.is_set():
            raise EngineError("CANCELLED", "cancelled")


def _task(source: Path, output: Path, **options):
    return ProcessorTask(
        id="office-cascade", engine="office_bridge", action="office_to_pdf",
        inputFiles=[str(source)], outputDir=str(output), options=options,
    )


def test_auto_prefers_com_and_reports_engine(tmp_path, monkeypatch):
    source, output = tmp_path / "Informe.docx", tmp_path / "out"
    source.write_bytes(b"docx")
    calls = []

    monkeypatch.setattr(office_engines, "com_available", lambda kind: True)
    monkeypatch.setattr(office_engines, "locate_binary", lambda *_: None)

    def fake_com(kind, input_file, output_dir, **kwargs):
        calls.append(("com", kind))
        result = Path(output_dir) / "input.pdf"
        result.write_bytes(b"%PDF COM")
        return result

    monkeypatch.setattr(office_engines, "convert_with_office_com", fake_com)
    outputs, metadata = office_engines.convert_office_to_pdf(_task(source, output), Reporter())
    assert Path(outputs[0]).is_file()
    assert metadata["engine"] == "msword"
    assert calls == [("com", "msword")]


def test_auto_falls_back_to_libreoffice_after_com_failure(tmp_path, monkeypatch):
    source, output = tmp_path / "Informe.docx", tmp_path / "out"
    source.write_bytes(b"docx")
    reporter = Reporter()
    calls = []
    monkeypatch.setattr(office_engines, "com_available", lambda kind: True)
    monkeypatch.setattr(office_engines, "locate_binary", lambda *_: "soffice.exe")
    monkeypatch.setattr(office_engines, "convert_with_office_com", lambda *args, **kwargs: (_ for _ in ()).throw(OfficeComError("protected")))

    def fake_soffice(binary, input_file, output_dir, convert_to, **kwargs):
        calls.append(binary)
        result = Path(output_dir) / "input.pdf"
        result.write_bytes(b"%PDF LO")
        return result

    monkeypatch.setattr(office_engines, "convert_with_soffice", fake_soffice)
    outputs, metadata = office_engines.convert_office_to_pdf(_task(source, output), reporter)
    assert Path(outputs[0]).read_bytes() == b"%PDF LO"
    assert metadata["engine"] == "libreoffice"
    assert calls == ["soffice.exe"]
    assert any(level == "warn" for level, _ in reporter.logs)


def test_explicit_engines_do_not_cross_fallback_boundary(tmp_path, monkeypatch):
    source, output = tmp_path / "Libro.xlsx", tmp_path / "out"
    source.write_bytes(b"xlsx")
    monkeypatch.setattr(office_engines, "com_available", lambda kind: True)
    monkeypatch.setattr(office_engines, "locate_binary", lambda *_: "soffice.exe")
    monkeypatch.setattr(office_engines, "convert_with_office_com", lambda *args, **kwargs: (_ for _ in ()).throw(OfficeComError("failed")))
    with pytest.raises(EngineError) as error:
        office_engines.convert_office_to_pdf(_task(source, output, officeEngine="msoffice"), Reporter())
    assert error.value.code == "CONVERSION_FAILED"

    com_called = []
    monkeypatch.setattr(office_engines, "convert_with_office_com", lambda *args, **kwargs: com_called.append(True))
    monkeypatch.setattr(office_engines, "convert_with_soffice", lambda binary, input_file, output_dir, convert_to, **kwargs: _write_pdf(output_dir))
    outputs, metadata = office_engines.convert_office_to_pdf(_task(source, output, officeEngine="libreoffice"), Reporter())
    assert Path(outputs[0]).is_file() and metadata["engine"] == "libreoffice"
    assert not com_called


def _write_pdf(directory):
    result = Path(directory) / "input.pdf"
    result.write_bytes(b"%PDF")
    return result


def test_no_engine_error_contains_install_choices(tmp_path, monkeypatch):
    source, output = tmp_path / "Informe.docx", tmp_path / "out"
    source.write_bytes(b"docx")
    monkeypatch.setattr(office_engines, "com_available", lambda kind: False)
    monkeypatch.setattr(office_engines, "locate_binary", lambda *_: None)
    with pytest.raises(EngineError) as error:
        office_engines.convert_office_to_pdf(_task(source, output), Reporter())
    assert error.value.code == "BINARY_NOT_FOUND"
    assert "Microsoft Office" in (error.value.details or "")
    assert "libreoffice.org/download" in (error.value.details or "")
    assert "pdf2docx" in (error.value.details or "")


def test_candidate_list_includes_user_portable_and_scoop_paths(monkeypatch, tmp_path):
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "User"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    candidates = [str(path).lower() for path in binaries._candidates("soffice")]
    assert any("libreofficeportable" in path for path in candidates)
    assert any("scoop" in path and "libreoffice" in path for path in candidates)


def test_ffmpeg_popen_combines_no_window_and_process_group_flags(tmp_path, monkeypatch):
    from docforge_engine.processors.ffmpeg_bridge import ffmpeg

    source = tmp_path / "input.mov"
    source.write_bytes(b"input")
    task = ProcessorTask(
        id="ffmpeg-flags", engine="ffmpeg_bridge", action="convert",
        inputFiles=[str(source)], outputDir=str(tmp_path), options={},
    )
    captured = {}

    class Completed:
        pid = 123
        returncode = 0

        def poll(self):
            return 0

    def fake_popen(command, **kwargs):
        captured.update(kwargs)
        Path(command[-1]).write_bytes(b"video")
        return Completed()

    monkeypatch.setattr(ffmpeg, "locate_binary", lambda *_: "ffmpeg.exe")
    monkeypatch.setattr(ffmpeg.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(sys, "platform", "win32")
    ffmpeg.FfmpegProcessor()._run(task, source, "mp4", [], Reporter())
    assert captured["creationflags"] & getattr(subprocess, "CREATE_NO_WINDOW", 0)
    assert captured["creationflags"] & getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
