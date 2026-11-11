"""PyInstaller entrypoint that preserves the package context for relative imports."""
from __future__ import annotations

from docforge_engine.__main__ import main


if __name__ == "__main__":
    raise SystemExit(main())
