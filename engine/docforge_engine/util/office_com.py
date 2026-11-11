"""Optional, invisible Microsoft Office COM conversion backend.

This module never imports pywin32 at module import time.  That keeps the engine usable on
non-Windows platforms and lets LibreOffice remain the fallback when Office is absent or a
document cannot be opened by COM.
"""
from __future__ import annotations

import csv
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Callable

from ..errors import EngineError
from .proc import no_window_kwargs
from .soffice_runner import neutral_temp_root


class OfficeComError(Exception):
    """A conversion failure for which the caller should try LibreOffice."""


_PROGIDS = {
    "msword": "Word.Application",
    "msexcel": "Excel.Application",
    "mspowerpoint": "PowerPoint.Application",
}
_EXTENSIONS = {
    "msword": frozenset({".docx", ".doc", ".odt", ".rtf", ".txt"}),
    "msexcel": frozenset({".xlsx", ".xls", ".ods", ".csv"}),
    "mspowerpoint": frozenset({".pptx", ".ppt", ".odp"}),
}


_DUMMY_PASSWORD = "docforge-no-password"


def office_kind_for_extension(extension: str) -> str | None:
    extension = extension.lower()
    return next((kind for kind, extensions in _EXTENSIONS.items() if extension in extensions), None)


def _com_modules():
    try:
        import pythoncom  # type: ignore
        import win32com.client  # type: ignore
    except Exception:  # ImportError, or OSError when frozen pywin32 DLLs fail to load
        return None
    try:
        import win32process  # type: ignore
    except Exception:
        win32process = None
    return pythoncom, win32com.client, win32process


def _registry_has_progid(progid: str) -> bool:
    if sys.platform != "win32":
        return False
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, f"{progid}\\CLSID"):
            return True
    except Exception:
        return False


def com_available(kind: str) -> bool:
    """Check pywin32 and the Office ProgID registry entry without launching Office."""
    if sys.platform != "win32" or kind not in _PROGIDS:
        return False
    # Escape hatch (tests, troubleshooting): force the LibreOffice path.
    if os.environ.get("DOCFORGE_DISABLE_OFFICE_COM", "").strip() not in ("", "0"):
        return False
    return _com_modules() is not None and _registry_has_progid(_PROGIDS[kind])


def _tasklist_pids(image_name: str) -> set[int]:
    if sys.platform != "win32":
        return set()
    try:
        completed = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {image_name}", "/FO", "CSV", "/NH"],
            capture_output=True,
            check=False,
            timeout=5,
            **no_window_kwargs(),
        )
        text = completed.stdout.decode("mbcs", errors="replace")
        result: set[int] = set()
        for row in csv.reader(text.splitlines()):
            if len(row) >= 2:
                try:
                    result.add(int(row[1].replace(",", "")))
                except ValueError:
                    pass
        return result
    except (OSError, subprocess.SubprocessError, LookupError):
        return set()


def _app_pid(app, win32process, kind: str, before: set[int]) -> int | None:
    if win32process is not None:
        for attribute in ("Hwnd", "HWND", "hwnd"):
            try:
                hwnd = int(getattr(app, attribute))
                if hwnd:
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    if pid:
                        return int(pid)
            except (AttributeError, TypeError, ValueError, OSError):
                continue
    image = {"msword": "WINWORD.EXE", "msexcel": "EXCEL.EXE", "mspowerpoint": "POWERPNT.EXE"}[kind]
    new_pids = _tasklist_pids(image) - before
    return next(iter(new_pids), None)


def _kill_office_pid(pid: int | None, log: Callable[[str, str], None] | None) -> None:
    if not pid or sys.platform != "win32":
        return
    try:
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=15,
            **no_window_kwargs(),
        )
        if log:
            log(f"Proceso de Microsoft Office {pid} terminado", "warn")
    except (OSError, subprocess.SubprocessError):
        pass


def _convert_word(app, input_path: Path, output_path: Path) -> None:
    app.Visible = False
    app.DisplayAlerts = 0
    document = None
    try:
        document = app.Documents.Open(
            str(input_path),
            ConfirmConversions=False,
            ReadOnly=True,
            AddToRecentFiles=False,
            Visible=False,
            OpenAndRepair=False,
            NoEncodingDialog=True,
            # A dummy password is ignored by unprotected files but makes protected ones
            # fail immediately instead of blocking on an invisible password dialog.
            PasswordDocument=_DUMMY_PASSWORD,
            WritePasswordDocument=_DUMMY_PASSWORD,
        )
        document.ExportAsFixedFormat(str(output_path), 17)
    finally:
        if document is not None:
            try:
                document.Close(SaveChanges=0)
            except Exception:
                pass


def _convert_excel(app, input_path: Path, output_path: Path) -> None:
    app.Visible = False
    app.DisplayAlerts = False
    workbook = None
    try:
        workbook = app.Workbooks.Open(
            str(input_path), UpdateLinks=0, ReadOnly=True,
            Password=_DUMMY_PASSWORD, WriteResPassword=_DUMMY_PASSWORD,
            IgnoreReadOnlyRecommended=True, Notify=False, AddToMru=False,
        )
        workbook.ExportAsFixedFormat(0, str(output_path))
    finally:
        if workbook is not None:
            try:
                workbook.Close(SaveChanges=False)
            except Exception:
                pass


def _convert_powerpoint(app, input_path: Path, output_path: Path) -> None:
    # PowerPoint refuses ``Visible = False`` ("Hiding the application window is not
    # allowed"); WithWindow=False below keeps the document windowless instead.
    try:
        app.DisplayAlerts = 1  # ppAlertsNone
    except Exception:
        pass
    presentation = None
    try:
        presentation = app.Presentations.Open(str(input_path), ReadOnly=True, Untitled=False, WithWindow=False)
        presentation.SaveAs(str(output_path), 32)
    finally:
        if presentation is not None:
            try:
                presentation.Close()
            except Exception:
                pass


def convert_with_office_com(
    kind: str,
    input_file: Path,
    output_dir: Path,
    *,
    timeout_sec: float,
    on_tick: Callable[[float, float], None] | None = None,
    is_cancelled: Callable[[], bool] | None = None,
    log: Callable[[str, str], None] | None = None,
) -> Path:
    """Convert one Office document in an isolated COM instance.

    COM is initialized and uninitialized on the worker thread.  The caller thread owns
    timeout/cancellation polling and only kills the PID discovered for this DispatchEx.
    """
    modules = _com_modules()
    if sys.platform != "win32" or modules is None or kind not in _PROGIDS:
        raise OfficeComError(f"Microsoft Office no está disponible para {kind}")
    pythoncom, client, win32process = modules
    input_file = Path(os.path.abspath(input_file))
    output_dir = Path(os.path.abspath(output_dir))
    if not input_file.is_file():
        raise EngineError("INPUT_NOT_FOUND", f"Archivo de entrada no encontrado: {input_file}")
    output_dir.mkdir(parents=True, exist_ok=True)

    # A killed Office process may still hold the copy for a moment; never let cleanup
    # mask the real TIMEOUT/CANCELLED error.
    work_ctx = tempfile.TemporaryDirectory(prefix="docforge-office-", dir=neutral_temp_root(), ignore_cleanup_errors=True)
    work_dir = Path(work_ctx.name)
    neutral_input = work_dir / f"input{input_file.suffix.lower()}"
    neutral_output = work_dir / "input.pdf"
    shutil.copy2(input_file, neutral_input)
    before = _tasklist_pids({"msword": "WINWORD.EXE", "msexcel": "EXCEL.EXE", "mspowerpoint": "POWERPNT.EXE"}[kind])
    state: dict[str, object] = {"pid": None, "error": None}
    ready = threading.Event()
    abort = threading.Event()

    def worker() -> None:
        app = None
        try:
            pythoncom.CoInitialize()
            try:
                app = client.DispatchEx(_PROGIDS[kind])
                state["pid"] = _app_pid(app, win32process, kind, before)
                ready.set()
                if abort.is_set():
                    # Timed out / cancelled while Office was still starting: quit at once.
                    return
                if kind == "msword":
                    _convert_word(app, neutral_input, neutral_output)
                elif kind == "msexcel":
                    _convert_excel(app, neutral_input, neutral_output)
                else:
                    _convert_powerpoint(app, neutral_input, neutral_output)
            finally:
                if app is not None:
                    try:
                        app.Quit()
                    except Exception:
                        pass
                pythoncom.CoUninitialize()
        except BaseException as exc:  # transfer all COM exceptions to the caller
            state["error"] = exc
            ready.set()

    def stop_office() -> None:
        # If Office is still launching, its PID is unknown: wait briefly for it so the
        # instance we created is never orphaned. Pre-existing Office processes are untouched.
        abort.set()
        ready.wait(timeout=15)
        _kill_office_pid(state.get("pid"), log)
        thread.join(timeout=5)

    thread = threading.Thread(target=worker, name="docforge-office-com", daemon=True)
    thread.start()
    started = time.monotonic()
    last_heartbeat = -1.0
    try:
        while thread.is_alive():
            elapsed = time.monotonic() - started
            if is_cancelled and is_cancelled():
                stop_office()
                raise EngineError("CANCELLED", "Conversión cancelada por el usuario")
            if elapsed >= timeout_sec:
                stop_office()
                raise EngineError(
                    "TIMEOUT",
                    f"Microsoft Office superó el tiempo límite de {timeout_sec:g}s convirtiendo {input_file.name}",
                    "La aplicación de Office fue terminada para evitar que la tarea quedara bloqueada.",
                )
            if log and elapsed - last_heartbeat >= 5.0:
                log(f"Esperando a Microsoft Office ({kind})... {elapsed:.0f}s", "info")
                last_heartbeat = elapsed
            if on_tick:
                on_tick(elapsed, timeout_sec)
            time.sleep(0.1)
        thread.join(timeout=1)
        error = state.get("error")
        if error is not None:
            if isinstance(error, EngineError):
                raise error
            raise OfficeComError(f"Microsoft Office no pudo convertir {input_file.name}: {error}") from error
        if not neutral_output.is_file() or neutral_output.stat().st_size == 0:
            raise OfficeComError(f"Microsoft Office terminó sin generar el PDF de {input_file.name}")
        expected = output_dir / f"{input_file.stem}.pdf"
        if expected.exists():
            expected.unlink()
        shutil.move(str(neutral_output), str(expected))
        return expected
    finally:
        work_ctx.cleanup()
