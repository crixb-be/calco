"""Build the frozen Python sidecar consumed by Tauri externalBin."""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


TARGET = "x86_64-pc-windows-msvc"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lite", action="store_true", help="exclude optional Docling/Torch modules")
    parser.add_argument("--target", default=TARGET, help="Rust target suffix used by Tauri")
    args = parser.parse_args(argv)

    engine_root = Path(__file__).resolve().parent
    repo_root = engine_root.parent
    entry = engine_root / "docforge_engine" / "sidecar_entry.py"
    if not entry.is_file():
        raise FileNotFoundError(entry)

    target_name = f"docforge-engine-{args.target}"
    build_root = engine_root / "build" / target_name
    dist_root = engine_root / "dist" / target_name
    binary_dir = repo_root / "app" / "src-tauri" / "binaries"
    binary_dir.mkdir(parents=True, exist_ok=True)
    for known in (build_root, dist_root):
        if known.exists():
            shutil.rmtree(known)

    command = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--console",
        "--name", target_name, "--paths", str(engine_root),
        "--distpath", str(engine_root / "dist"), "--workpath", str(build_root),
        "--specpath", str(build_root),
        "--collect-all", "pymupdf", "--collect-all", "PIL",
        "--hidden-import", "pymupdf", "--hidden-import", "PIL._tkinter_finder",
        "--exclude-module", "tests", "--exclude-module", "pytest",
        "--exclude-module", "__pycache__", str(entry),
    ]
    if args.lite:
        command += [
            "--exclude-module", "docling", "--exclude-module", "docling_core",
            "--exclude-module", "torch", "--exclude-module", "torchvision",
        ]

    subprocess.run(command, cwd=engine_root, check=True)
    suffix = ".exe" if sys.platform == "win32" else ""
    built = dist_root.with_suffix(suffix)
    if not built.is_file():
        raise RuntimeError(f"PyInstaller no creó el binario esperado: {built}")
    destination = binary_dir / f"{target_name}{suffix}"
    shutil.copy2(built, destination)
    print(f"Sidecar listo: {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
