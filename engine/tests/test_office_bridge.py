"""Office bridge robustness tests using a fake soffice (LibreOffice need not be installed)."""
from __future__ import annotations

import sys
import textwrap
import threading
import time
from pathlib import Path

import pytest

from docforge_engine.contract import ProcessorTask
from docforge_engine.errors import EngineError
from docforge_engine.registry import EngineRegistry
from docforge_engine.util.binaries import locate_binary
from docforge_engine.util.soffice_runner import convert_with_soffice

FAKE_SOFFICE = textwrap.dedent(
    r'''
    import os, subprocess, sys, time
    from pathlib import Path
    args = sys.argv[1:]
    mode = os.environ.get("FAKE_SOFFICE_MODE", "ok")
    log = os.environ.get("FAKE_SOFFICE_ARGS")
    if log:
        Path(log).write_text("\n".join(args), encoding="utf-8")
    outdir = Path(args[args.index("--outdir") + 1])
    ext = args[args.index("--convert-to") + 1].split(":")[0]
    src = Path(args[-1])
    if mode == "ok":
        (outdir / f"{src.stem}.{ext}").write_bytes(b"%PDF-1.4 fake")
    elif mode == "fail":
        sys.stderr.write("Error: source file could not be loaded\n"); sys.exit(1)
    elif mode == "nooutput":
        sys.exit(0)
    elif mode == "hang":
        # Grandchild inherits stdout/stderr, like soffice.exe -> soffice.bin on Windows.
        subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
        time.sleep(120)
    '''
)


@pytest.fixture()
def fake_soffice(tmp_path: Path) -> str:
    folder = tmp_path / "Program Files" / "Libre Office" / "program"
    folder.mkdir(parents=True)
    script = folder / "fake_soffice.py"
    script.write_text(FAKE_SOFFICE, encoding="utf-8")
    if sys.platform == "win32":
        launcher = folder / "soffice.cmd"
        launcher.write_text(f'@"{sys.executable}" "{script}" %*\r\n', encoding="utf-8")
    else:
        launcher = folder / "soffice"
        launcher.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n', encoding="utf-8")
        launcher.chmod(0o755)
    return str(launcher)


@pytest.fixture()
def spaced(tmp_path: Path):
    src_dir = tmp_path / "Mis Documentos" / "informe final"
    out_dir = tmp_path / "Salida PDF" / "carpeta con espacios"
    src_dir.mkdir(parents=True)
    out_dir.mkdir(parents=True)
    src = src_dir / "Reporte trimestral (v2).docx"
    src.write_bytes(b"fake docx")
    return src, out_dir


def test_converts_with_spaces_in_paths(fake_soffice, spaced, monkeypatch, tmp_path):
    src, out_dir = spaced
    args_log = tmp_path / "args.txt"
    monkeypatch.setenv("FAKE_SOFFICE_MODE", "ok")
    monkeypatch.setenv("FAKE_SOFFICE_ARGS", str(args_log))
    result = convert_with_soffice(fake_soffice, src, out_dir, "pdf", timeout_sec=30)
    assert result == out_dir / "Reporte trimestral (v2).pdf" and result.is_file()
    args = args_log.read_text(encoding="utf-8").splitlines()
    # LibreOffice only ever sees a neutral ASCII copy of the input and a neutral outdir.
    neutral_in, neutral_out = args[-1], args[args.index("--outdir") + 1]
    assert Path(neutral_in).name == "input.docx"
    assert neutral_in.isascii() and neutral_out.isascii()
    assert "--headless" in args and "--norestore" in args
    assert any(a.startswith("-env:UserInstallation=file:///") for a in args)


def test_accented_paths_and_step_logs(fake_soffice, tmp_path, monkeypatch):
    src_dir = tmp_path / "MAESTRÍA GESTIÓN" / "Año 2026"
    out_dir = tmp_path / "Salida — Ñandú"
    src_dir.mkdir(parents=True)
    src = src_dir / "Tesis Maestría – capítulo 1.docx"
    src.write_bytes(b"fake docx")
    monkeypatch.setenv("FAKE_SOFFICE_MODE", "ok")
    logs = []
    result = convert_with_soffice(fake_soffice, src, out_dir, "pdf", timeout_sec=30, log=lambda m, l: logs.append(m))
    assert result == out_dir / "Tesis Maestría – capítulo 1.pdf" and result.is_file()
    text = "\n".join(logs)
    for step in ("Comando:", "PID lanzado:", "Proceso terminado: código de retorno 0", "Resultado movido a:"):
        assert step in text


def test_timeout_does_not_hang_with_grandchild_holding_pipes(fake_soffice, spaced, monkeypatch):
    src, out_dir = spaced
    monkeypatch.setenv("FAKE_SOFFICE_MODE", "hang")
    started = time.monotonic()
    with pytest.raises(EngineError) as error:
        convert_with_soffice(fake_soffice, src, out_dir, "pdf", timeout_sec=2)
    assert error.value.code == "TIMEOUT"
    assert "2s" in error.value.message
    assert time.monotonic() - started < 20


def test_missing_output_is_reported(fake_soffice, spaced, monkeypatch):
    src, out_dir = spaced
    monkeypatch.setenv("FAKE_SOFFICE_MODE", "nooutput")
    with pytest.raises(EngineError) as error:
        convert_with_soffice(fake_soffice, src, out_dir, "pdf", timeout_sec=30)
    assert error.value.code == "CONVERSION_FAILED"
    assert "no generó" in error.value.message


def test_nonzero_exit_includes_stderr(fake_soffice, spaced, monkeypatch):
    src, out_dir = spaced
    monkeypatch.setenv("FAKE_SOFFICE_MODE", "fail")
    with pytest.raises(EngineError) as error:
        convert_with_soffice(fake_soffice, src, out_dir, "pdf", timeout_sec=30)
    assert error.value.code == "CONVERSION_FAILED"
    assert "could not be loaded" in (error.value.details or "")


def test_cancel_kills_conversion(fake_soffice, spaced, monkeypatch):
    src, out_dir = spaced
    monkeypatch.setenv("FAKE_SOFFICE_MODE", "hang")
    cancel = threading.Event()
    threading.Timer(1.0, cancel.set).start()
    started = time.monotonic()
    with pytest.raises(EngineError) as error:
        convert_with_soffice(fake_soffice, src, out_dir, "pdf", timeout_sec=60, is_cancelled=cancel.is_set)
    assert error.value.code == "CANCELLED"
    assert time.monotonic() - started < 20


def test_office_to_pdf_action_reports_progress(fake_soffice, spaced, monkeypatch):
    src, out_dir = spaced
    monkeypatch.setenv("FAKE_SOFFICE_MODE", "ok")
    task = ProcessorTask(id="o2p", engine="office_bridge", action="office_to_pdf", inputFiles=[str(src)],
                         outputDir=str(out_dir), options={"binaryPath": f'"{fake_soffice}"'})
    events = []
    outputs, _ = EngineRegistry().execute(task, events.append, threading.Event())
    assert Path(outputs[0]).is_file() and Path(outputs[0]).parent == out_dir
    percents = [e["percent"] for e in events if e.get("type") == "progress"]
    assert percents and percents[0] > 0 and percents[-1] == 100
    assert not [p for p in out_dir.iterdir() if p.name.startswith(".docforge-")]  # temp dir cleaned


def test_office_error_event_is_descriptive_json(fake_soffice, spaced, monkeypatch):
    import json
    import subprocess

    src, out_dir = spaced
    task = {"id": "t-err", "engine": "office_bridge", "action": "office_to_pdf", "inputFiles": [str(src)],
            "outputDir": str(out_dir), "options": {"binaryPath": fake_soffice}}
    env = dict(__import__("os").environ, FAKE_SOFFICE_MODE="nooutput")
    proc = subprocess.run([sys.executable, "-m", "docforge_engine", "serve"], input=json.dumps(task) + "\n",
                          capture_output=True, text=True, timeout=60, env=env)
    events = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
    error = next(e for e in events if e.get("type") == "error")
    assert error["id"] == "t-err" and error["code"] == "CONVERSION_FAILED"
    assert "no generó" in error["message"] and "exit code: 0" in error["details"]


def test_locate_binary_accepts_quoted_path_and_directory(fake_soffice, monkeypatch):
    monkeypatch.delenv("DOCFORGE_SOFFICE", raising=False)
    assert locate_binary("soffice", {"binaryPath": f'  "{fake_soffice}" '}) == fake_soffice


def test_locate_binary_falls_back_to_program_files(tmp_path, monkeypatch):
    if sys.platform != "win32":
        pytest.skip("Windows install layout")
    exe = tmp_path / "PF" / "LibreOffice" / "program" / "soffice.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"")
    monkeypatch.setenv("ProgramFiles", str(tmp_path / "PF"))
    monkeypatch.delenv("DOCFORGE_SOFFICE", raising=False)
    monkeypatch.setattr("shutil.which", lambda *_: None)
    assert locate_binary("soffice", {"binaryPath": ""}) == str(exe)
    # A directory pointing at the install root also resolves.
    assert locate_binary("soffice", {"binaryPath": str(tmp_path / "PF" / "LibreOffice")}) == str(exe)


def test_serve_channel_survives_accents_without_utf8_env(fake_soffice, tmp_path):
    """Regression: Windows pipes default to cp1252. Send raw UTF-8 like Tauri does, with no
    PYTHONUTF8 in the environment, and require every stdout line to be valid UTF-8 JSON."""
    import json
    import os
    import subprocess

    src_dir = tmp_path / "MAESTRÍA GESTIÓN"
    src_dir.mkdir()
    src = src_dir / "Informe Gestión.docx"
    src.write_bytes(b"fake docx")
    out_dir = tmp_path / "Salida Ñ"
    task = {"id": "t-utf8", "engine": "office_bridge", "action": "office_to_pdf", "inputFiles": [str(src)],
            "outputDir": str(out_dir), "options": {"binaryPath": fake_soffice}}
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONUTF8", "PYTHONIOENCODING")}
    env["FAKE_SOFFICE_MODE"] = "ok"
    proc = subprocess.run([sys.executable, "-m", "docforge_engine", "serve"],
                          input=(json.dumps(task, ensure_ascii=False) + "\n").encode("utf-8"),
                          capture_output=True, timeout=60, env=env)
    events = [json.loads(line.decode("utf-8")) for line in proc.stdout.splitlines() if line.strip()]
    result = next(e for e in events if e.get("type") in ("result", "error"))
    assert result["type"] == "result", result
    out = Path(result["outputFiles"][0])
    assert out.is_file() and out.parent == out_dir and "Gestión" in out.name
    assert any(e.get("type") == "log" and "PID lanzado" in e["message"] for e in events)
    assert all(line.isascii() for line in proc.stdout.splitlines())


@pytest.mark.skipif(locate_binary("soffice", {}) is None, reason="LibreOffice not installed")
def test_real_libreoffice_docx_to_pdf_with_accents(tmp_path):
    import zipfile

    import fitz

    src_dir = tmp_path / "MAESTRÍA GESTIÓN"
    src_dir.mkdir()
    src = src_dir / "Tesis Maestría.docx"
    body = "Gestión de la Maestría — ñ á é í ó ú"
    parts = {
        "[Content_Types].xml": '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>',
        "_rels/.rels": '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>',
        "word/document.xml": f'<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>{body}</w:t></w:r></w:p></w:body></w:document>',
    }
    with zipfile.ZipFile(src, "w") as archive:
        for name, xml in parts.items():
            archive.writestr(name, xml.encode("utf-8"))
    task = ProcessorTask(id="real", engine="office_bridge", action="office_to_pdf", inputFiles=[str(src)],
                         outputDir=str(tmp_path / "Salida PDF"), options={"timeoutSec": 120})
    outputs, _ = EngineRegistry().execute(task, lambda e: None, threading.Event())
    with fitz.open(outputs[0]) as doc:
        assert doc[0].get_text().strip() == body
