from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from typing import Callable

from ..errors import EngineError


def require_inputs(task) -> list[Path]:
    paths = [Path(p).expanduser() for p in task.inputFiles]
    missing = [str(p) for p in paths if not p.is_file()]
    if missing:
        raise EngineError("INPUT_NOT_FOUND", "Input file not found", "; ".join(missing))
    Path(task.outputDir).mkdir(parents=True, exist_ok=True)
    return paths


_WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def safe_stem(path: Path) -> str:
    """Keep accents/Unicode letters and spaces (e.g. 'Tesis Maestría'); only replace characters
    that are invalid in Windows/macOS file names."""
    stem = "".join(ch for ch in path.stem if ord(ch) >= 32)  # drop control characters
    stem = re.sub(r'[<>:"/\\|?*]+', "_", stem)
    stem = re.sub(r"\s+", " ", stem).strip(" ._") or "document"
    if stem.upper() in _WINDOWS_RESERVED:
        stem = f"_{stem}"
    return stem[:150]


def output_path(task, stem: str, action: str, extension: str, index: int | None = None) -> Path:
    out_dir = Path(task.outputDir)
    output_name = task.options.get("outputName") if index is None else None
    if output_name:
        candidate_name = Path(str(output_name)).name
        if not Path(candidate_name).suffix:
            candidate_name += extension if extension.startswith(".") else f".{extension}"
    else:
        suffix = extension if extension.startswith(".") else f".{extension}"
        candidate_name = f"{safe_stem(Path(stem))}_{action}"
        if index is not None:
            candidate_name += f"_{index + 1}"
        candidate_name += suffix
    candidate = out_dir / candidate_name
    input_set = {Path(p).resolve() for p in task.inputFiles}
    n = 2
    while candidate.resolve() in input_set or candidate.exists():
        candidate = out_dir / f"{candidate.stem}_{n}{candidate.suffix}"
        n += 1
    return candidate


def atomic_write_bytes(path: Path, data: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.stem}-", suffix=path.suffix, dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    return path


def atomic_save(path: Path, saver: Callable[[str], None]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.stem}-", suffix=path.suffix, dir=path.parent)
    os.close(fd)
    try:
        saver(temp_name)
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    return path
