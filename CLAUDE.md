# DocForge Desktop — reglas del proyecto

## Idioma obligatorio
- Todas las respuestas, explicaciones, resúmenes y mensajes de commit deben estar 100 % en español.
- Nunca respondas en inglés al usuario.

## Versionado automático
- Antes de cada compilación (`npm run tauri build`) o commit de nuevas funciones/correcciones, incrementa la versión **patch** (0.1.0 → 0.1.1 → 0.1.2 …).
- La versión debe quedar sincronizada en los tres archivos:
  - `app/package.json` (`"version"`)
  - `app/src-tauri/tauri.conf.json` (`"version"`)
  - `app/src-tauri/Cargo.toml` (`version` en `[package]`; `Cargo.lock` se actualiza al compilar e incluye el cambio en el commit)
- La interfaz lee la versión en tiempo de ejecución (`getVersion()` de `@tauri-apps/api/app`), así que no hay que tocarla en el código.
