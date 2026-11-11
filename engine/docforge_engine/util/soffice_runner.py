"""Robust, cancellable LibreOffice (soffice) headless conversion.

Why not a plain ``subprocess.run(cmd, capture_output=True, timeout=60)``:
on Windows ``soffice.exe`` is only a launcher that spawns ``soffice.bin``.
On timeout Python kills the launcher, but the grandchild keeps the stdout/stderr
pipes open and ``run()`` blocks forever reading them -> task frozen at 0%.

This runner:
  * passes arguments as a list (no shell),
  * runs LibreOffice in a *neutral* temp dir (ASCII, no spaces): the input is copied as
    ``in/input.<ext>`` and the result is moved to the real output dir afterwards, so accents
    ('MAESTRÍA GESTIÓN'), spaces, OneDrive or long paths never reach LibreOffice,
  * redirects LibreOffice output to files instead of pipes (nothing can block on a pipe),
  * uses an isolated, throwaway LibreOffice profile (-env:UserInstallation) so an
    already-open LibreOffice window or a stale lock cannot capture/stall the job,
  * polls in a loop: heartbeat progress + logs, honours cancellation, enforces timeout,
  * kills the whole process tree on timeout/cancel (taskkill /T on Windows),
  * logs every step (command, PID, waiting, captured output, return code).
"""
from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Callable

from ..errors import EngineError

DEFAULT_TIMEOUT_SEC = 60.0
_POLL_SEC = 0.25
_HEARTBEAT_LOG_SEC = 5.0


def _is_ascii(text: str) -> bool:
    return all(ord(ch) < 128 for ch in text)


def neutral_temp_root() -> Path:
    """Writable temp root whose path is pure ASCII (e.g. a user named 'José' breaks %TEMP%)."""
    candidates = [tempfile.gettempdir()]
    if sys.platform == "win32":
        candidates += [
            os.path.join(os.environ.get("PUBLIC", "C:" + os.sep + "Users" + os.sep + "Public"), "DocForge", "tmp"),
            os.path.join(os.environ.get("ProgramData", "C:" + os.sep + "ProgramData"), "DocForge", "tmp"),
        ]
    for candidate in candidates:
        path = os.path.abspath(candidate)
        if not _is_ascii(path):
            continue
        try:
            os.makedirs(path, exist_ok=True)
            return Path(path)
        except OSError:
            continue
    return Path(os.path.abspath(tempfile.gettempdir()))


def _kill_tree(process: subprocess.Popen) -> None:
    if sys.platform == "win32":
        # The launcher can exit before its soffice.bin child does. Run taskkill
        # even when poll() says the direct child is gone, so inherited handles
        # held by the process tree cannot keep temp files open.
        try:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), timeout=15,
            )
        except Exception:
            pass
    else:
        if process.poll() is not None:
            return
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except Exception:
            pass
    try:
        process.kill()
        process.wait(timeout=5)
    except Exception:
        pass


def _tail(path: Path, limit: int = 4000) -> str:
    """Read LibreOffice output; it may be UTF-8 or the ANSI code page, never fail on it."""
    try:
        raw = path.read_bytes()[-limit:]
    except OSError:
        return ""
    for encoding in ("utf-8", "mbcs" if sys.platform == "win32" else "latin-1"):
        try:
            return raw.decode(encoding).strip()
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace").strip()


def convert_with_soffice(
    soffice_path: str,
    input_file: Path,
    output_dir: Path,
    convert_to: str,
    *,
    infilter: str | None = None,
    timeout_sec: float = DEFAULT_TIMEOUT_SEC,
    on_tick: Callable[[float, float], None] | None = None,
    is_cancelled: Callable[[], bool] | None = None,
    log: Callable[[str, str], None] | None = None,
) -> Path:
    """Convert ``input_file``; the result lands in ``output_dir`` as ``<stem>.<ext>``.

    ``convert_to`` is the soffice --convert-to argument (e.g. "pdf" or "docx:MS Word 2007 XML").
    ``on_tick(elapsed, timeout)`` is called while waiting; ``log(message, level)`` for each step.
    Raises EngineError(TIMEOUT | CANCELLED | CONVERSION_FAILED | INPUT_NOT_FOUND | BINARY_NOT_FOUND).
    """

    def _log(message: str, level: str = "info") -> None:
        if log:
            log(message, level)
        else:
            print(f"[soffice] {level.upper()} {message}", file=sys.stderr, flush=True)

    input_file = Path(os.path.abspath(input_file))
    output_dir = Path(os.path.abspath(output_dir))
    if not input_file.is_file():
        raise EngineError("INPUT_NOT_FOUND", f"Archivo de entrada no encontrado: {input_file}")
    output_dir.mkdir(parents=True, exist_ok=True)
    target_ext = convert_to.split(":", 1)[0].strip().lower()
    expected = output_dir / f"{input_file.stem}.{target_ext}"

    work_ctx = tempfile.TemporaryDirectory(prefix="docforge-lo-", dir=neutral_temp_root())
    log_root = Path(tempfile.mkdtemp(prefix="docforge-lo-logs-", dir=neutral_temp_root()))
    stdout_path = log_root / "stdout.log"
    stderr_path = log_root / "stderr.log"
    try:
        work_dir = Path(work_ctx.name)
        in_dir, out_tmp = work_dir / "in", work_dir / "out"
        in_dir.mkdir()
        out_tmp.mkdir()
        neutral_input = in_dir / f"input{input_file.suffix.lower()}"
        shutil.copy2(input_file, neutral_input)
        generated = out_tmp / f"input.{target_ext}"
        _log(f"Entrada: {input_file}")
        _log(f"Copia neutra para LibreOffice: {neutral_input}")

        profile_uri = (work_dir / "profile").as_uri()  # file:///C:/... (percent-encoded)
        cmd = [
            soffice_path,
            f"-env:UserInstallation={profile_uri}",
            "--headless",
            "--invisible",
            "--nologo",
            "--nodefault",
            "--nofirststartwizard",
            "--norestore",
            "--nolockcheck",
        ]
        if infilter:
            cmd.append(f"--infilter={infilter}")
        cmd += ["--convert-to", convert_to, "--outdir", str(out_tmp), str(neutral_input)]
        cmdline = subprocess.list2cmdline(cmd)
        _log(f"Comando: {cmdline}")
        popen_kwargs: dict = {}
        if sys.platform == "win32":
            popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        else:
            popen_kwargs["start_new_session"] = True

        with stdout_path.open("wb") as stdout_handle, stderr_path.open("wb") as stderr_handle:
            try:
                process = subprocess.Popen(
                    cmd, stdin=subprocess.DEVNULL, stdout=stdout_handle, stderr=stderr_handle,
                # Do not use the disposable work directory as CWD: soffice.exe may
                # spawn a child that keeps that directory open on Windows.
                cwd=str(neutral_temp_root()), **popen_kwargs,
                )
            except OSError as exc:
                _log(f"No se pudo lanzar LibreOffice: {exc}", "error")
                raise EngineError("BINARY_NOT_FOUND", f"No se pudo ejecutar LibreOffice: {soffice_path}", str(exc)) from exc

            _log(f"PID lanzado: {process.pid}; esperando proceso (timeout {timeout_sec:.0f}s)")
            started = time.monotonic()
            next_heartbeat = _HEARTBEAT_LOG_SEC
            try:
                while process.poll() is None:
                    elapsed = time.monotonic() - started
                    if is_cancelled and is_cancelled():
                        _kill_tree(process)
                        _log(f"Cancelado; árbol de procesos {process.pid} terminado", "warn")
                        raise EngineError("CANCELLED", "Conversión cancelada")
                    if elapsed > timeout_sec:
                        _kill_tree(process)
                        _log(f"Timeout tras {elapsed:.0f}s; árbol de procesos {process.pid} terminado", "error")
                        raise EngineError(
                            "TIMEOUT",
                            f"LibreOffice superó el tiempo límite de {timeout_sec:.0f}s convirtiendo {input_file.name}",
                            "Aumenta 'timeoutSec' en las opciones o revisa si el documento es muy grande o está dañado.\n"
                            f"comando: {cmdline}",
                        )
                    if elapsed >= next_heartbeat:
                        _log(f"Esperando a LibreOffice (PID {process.pid})... {elapsed:.0f}s")
                        next_heartbeat += _HEARTBEAT_LOG_SEC
                    if on_tick:
                        on_tick(elapsed, timeout_sec)
                    time.sleep(_POLL_SEC)
            finally:
                if process.poll() is None:
                    _kill_tree(process)
                # Never call communicate() after a timeout: a soffice grandchild can
                # intentionally retain an inherited pipe and block forever. Output
                # is file-backed, so closing these handles releases the descriptors.
        returncode = process.returncode
        duration = time.monotonic() - started
        stdout = _tail(stdout_path)
        stderr = _tail(stderr_path)
        _log(f"Proceso terminado: código de retorno {returncode} en {duration:.1f}s")
        if stdout:
            _log(f"stdout de LibreOffice: {stdout}")
        if stderr:
            _log(f"stderr de LibreOffice: {stderr}", "warn")

        details = "\n".join(filter(None, [
            f"exit code: {returncode}",
            f"comando: {cmdline}",
            f"stdout: {stdout}" if stdout else "",
            f"stderr: {stderr}" if stderr else "",
        ]))
        if returncode != 0:
            raise EngineError("CONVERSION_FAILED", f"LibreOffice falló al convertir {input_file.name} (código {returncode})", details)
        if not generated.is_file() or generated.stat().st_size == 0:
            raise EngineError(
                "CONVERSION_FAILED",
                f"LibreOffice terminó pero no generó {expected.name} en {output_dir}",
                details,
            )
        if expected.exists():
            expected.unlink()
        shutil.move(str(generated), str(expected))
        _log(f"Resultado movido a: {expected}")
    finally:
        work_ctx.cleanup()
        shutil.rmtree(log_root, ignore_errors=True)
    return expected
