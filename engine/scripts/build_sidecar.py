"""Project-standard entry point for freezing the DocForge sidecar."""
from __future__ import annotations

import sys
from pathlib import Path

engine_root = Path(__file__).resolve().parents[1]
if str(engine_root) not in sys.path:
    sys.path.insert(0, str(engine_root))

from build_sidecar import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
