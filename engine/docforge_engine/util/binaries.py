from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

_EXE = {"soffice": "soffice", "ffmpeg": "ffmpeg"}
_ENV = {"soffice": "DOCFORGE_SOFFICE", "ffmpeg": "DOCFORGE_FFMPEG"}


def _program_dirs() -> list[str]:
    dirs = [os.environ.get(name) for name in (
        "ProgramFiles", "ProgramW6432", "ProgramFiles(x86)", "LOCALAPPDATA", "APPDATA", "ProgramData",
    )]
    user_profile = os.environ.get("USERPROFILE") or os.path.expanduser("~")
    dirs += [user_profile, os.path.join(user_profile, "Desktop"), os.path.join(user_profile, "Downloads")]
    dirs += [r"C:\Program Files", r"C:\Program Files (x86)", r"C:\ProgramData"]
    seen, result = set(), []
    for d in dirs:
        if d and d.lower() not in seen:
            seen.add(d.lower())
            result.append(d)
    return result


def _candidates(kind: str) -> list[Path]:
    if kind == "soffice":
        roots = [Path(d) for d in _program_dirs()]
        paths = []
        for root in roots:
            paths += [
                root / "LibreOffice" / "program" / "soffice.exe",
                root / "Programs" / "LibreOffice" / "program" / "soffice.exe",
                root / "LibreOfficePortable" / "App" / "libreoffice" / "program" / "soffice.exe",
                root / "LibreOfficePortable" / "App" / "LibreOffice" / "program" / "soffice.exe",
            ]
            # Installed packages commonly use "LibreOffice 7" or another versioned folder.
            try:
                paths.extend(root.glob("LibreOffice*/program/soffice.exe"))
                paths.extend((root / "Programs").glob("LibreOffice*/program/soffice.exe"))
                paths.extend((root / "LibreOfficePortable").glob("*/App/libreoffice/program/soffice.exe"))
            except OSError:
                pass
        home = Path(os.path.expanduser("~"))
        paths += [
            home / "scoop" / "apps" / "libreoffice" / "current" / "LibreOffice" / "program" / "soffice.exe",
            home / "scoop" / "apps" / "libreoffice" / "current" / "program" / "soffice.exe",
            Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "chocolatey" / "bin" / "soffice.exe",
        ]
        try:
            choco = Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "chocolatey" / "lib"
            paths.extend(choco.glob("libreoffice*/tools/LibreOffice/program/soffice.exe"))
            paths.extend(choco.glob("libreoffice*/tools/program/soffice.exe"))
        except OSError:
            pass
        paths += _registry_candidates()
        paths += [Path("/Applications/LibreOffice.app/Contents/MacOS/soffice"), Path("/usr/bin/soffice"),
                  Path("/usr/local/bin/soffice"), Path("/opt/homebrew/bin/soffice")]
    else:
        paths = [Path(d) / "ffmpeg" / "bin" / "ffmpeg.exe" for d in _program_dirs()]
        paths += [Path(r"C:\ffmpeg\bin\ffmpeg.exe"), Path("/opt/homebrew/bin/ffmpeg"),
                  Path("/usr/local/bin/ffmpeg"), Path("/usr/bin/ffmpeg")]
    return paths


def _registry_candidates() -> list[Path]:
    """Read only the documented LibreOffice install keys; never recurse the registry."""
    if sys.platform != "win32":
        return []
    try:
        import winreg
    except ImportError:
        return []
    candidates: list[Path] = []
    locations = (
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\LibreOffice\UNO"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\LibreOffice\UNO"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\LibreOffice\UNO"),
    )
    for hive, key_name in locations:
        try:
            with winreg.OpenKey(hive, key_name) as key:
                value, _ = winreg.QueryValueEx(key, "InstallPath")
            root = Path(str(value))
            candidates.extend((root / "program" / "soffice.exe", root / "soffice.exe"))
        except (OSError, TypeError, ValueError):
            continue
    return candidates


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
        # PATHEXT resolves "soffice" to soffice.COM first; normalise to soffice.exe.
        return str(_normalize(kind, on_path) or Path(on_path))
    return next((str(p) for p in _candidates(kind) if p.is_file()), None)
