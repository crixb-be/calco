# DocForge

DocForge es una suite documental local: la interfaz Tauri v2 + React vive en
`app/` y el motor Python offline vive en `engine/`.

## Puesta en marcha

Requisitos: Node 26, Rust 1.99, Python 3.12 y `uv`.

```powershell
cd engine
uv venv --python 3.12
# instala las dependencias del engine según pyproject.toml y sus extras

cd ..\app
npm install
npm run tauri dev
npm run tauri:dev
```

En desarrollo, DocForge arranca `engine/.venv/Scripts/python.exe -m
docforge_engine serve` (en macOS/Linux usa `.venv/bin/python`) cuando no hay
sidecar compilado. Para construirlo, ejecuta `python engine/build_sidecar.py` y
deja el binario generado en `app/src-tauri/binaries/`; luego usa el flujo de
empaquetado de Tauri.

LibreOffice y FFmpeg no se embeben: son opcionales y se buscan en `PATH` o en
las rutas que guardes desde Ajustes. Docling usa modelos locales después del
prefetch inicial.
