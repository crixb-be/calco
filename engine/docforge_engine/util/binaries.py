from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

_EXE = {"soffice": "soffice", "ffmpeg": "ffmpeg"}
_ENV = {"soffice": "DOCFORGE_SOFFICE", "ffmpeg": "DOCFORGE_FFMPEG"}


def _program_dirs() -> list[str]:
    dirs = [os.environ.get(name) for name in ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)", "LOCALAPPDATA")]
    dirs += [r"C:\Program Files", r"C:\Program Files (x86)"]
    seen, result = set(), []
    for d in dirs:
        if d and d.lower() not in seen:
            seen.add(d.lower())
            result.append(d)
    return result


def _candidates(kind: str) -> list[Path]:
    if kind == "soffice":
        paths = [Path(d) / "LibreOffice" / "program" / "soffice.exe" for d in _program_dirs()]
        paths += [Path(d) / "Programs" / "LibreOffice" / "program" / "soffice.exe" for d in _program_dirs()]
        paths += [Path("/Applications/LibreOffice.app/Contents/MacOS/soffice"), Path("/usr/bin/soffice"),
                  Path("/usr/local/bin/soffice"), Path("/opt/homebrew/bin/soffice")]
    else:
        paths = [Path(d) / "ffmpeg" / "bin" / "ffmpeg.exe" for d in _program_dirs()]
        paths += [Path(r"C:\ffmpeg\bin\ffmpeg.exe"), Path("/opt/homebrew/bin/ffmpeg"),
                  Path("/usr/local/bin/ffmpeg"), Path("/usr/bin/ffmpeg")]
    return paths


def _normalize(kind: str, raw) -> Path | None:
    """Accept a file path, a quoted path, or a directory containing the binary."""
    if raw is None:
        return None
    text = str(raw).strip().strip('"').strip("'").strip()
    if not text:
        return None
    path = Path(os.path.expandvars(os.path.expanduser(text)))
    if path.is_dir():
        exe = _EXE[kind] + (".exe" if sys.platform == "win32" else "")
        for candidate in (path / exe, path / "program" / exe, path / "bin" / exe):
            if candidate.is_file():
                return candidate
        return None
    if path.is_file():
        # On Windows prefer soffice.exe over soffice.com / soffice.bin if user pointed at those.
        if kind == "soffice" and sys.platform == "win32" and path.suffix.lower() in (".com", ".bin"):
            exe = path.with_name("soffice.exe")
            return exe if exe.is_file() else path
        return path
    return None


def locate_binary(kind: str, options: dict | None = None) -> str | None:
    """Resolution order: options.binaryPath -> env var -> PATH -> standard install locations."""
    options = options or {}
    for raw in (options.get("binaryPath"), os.environ.get(_ENV[kind])):
        found = _normalize(kind, raw)
        if found:
            return str(found)
    on_path = shutil.which(_EXE[kind])
    if on_path:
        return str(Path(on_path))
    return next((str(p) for p in _candidates(kind) if p.is_file()), None)
