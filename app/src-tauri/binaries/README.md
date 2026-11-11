# Sidecar binario

Esta carpeta recibe el artefacto generado por `engine/build_sidecar.py`.
PyInstaller debe producir un binario con el nombre esperado por Tauri y por
plataforma, por ejemplo `docforge-engine-x86_64-pc-windows-msvc.exe`.

Durante desarrollo, si el binario no existe (o si `DOCFORGE_ENGINE_DEV` está
definida), Rust usa `engine/.venv/Scripts/python.exe -m docforge_engine serve`
en Windows y `engine/.venv/bin/python` en macOS/Linux. Por eso una instalación
de desarrollo no necesita copiar un stub a esta carpeta. Para `tauri build`,
construye primero el sidecar y cópialo aquí con el sufijo del target de Tauri.
