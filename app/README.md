# DocForge Desktop

## Desarrollo

1. Instala Node 26, Rust 1.99 y Python 3.12.
2. Desde `DocForge/engine`, crea el entorno con `uv venv --python 3.12` y
   instala las dependencias del motor según sus extras.
3. Desde `DocForge/app`, ejecuta `npm install` y después `npm run tauri dev`.
   La configuración base no declara `externalBin`, así que desarrollo y
   `cargo check` funcionan sin el sidecar compilado.
4. Si el sidecar compilado no está presente, el modo desarrollo arranca el
   motor con el Python del entorno virtual. También puedes forzarlo con
   `DOCFORGE_ENGINE_DEV=1`.

## Sidecar y prerrequisitos

Para empaquetar, ejecuta `python engine/build_sidecar.py` desde el repositorio y
coloca el resultado en `src-tauri/binaries/` con el nombre que corresponda al
target. Después empaqueta con `npm run tauri:build`, que añade
`tauri.release.conf.json` (declara `externalBin: binaries/docforge-engine`).

LibreOffice y FFmpeg son opcionales: se detectan desde `PATH` o se configuran
en Ajustes. Docling puede descargar sus modelos una vez con `prefetch_models`
para trabajar después completamente offline.

## Comandos

```powershell
npm install
npm run tauri dev
npm run build
cd src-tauri; cargo check
```
