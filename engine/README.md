# DocForge Desktop engine

The sidecar targets Python 3.12 and communicates with the Tauri host using one JSON object per line.

## Setup

From this directory:

```powershell
uv venv --python 3.12
.\.venv\Scripts\Activate.ps1
uv pip install -e ".[pdf,dev]"
# Optional full Docling installation:
uv pip install -e ".[pdf,docling,dev]"
```

Docling model artifacts are kept at `%APPDATA%\DocForge\models`.

## Run

```powershell
python -m docforge_engine serve
python -m docforge_engine run .\task.json
```

`serve` reads `ProcessorTask` JSON lines from stdin and emits progress, result, and error events on stdout. It also accepts `{"type":"cancel","id":"..."}` and `{"type":"health"}` control messages.

## Test

```powershell
pytest
```

## Build

```powershell
python build_sidecar.py
python build_sidecar.py --lite
```

The PyInstaller onedir output is copied to `..\app\src-tauri\binaries\docforge-engine-<rust-target-triple>`.
