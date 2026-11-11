"""Small subprocess helpers shared by Windows-facing engine integrations."""
from __future__ import annotations

import subprocess
import sys


def no_window_kwargs(*, extra_creationflags: int = 0) -> dict[str, int]:
    """Return Windows creation flags that keep child processes invisible.

    The function is deliberately usable on every platform so modules remain import-safe
    during tests and when the sidecar is developed on macOS/Linux.
    """
    if sys.platform != "win32":
        return {}
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | extra_creationflags
    return {"creationflags": flags}
