"""Safe cleanup for DocForge's own temporary workspace.

The cleanup scope is deliberately narrow: only ``%TEMP%/DocForge`` (or the
explicitly supplied directory) is touched. This prevents a bundled app from
accidentally deleting files created by another application.
"""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path


def temp_root() -> Path:
    """Return the application-owned temporary directory."""
    return Path(os.environ.get("TEMP") or os.environ.get("TMP") or tempfile.gettempdir()) / "DocForge"


def _is_owned_root(root: Path) -> bool:
    try:
        return root.resolve().name.casefold() == "docforge"
    except OSError:
        return False


def purge_temp_artifacts(root: Path | None = None) -> int:
    """Remove stale files and ``.pytest-tmp`` directories from our temp root.

    Returns the number of entries removed. Permission errors are ignored so a
    locked file cannot prevent the sidecar from starting or shutting down.
    """
    target = Path(root) if root is not None else temp_root()
    if not _is_owned_root(target) or not target.exists() or not target.is_dir():
        return 0
    removed = 0
    try:
        children = tuple(target.iterdir())
    except OSError:
        return 0
    for child in children:
        try:
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child)
            else:
                child.unlink()
            removed += 1
        except (OSError, PermissionError):
            # Windows may still have a handle open; leave that entry for the
            # next startup instead of turning cleanup into a task failure.
            continue
    try:
        target.rmdir()
    except OSError:
        pass
    return removed


def startup_cleanup() -> int:
    """Purge leftovers from an earlier sidecar process."""
    return purge_temp_artifacts()


def shutdown_cleanup() -> int:
    """Purge leftovers after all worker pools have stopped."""
    return purge_temp_artifacts()

