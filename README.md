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

## Conversión de Office a PDF

LibreOffice ya **no es obligatorio**. Para convertir documentos Office a PDF,
DocForge prueba los motores en cascada:

1. **Microsoft Office** (Word, Excel o PowerPoint según el archivo), si está
   instalado. Se usa por COM en una instancia propia e invisible, sin tocar los
   documentos que tengas abiertos.
2. **LibreOffice**, si Office no está o no puede abrir el archivo. Se busca en
   la ruta de Ajustes, `DOCFORGE_SOFFICE`, `PATH`, Program Files, AppData,
   LibreOffice Portable, Scoop, Chocolatey y el registro de Windows.
3. Si no hay ninguno, la tarea muestra las alternativas disponibles.

La opción de tarea `officeEngine` (`auto` por defecto, `msoffice` o
`libreoffice`) fuerza un motor concreto. La variable de entorno
`DOCFORGE_DISABLE_OFFICE_COM=1` desactiva Microsoft Office (la usan las pruebas).

FFmpeg tampoco se embebe: es opcional y se busca en `PATH` o en la ruta que
guardes desde Ajustes. Docling usa modelos locales después del prefetch inicial.

## Sidecar

`python engine/build_sidecar.py --lite` genera el sidecar sin Docling/Torch y
con optimización de bytecode `-OO` por defecto. La build completa usa `-O0`
salvo que pases `--optimize 2`. `--upx` activa la compresión UPX (opcional).
