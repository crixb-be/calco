from __future__ import annotations

import os
import re
import tempfile
import threading
from contextlib import contextmanager
from contextvars import ContextVar
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
_reservation_lock = threading.Lock()
_reserved_paths: set[Path] = set()
# Paths reserved by the task running in the current thread (set by task_reservations()).
_task_reservations: ContextVar[list[Path] | None] = ContextVar("docforge_task_reservations", default=None)


@contextmanager
def task_reservations():
    """Scope output-name reservations to one task.

    On success every reservation still held is released (the outputs stay). On failure or
    cancellation, placeholders that were never written (still 0 bytes) are deleted so a
    failed task never leaves empty files in the user's output folder."""
    reserved: list[Path] = []
    token = _task_reservations.set(reserved)
    try:
        yield
    except BaseException:
        for path in reserved:
            release_output_path(path, remove_placeholder=False)
            try:
                if path.is_file() and path.stat().st_size == 0:
                    path.unlink()
            except OSError:
                pass
        raise
    else:
        for path in reserved:
            release_output_path(path, remove_placeholder=False)
    finally:
        _task_reservations.reset(token)


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
    out_dir.mkdir(parents=True, exist_ok=True)
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
    input_set = {Path(p).resolve() for p in task.inputFiles}
    n = 1
    with _reservation_lock:
        while True:
            candidate = out_dir / candidate_name if n == 1 else out_dir / f"{Path(candidate_name).stem}_{n}{Path(candidate_name).suffix}"
            resolved = candidate.resolve()
            if resolved in input_set or resolved in _reserved_paths:
                n += 1
                continue
            try:
                # The placeholder reserves the name for this process and also closes
                # the race with another process doing the same atomic create.
                with candidate.open("x"):
                    pass
            except FileExistsError:
                n += 1
                continue
            _reserved_paths.add(resolved)
            scoped = _task_reservations.get()
            if scoped is not None:
                scoped.append(candidate)
            return candidate


def release_output_path(path: Path, *, remove_placeholder: bool = True) -> None:
    """Release a reserved output name, optionally removing its placeholder."""
    resolved = Path(path).resolve()
    with _reservation_lock:
        if resolved not in _reserved_paths:
            return
        _reserved_paths.remove(resolved)
        if remove_placeholder:
            try:
                Path(path).unlink()
            except FileNotFoundError:
                pass


def atomic_write_bytes(path: Path, data: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.stem}-", suffix=path.suffix, dir=path.parent)
    committed = False
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
        committed = True
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
        release_output_path(path, remove_placeholder=not committed)
    return path


def atomic_save(path: Path, saver: Callable[[str], None]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.stem}-", suffix=path.suffix, dir=path.parent)
    os.close(fd)
    committed = False
    try:
        saver(temp_name)
        os.replace(temp_name, path)
        committed = True
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
        release_output_path(path, remove_placeholder=not committed)
    return path
