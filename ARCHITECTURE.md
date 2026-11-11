# DocForge Desktop — Arquitectura (v0.1)

Suite documental 100% offline: Tauri v2 (Rust) + React 19/TS + Tailwind + shadcn/ui + Lucide,
con un **sidecar Python** que implementa los motores mediante Strategy Pattern.

## 1. Estructura del monorepo

```
DocForge/
├─ ARCHITECTURE.md
├─ README.md                      # setup dev, build, empaquetado
├─ app/                           # Tauri + React
│  ├─ package.json  vite.config.ts  tailwind  components.json (shadcn)
│  ├─ src/
│  │  ├─ main.tsx  App.tsx
│  │  ├─ contracts/task.ts        # ProcessorTask / TaskEvent / TaskResult (espejo del contrato)
│  │  ├─ catalog/tools.ts         # Catálogo declarativo: id, dominio, engine, action, icono, schema de opciones
│  │  ├─ lib/engine.ts            # invoke('run_task'), listen('task://event'), cancel
│  │  ├─ store/jobs.ts            # cola de trabajos (zustand)
│  │  ├─ components/ui/*          # shadcn
│  │  ├─ components/ToolForm.tsx  # formulario generado desde el schema de opciones
│  │  ├─ components/FileDrop.tsx  # drag&drop + diálogo nativo (plugin-dialog), reordenable
│  │  ├─ components/JobQueue.tsx  # progreso, logs, abrir carpeta de salida
│  │  └─ pages/ Home (grid por dominio + búsqueda) · ToolPage · Settings (rutas soffice/ffmpeg, diagnóstico)
│  └─ src-tauri/
│     ├─ tauri.conf.json          # externalBin: binaries/docforge-engine
│     ├─ capabilities/default.json
│     └─ src/ main.rs lib.rs
│        ├─ contract.rs           # structs serde del contrato
│        ├─ sidecar.rs            # spawn/gestión del proceso, NDJSON por stdin/stdout
│        └─ commands.rs           # run_task, cancel_task, engine_health, open_path
└─ engine/                        # Sidecar Python 3.12
   ├─ pyproject.toml              # extras: [pdf] [docling] [dev]
   ├─ docforge_engine/
   │  ├─ __main__.py              # modos: `serve` (NDJSON loop) y `run <task.json>` (CLI one-shot)
   │  ├─ contract.py              # pydantic: ProcessorTask, TaskEvent, TaskResult
   │  ├─ registry.py              # EngineRegistry: engine -> Processor; action -> handler
   │  ├─ base.py                  # BaseProcessor (Strategy), @action decorator, ProgressReporter
   │  ├─ util/ paths.py pages.py (parser de rangos "1-3,5,8-") binaries.py (localizar soffice/ffmpeg)
   │  └─ processors/
   │     ├─ stirling_core/ organize.py security.py edit.py convert_pdf.py
   │     ├─ docling_core/ parse.py   # import perezoso de docling
   │     ├─ office_bridge/ soffice.py
   │     └─ ffmpeg_bridge/ ffmpeg.py
   ├─ tests/                      # pytest con PDFs generados en fixtures
   └─ build_sidecar.py            # PyInstaller -> app/src-tauri/binaries/docforge-engine-<target-triple>[.exe]
```

## 2. Contrato de ejecución

```ts
interface ProcessorTask {
  id: string;
  engine: 'stirling_core' | 'docling_core' | 'office_bridge' | 'ffmpeg_bridge';
  action: string;
  inputFiles: string[];      // rutas absolutas
  outputDir: string;
  options?: Record<string, any>;
}

type TaskEvent =
  | { type: 'progress'; id: string; percent: number; message?: string }
  | { type: 'log';      id: string; level: 'info'|'warn'|'error'; message: string }
  | { type: 'result';   id: string; status: 'success'; outputFiles: string[]; meta?: Record<string, any> }
  | { type: 'error';    id: string; code: ErrorCode; message: string; details?: string };

type ErrorCode = 'INVALID_TASK'|'UNKNOWN_ACTION'|'INPUT_NOT_FOUND'|'WRONG_PASSWORD'
               |'DEPENDENCY_MISSING'|'BINARY_NOT_FOUND'|'CANCELLED'|'INTERNAL';
```

**Transporte:** el sidecar corre en modo `serve` como proceso persistente (evita re-importar PyMuPDF/torch
por tarea). Rust escribe una `ProcessorTask` JSON por línea en stdin; Python emite `TaskEvent` NDJSON por
stdout (stderr = logs de diagnóstico). Las tareas se ejecutan en un `ThreadPoolExecutor` (docling en un
worker serializado por coste de memoria). Mensajes de control: `{"type":"cancel","id":...}`,
`{"type":"health"}` → `{"type":"health", engines:{...disponible, versión, motivo}}`.
Rust reemite cada evento al frontend como `task://event`. Si el sidecar muere, Rust lo relanza y
marca las tareas en vuelo como `error/INTERNAL`.

**Reglas:** nunca sobrescribir entradas; salida = `outputDir/<stem>_<action>[_n].<ext>`; escritura atómica
(archivo temporal + rename); procesar en streaming página a página (sin límites de tamaño).

## 3. Catálogo de acciones

| engine | action | opciones clave |
|---|---|---|
| stirling_core | merge | order (índices), outputName |
| | split | mode: ranges/every/single, ranges "1-3,5" , every N |
| | rotate | angle 90/180/270, pages |
| | crop | box {x0,y0,x1,y1} pt o margins |
| | delete_pages | pages |
| | nup | perSheet 2/4/6/9, pageSize A4/Letter, landscape |
| | redact | terms[], regex[], presets: email/phone/dni/iban/card, areas[] → apply_redactions (borrado real) |
| | sanitize | removeMetadata, removeJs, removeAttachments, removeLinks, removeXmp (pikepdf) |
| | protect | userPassword, ownerPassword, permissions, AES-256 (pikepdf) |
| | unprotect | password |
| | page_numbers | position, format "{n}/{total}", startAt, fontSize |
| | watermark | text \| imagePath, opacity, rotation, fontSize, tile |
| | flatten | (formularios + anotaciones a contenido) |
| | pdf_to_images | dpi, format png/jpg/webp, pages |
| | extract_images | minSize |
| | images_to_pdf | pageSize fit/A4, margin |
| | pdf_to_html | (PyMuPDF get_text('html') por página) |
| docling_core | docling_parse | exportFormats [md,json,html,doctags], ocr bool, ocrLang, tableMode fast/accurate, formulas bool (LaTeX), images embedded/referenced, pages |
| office_bridge | office_to_pdf | (docx/xlsx/pptx/odt…) |
| | pdf_to_docx | vía soffice `--infilter=writer_pdf_import`; fallback `pdf2docx` si instalado |
| | pdf_to_xlsx | tablas detectadas por docling/PyMuPDF `find_tables` → openpyxl |
| ffmpeg_bridge | to_audio | format mp3/wav/aac, bitrate |
| | compress_video | crf, preset, maxHeight |
| | convert | container mp4/mkv/webm |

Docling: `DocumentConverter` con `PdfPipelineOptions(do_ocr, do_table_structure, table_structure_options.mode,
do_formula_enrichment)`; export `export_to_markdown()`, `export_to_dict()` (JSON AST), `export_to_html()`.
Modelos descargados una vez a `%APPDATA%/DocForge/models` (`artifacts_path`) para funcionamiento offline;
comando `prefetch_models` en Settings.

## 4. Empaquetado
- Sidecar: PyInstaller onedir → registrado como `externalBin`. Variante "lite" (sin docling/torch, ~80 MB)
  y "full" (con docling, ~1.5 GB) seleccionable en build.
- LibreOffice y FFmpeg: no se embeben; se detectan (PATH, rutas estándar, ruta configurada en Settings).
- Seguridad: CSP estricta, sin red; capabilities mínimas (dialog, opener, shell sidecar).

## 5. Fases
1. **MVP (este entregable):** scaffold completo, contrato, sidecar con stirling_core completo, docling_core,
   office_bridge, ffmpeg_bridge funcional básico, UI con catálogo + cola, tests del motor.
2. Previsualización de páginas (thumbnails) y redacción manual por áreas en canvas.
3. Pipelines encadenados (salida de una tarea → entrada de otra), presets guardados.
4. Firma de código, auto-update offline, instaladores MSI/DMG.

---

## 6. Fase 2 — Manipulación visual de páginas + Visor dual Docling

### 6.1 Canal RPC (petición/respuesta) además de las tareas

Las miniaturas y lecturas de archivos son consultas rápidas, no trabajos de la cola. Se añade al
NDJSON un tipo de mensaje con correlación por id (convive con `ProcessorTask`, `cancel`, `health`):

```jsonc
// Rust -> Python (stdin)
{"type":"rpc","rpcId":"<uuid>","method":"<método>","params":{...}}
// Python -> Rust (stdout)
{"type":"rpc_result","rpcId":"<uuid>","ok":true,"result":{...}}
{"type":"rpc_result","rpcId":"<uuid>","ok":false,"error":{"code":"<ErrorCode>","message":"...","details":"..."}}
```

- Python ejecuta los RPC en un pool propio (`max_workers=4`) para que nunca esperen detrás de tareas largas.
- Rust: `SidecarManager::rpc(method, params, timeout)` registra un `oneshot`/`mpsc` por `rpcId` en un
  `HashMap`, el lector de stdout lo resuelve; timeout por defecto 30 s → error `TIMEOUT`. Si el sidecar
  muere, todos los RPC pendientes se resuelven con `INTERNAL`.
- Comando Tauri **async**: `engine_rpc(method: String, params: serde_json::Value) -> Result<Value, String>`
  (el `Err` es el JSON del objeto `error` serializado). Front: `engineRpc<T>(method, params): Promise<T>`.

### 6.2 Métodos RPC (engine/docforge_engine/rpc.py)

| método | params | result |
|---|---|---|
| `get_pdf_pages_metadata` | `{pdfPath}` | `{fileHash, pageCount, pages:[{index,width,height,rotation}]}` — sin renderizar (rápido incluso con 1000+ páginas) |
| `get_page_thumbnails` | `{pdfPath, start, count, maxWidth=300, format="webp"}` (count ≤ 24) | `{pages:[{index, thumbUrl:"data:image/webp;base64,...", width, height}]}` |
| `render_page` | `{pdfPath, index, maxWidth=1100}` | `{index, imageUrl, width, height}` (visor del panel izquierdo) |
| `read_text_file` | `{path, maxBytes=20MB}` | `{content, size}` — solo extensiones .md .json .html .txt .doctags |
| `export_file` | `{sourcePath, targetPath}` | `{path}` (copia; usado por "Exportar .md") |

**Caché de miniaturas** (`util/thumbnail_generator.py`):
- `fileHash` = sha1 de (ruta absoluta normalizada + tamaño + mtime_ns) → no relee el PDF entero.
- Disco: `tempfile.gettempdir()/docforge_thumbs/<fileHash>/<maxWidth>/<index>.webp`; memoria: LRU (≈256 entradas)
  de bytes ya codificados. Render con `page.get_pixmap(matrix=fitz.Matrix(z,z), alpha=False)` donde
  `z = maxWidth / page.rect.width` (tope DPI 150); WebP vía Pillow (fallback PNG).
- Documentos abiertos: caché LRU de `fitz.Document` (≈8) con lock por documento (fitz no es thread-safe por doc).
- Limpieza: al arrancar, borrar carpetas de caché con más de 7 días.
- PDFs cifrados → error `WRONG_PASSWORD` (se admite `password` opcional en params).

### 6.3 Acción `stirling_core.apply_page_plan`

```ts
interface PageRef { sourceIndex: number; pageIndex: number; rotation?: 0|90|180|270 } // rotación adicional, horario
interface PageOperationPlan { sourcePath: string; pageOrder: number[]; rotations: Record<number, number>; deletedPages: number[] }
options: {
  sequence?: PageRef[];                 // forma canónica (front la usa siempre): orden final, multi-archivo (merge)
  plans?: PageOperationPlan[];          // forma alternativa: se concatenan en orden; deletedPages se excluyen
  outputMode?: "single" | "per_page" | "per_source";   // default "single"
  outputName?: string;
}
```
- `inputFiles` = fuentes; `sourceIndex` indexa en `inputFiles`; `sourcePath` de un plan debe estar en `inputFiles`.
- Rotación: `(rotación_original + rotation) % 360`, valores negativos normalizados (-90 → 270).
- Implementación con `insert_pdf(from_page=to_page=idx)` página a página (sin cargar todo), progreso por página,
  conserva enlaces/anotaciones cuando PyMuPDF lo permite. Validar índices → `INVALID_TASK`.

### 6.4 Frontend

- `components/pages/PageGridManager.tsx` — se muestra en ToolPage para `merge`, `split`, `rotate`, `delete_pages`
  cuando hay archivos PDF elegidos. Estado en `store/pageGrid.ts` (zustand): `items: {key, sourceIndex, pageIndex,
  rotation, deleted, selected}[]` + historial para "Restablecer orden".
  - `@dnd-kit/core` + `@dnd-kit/sortable` (`rectSortingStrategy`, `PointerSensor` con `activationConstraint.distance=6`,
    `KeyboardSensor`), `DragOverlay` para arrastre fluido.
  - `PageCard`: badge de número (posición final) + "A·3" (archivo·página original) si hay varios archivos;
    miniatura lazy (`IntersectionObserver`, rootMargin 400px) pedida en lotes de 12 por `get_page_thumbnails`;
    rotación aplicada con `transform: rotate()` en la miniatura (sin re-render); hover: ↻ 90°, ↺ 90°, 🗑 marcar
    (overlay rojo semitransparente + icono); checkbox de selección (shift+click = rango).
  - Toolbar: Seleccionar todo · Invertir selección · Rotar seleccionados (↻) · Eliminar seleccionados ·
    Restablecer orden · contador "N páginas · M seleccionadas · K a eliminar" · zoom de miniatura (S/M/L).
  - Virtualización no necesaria con lazy-load + `content-visibility:auto` en las tarjetas (≥500 páginas fluido).
  - Envío: siempre `stirling_core/apply_page_plan` con `sequence` (excluye `deleted`). En **Dividir**: selector
    "Extraer seleccionadas a un PDF" (`single` con solo seleccionadas) / "Un PDF por página seleccionada" (`per_page`) /
    "Dividir por rangos" (mantiene la acción `split` clásica con el formulario).
- `components/docling/DoclingDualViewer.tsx` — en ToolPage de `docling_parse`, se abre cuando el trabajo termina
  (o al pulsar "Ver resultado" en la cola) con `{sourcePdf, markdownPath}`.
  - Split pane redimensionable propio (divisor arrastrable, 20–80 %, persistido en localStorage).
  - Izquierda: visor de páginas con `render_page` lazy + barra (página X/N, zoom). Si la fuente no es PDF: mensaje.
  - Derecha: pestañas "Markdown renderizado" (`react-markdown` + `remark-gfm` + `remark-math` + `rehype-katex` +
    `rehype-highlight`; tablas/código/citas con clases Tailwind, `katex/dist/katex.min.css` y un tema de
    highlight.js importados localmente) y "Markdown raw" (`<pre>` monoespaciado con números de línea).
  - Acciones: "Copiar Markdown" (`navigator.clipboard.writeText` + toast) y "Exportar .md" (`plugin-dialog save` →
    RPC `export_file`).
- `components/ui/toast.tsx`: toaster mínimo (zustand) — éxito/error, autocierre 3 s.
- `lib/engine.ts`: `engineRpc`. Contrato TS en `contracts/rpc.ts`.
