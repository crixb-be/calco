<div align="center">

<img src="app/src-tauri/icons/128x128.png" alt="Logo de CALCO" width="110" />

# CALCO

**Suite local y privada para PDF, conversión universal, Markdown para IA y multimedia.**

Edita, convierte y optimiza tus documentos **sin subir un solo archivo a la nube**.
Todo se procesa en tu equipo.

[![Versión](https://img.shields.io/badge/versión-0.1.2-6366f1?style=for-the-badge)](https://github.com/crixb-be/calco/releases)
[![Licencia MIT](https://img.shields.io/badge/licencia-MIT-22c55e?style=for-the-badge)](LICENSE)

![Tauri](https://img.shields.io/badge/Tauri-v2-24C8DB?style=flat-square&logo=tauri&logoColor=white)
![Rust](https://img.shields.io/badge/Rust-000000?style=flat-square&logo=rust&logoColor=white)
![React](https://img.shields.io/badge/React-20232A?style=flat-square&logo=react&logoColor=61DAFB)
![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?style=flat-square&logo=typescript&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white)
![PyMuPDF](https://img.shields.io/badge/PyMuPDF-PDF%20engine-c0392b?style=flat-square)
![MIT License](https://img.shields.io/badge/License-MIT-yellow?style=flat-square)

[Características](#-características) ·
[Arquitectura](#-arquitectura) ·
[Instalación](#-instalación-y-desarrollo-local) ·
[Descargas](https://github.com/crixb-be/calco/releases) ·
[Autor](#-autor)

</div>

---

## ✨ ¿Qué es CALCO?

CALCO es una aplicación de escritorio que reúne en un solo lugar las herramientas
que normalmente se buscan en webs de terceros: editar PDF, unirlos, comprimirlos,
convertir documentos de Office, extraer Markdown limpio para alimentar modelos de
IA o convertir audio y video.

La diferencia: **tus archivos nunca salen de tu computadora**. No hay servidores,
no hay cuentas, no hay límites de tamaño impuestos por un servicio en línea.

| 🔒 Privacidad total | ⚡ Rendimiento nativo | 🧩 Todo en uno |
| :---: | :---: | :---: |
| Procesamiento 100 % local, funciona sin conexión | Interfaz Tauri + Rust y motor Python optimizado | PDF, Office, imágenes, Markdown y multimedia |

---

## 🚀 Características

### ✍️ Editor PDF interactivo
- **Texto multilínea** con estilos personalizables.
- **Inserción de imágenes y firmas** sobre cualquier página.
- **Dibujo libre** a mano alzada.
- **Resaltador** para marcar fragmentos importantes.
- **Formas geométricas** (rectángulos, elipses, líneas, flechas).

### 🛠️ Herramientas PDF
| Organizar | Optimizar | Seguridad | Extras |
| --- | --- | --- | --- |
| Unir | Comprimir | Proteger con contraseña | Marcas de agua |
| Dividir | Rotar | Desbloquear | Numeración de páginas |
| Reordenar páginas | Recortar | | Extracción de imágenes |

### 🔄 Conversor universal y Markdown para IA
- Conversión entre **PDF ⇄ Office** (`DOCX`, `XLSX`, `PPTX`) e **imágenes** (`PNG`, `JPG`, …).
- Motores de Office en cascada: **Microsoft Office** (vía COM, invisible) → **LibreOffice** → aviso con alternativas.
- Extracción limpia de PDF a **`.md`** con **`PyMuPDF4LLM`**, ideal para usar como contexto en ChatGPT, Claude u otros LLM.

### 🎬 Multimedia
- **Conversión y compresión local de audio y video** con **FFmpeg**.
- FFmpeg es opcional: se detecta en el `PATH` o en la ruta que configures desde *Ajustes*.

---

## 🏗️ Arquitectura

```
┌──────────────────────────────────────────────┐
│  Frontend · React + TypeScript + Tailwind     │  app/src
│  (interfaz, editor PDF, historial)            │
└───────────────────────┬──────────────────────┘
                        │ invoke()
┌───────────────────────▼──────────────────────┐
│  Núcleo Tauri v2 · Rust                       │  app/src-tauri
│  (ventana nativa, diálogos, gestión sidecar)  │
└───────────────────────┬──────────────────────┘
                        │ JSON-RPC (stdin/stdout)
┌───────────────────────▼──────────────────────┐
│  Sidecar Python · docforge_engine             │  engine/
│  PyMuPDF · pikepdf · pypdf · Pillow ·         │
│  PyMuPDF4LLM · Office COM · LibreOffice ·     │
│  FFmpeg                                       │
└──────────────────────────────────────────────┘
```

| Carpeta | Contenido |
| --- | --- |
| `app/` | Interfaz React + Vite y proyecto Tauri (`src-tauri/`). |
| `app/src-tauri/binaries/` | Destino del sidecar compilado (no se versiona). |
| `engine/` | Motor Python: procesadores PDF, conversores, puente Office/FFmpeg y pruebas. |
| `scripts/` | Scripts de empaquetado y verificación de la distribución. |

Más detalles en [`ARCHITECTURE.md`](ARCHITECTURE.md).

---

## 💻 Instalación y desarrollo local

### Requisitos
- **Node.js** 20 o superior y **npm**
- **Rust** (stable) + requisitos de [Tauri v2](https://v2.tauri.app/start/prerequisites/)
- **Python 3.12** (se recomienda [`uv`](https://docs.astral.sh/uv/))
- *Opcional:* Microsoft Office o LibreOffice (conversiones Office) y FFmpeg (multimedia)

### 1. Clonar el repositorio
```powershell
git clone https://github.com/crixb-be/calco.git
cd calco
```

### 2. Entorno virtual de Python (motor)
```powershell
cd engine
uv venv --python 3.12
uv pip install -e ".[pdf,office,dev]"
# Opcional (pesado): soporte Docling
# uv pip install -e ".[docling]"
cd ..
```

<details>
<summary>Sin <code>uv</code> (venv estándar)</summary>

```powershell
cd engine
py -3.12 -m venv .venv
.\.venv\Scripts\activate
pip install -e ".[pdf,office,dev]"
cd ..
```
</details>

### 3. Compilar el sidecar (versión `--lite`)
Genera el ejecutable del motor sin Docling/Torch y lo copia automáticamente en
`app/src-tauri/binaries/` con el sufijo del target de Tauri:

```powershell
engine\.venv\Scripts\python.exe engine\build_sidecar.py --lite
```

> En desarrollo este paso es opcional: si no hay sidecar compilado, CALCO arranca
> el motor directamente desde `engine/.venv`.

### 4. Ejecutar en modo desarrollo
```powershell
cd app
npm install
npm run dev          # solo la interfaz web (Vite)
npm run tauri dev    # aplicación de escritorio completa
```

### 5. Generar el instalador
```powershell
cd app
npm run tauri build
```
El instalador NSIS queda en `app/src-tauri/target/release/bundle/nsis/`
(por ejemplo `CALCO_0.1.2_x64-setup.exe`).

### Pruebas del motor
```powershell
cd engine
.\.venv\Scripts\python.exe -m pytest
```

---

## 📦 Descargas

¿Solo quieres usarlo? Descarga el instalador para Windows desde la pestaña
[**Releases**](https://github.com/crixb-be/calco/releases).

---

## 👤 Autor

**Cristian Billy Bustamante Espinoza** — [@crixb-be](https://github.com/crixb-be)

Si CALCO te resulta útil, ¡deja una ⭐ en el repositorio!

---

## 📄 Licencia

Distribuido bajo la licencia **MIT**. Consulta el archivo [`LICENSE`](LICENSE) para más información.
