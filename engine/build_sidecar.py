"""Build the frozen Python sidecar consumed by Tauri externalBin.

The sidecar deliberately keeps ``--console``: its stdin/stdout are the NDJSON transport
used by Tauri, so a no-console build would remove the protocol streams.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

TARGET = "x86_64-pc-windows-msvc"
_EXCLUDES = (
    "tkinter", "_tkinter", "PIL._tkinter_finder", "PIL.ImageTk", "unittest", "pydoc", "pydoc_data",
    "doctest", "lib2to3", "idlelib", "turtle", "turtledemo", "test", "distutils", "setuptools",
    "pip", "ensurepip", "venv", "xmlrpc", "curses", "sqlite3", "IPython", "matplotlib", "pytest",
    "tests", "numpy.tests", "pikepdf.tests", "pydantic.v1", "win32com.test", "win32com.demos",
)


def _clean_python_caches(package_root: Path) -> None:
    for cache in package_root.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)
    for bytecode in package_root.rglob("*.pyc"):
        try:
            bytecode.unlink()
        except OSError:
            pass


def _size_mb(path: Path) -> str:
    return f"{path.stat().st_size / (1024 * 1024):.1f} MB" if path.is_file() else "n/a"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build the DocForge PyInstaller sidecar.",
        epilog="Lite builds default to bytecode optimization 2. Full Docling/Torch builds use optimization 0 unless --optimize is supplied.",
    )
    parser.add_argument("--lite", action="store_true", help="exclude optional Docling/Torch modules")
    parser.add_argument("--target", default=TARGET, help="Rust target suffix used by Tauri")
    parser.add_argument("--optimize", type=int, choices=(0, 1, 2), default=None, help="PyInstaller bytecode optimization level (default: 2 for --lite, 0 otherwise)")
    parser.add_argument("--upx", action="store_true", help="enable UPX compression (opt-in)")
    parser.add_argument("--upx-dir", default=None, help="UPX directory; otherwise PyInstaller searches PATH")
    args = parser.parse_args(argv)

    engine_root = Path(__file__).resolve().parent
    repo_root = engine_root.parent
    entry = engine_root / "docforge_engine" / "sidecar_entry.py"
    if not entry.is_file():
        raise FileNotFoundError(entry)
    _clean_python_caches(engine_root / "docforge_engine")

    target_name = f"docforge-engine-{args.target}"
    build_root = engine_root / "build" / target_name
    dist_root = engine_root / "dist" / target_name
    binary_dir = repo_root / "app" / "src-tauri" / "binaries"
    binary_dir.mkdir(parents=True, exist_ok=True)
    for known in (build_root, dist_root):
        if known.exists():
            shutil.rmtree(known)

    optimize = args.optimize if args.optimize is not None else (2 if args.lite else 0)
    command = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--console",
        "--optimize", str(optimize), "--name", target_name, "--paths", str(engine_root),
        "--distpath", str(engine_root / "dist"), "--workpath", str(build_root),
        "--specpath", str(build_root),
        "--collect-binaries", "pymupdf", "--collect-data", "pymupdf",
        "--hidden-import", "pymupdf", "--hidden-import", "win32com.client",
        "--hidden-import", "pythoncom", "--hidden-import", "pywintypes", "--hidden-import", "win32timezone",
        "--collect-submodules", "win32com",
    ]
    for module in _EXCLUDES:
        command += ["--exclude-module", module]
    if args.lite:
        command += [
            "--exclude-module", "docling", "--exclude-module", "docling_core",
            "--exclude-module", "torch", "--exclude-module", "torchvision", "--exclude-module", "numpy",
        ]
    if args.upx:
        command += ["--upx-exclude", "vcruntime140.dll", "--upx-exclude", "python3*.dll"]
        if args.upx_dir:
            command += ["--upx-dir", args.upx_dir]
    command.append(str(entry))

    previous = binary_dir / f"{target_name}.exe"
    previous_size = _size_mb(previous)
    subprocess.run(command, cwd=engine_root, check=True)
    built = dist_root.with_suffix(".exe" if sys.platform == "win32" else "")
    if not built.is_file():
        raise RuntimeError(f"PyInstaller no creó el binario esperado: {built}")
    destination = binary_dir / f"{target_name}{'.exe' if sys.platform == 'win32' else ''}"
    shutil.copy2(built, destination)
    print(f"Sidecar listo: {destination}")
    print(f"Tamaño producido: {_size_mb(destination)} (anterior: {previous_size})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
