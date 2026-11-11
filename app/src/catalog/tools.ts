import type { ComponentType } from "react";
import {
  AudioLines,
  Crop,
  Eraser,
  FileCode2,
  FileImage,
  FileOutput,
  FilePenLine,
  FileSpreadsheet,
  FileText,
  Film,
  Hash,
  ImagePlus,
  Layers,
  LockKeyhole,
  Maximize,
  Move,
  PanelsTopLeft,
  ScanText,
  ShieldCheck,
  Split,
  Trash2,
  UnlockKeyhole,
  Wand2,
  Workflow,
} from "lucide-react";
import type { Engine } from "@/contracts/task";

export type FieldType = "text" | "number" | "select" | "boolean" | "password" | "pages" | "list" | "multiselect";

export interface OptionField {
  key: string;
  label: string;
  type: FieldType;
  default?: unknown;
  placeholder?: string;
  options?: { value: string; label: string }[];
  description?: string;
}

export type Domain = "stirling" | "conversor" | "docling" | "multimedia";

export interface ToolDefinition {
  id: string;
  domain: Domain;
  engine: Engine;
  action: string;
  label: string;
  description: string;
  tip?: string;
  icon: ComponentType<{ size?: number; className?: string }>;
  extensions: string[];
  multiFile: boolean;
  fields: OptionField[];
}

// Acciones internas del motor: no se muestran como tarjetas del catálogo.
export const INTERNAL_ACTIONS = ["apply_page_plan"] as const;

export const domains: { id: Domain; label: string; description: string }[] = [
  {
    id: "stirling",
    label: "Stirling-PDF Core",
    description: "Organización, seguridad y edición de PDF",
  },
  {
    id: "conversor",
    label: "Conversor Universal",
    description: "Puentes con LibreOffice para formatos de oficina",
  },
  {
    id: "docling",
    label: "Docling AI Export",
    description: "Extracción estructurada y modelos locales",
  },
  {
    id: "multimedia",
    label: "Multimedia",
    description: "Audio y vídeo con FFmpeg",
  },
];

const s = (
  key: string,
  label: string,
  values: [string, string][],
  value: string,
): OptionField => ({
  key,
  label,
  type: "select",
  options: values.map(([optionValue, optionLabel]) => ({ value: optionValue, label: optionLabel })),
  default: value,
});

const t = (
  key: string,
  label: string,
  value = "",
  type: FieldType = "text",
  description?: string,
): OptionField => ({ key, label, type, default: value, description });

const b = (key: string, label: string, value = false): OptionField => ({
  key,
  label,
  type: "boolean",
  default: value,
});

const l = (key: string, label: string, defaultValue: unknown[] = []): OptionField => ({
  key,
  label,
  type: "list",
  default: defaultValue,
  placeholder: "Un valor por línea",
});

/** Chips with a fixed set of values; the task always receives a clean string[]. */
const m = (key: string, label: string, options: [string, string][], defaultValue: string[]): OptionField => ({
  key,
  label,
  type: "multiselect",
  options: options.map(([value, optionLabel]) => ({ value, label: optionLabel })),
  default: defaultValue,
});

const p = (key = "pages"): OptionField => t(
  key,
  "Páginas",
  "",
  "pages",
  "Ejemplos: 1-3,5,8-",
);

const pdf = ["pdf"];

export const tools: ToolDefinition[] = [
  {
    id: "merge",
    domain: "stirling",
    engine: "stirling_core",
    action: "merge",
    label: "Unir PDF",
    description: "Combina varios documentos en el orden elegido.",
    tip: "Arrastra para ordenar los archivos y haz doble clic en una página para ampliarla.",
    icon: Layers,
    extensions: pdf,
    multiFile: true,
    fields: [l("order", "Orden"), t("outputName", "Nombre de salida", "merged.pdf")],
  },
  {
    id: "page_organizer",
    domain: "stirling",
    engine: "stirling_core",
    action: "apply_page_layout",
    label: "Organizar y Rotar Páginas",
    description: "Reordena, gira y excluye páginas con miniaturas visuales.",
    tip: "Arrastra las tarjetas para cambiar el orden; las acciones no modifican el PDF original.",
    icon: PanelsTopLeft,
    extensions: pdf,
    multiFile: false,
    fields: [],
  },
  {
    id: "split",
    domain: "stirling",
    engine: "stirling_core",
    action: "split",
    label: "Dividir PDF",
    description: "Separa un PDF por rangos, cada N páginas o una página.",
    tip: "Haz doble clic para ampliar y usa Shift+clic para seleccionar un rango. En “Dividir por rangos” se conserva el formulario clásico.",
    icon: Split,
    extensions: pdf,
    multiFile: false,
    fields: [
      s("mode", "Modo", [["ranges", "Rangos"], ["every", "Cada N páginas"], ["single", "Página individual"]], "ranges"),
      p("ranges"),
      t("every", "Cada N páginas", "2", "number"),
      t("page", "Página", "1", "number"),
    ],
  },
  {
    id: "rotate",
    domain: "stirling",
    engine: "stirling_core",
    action: "rotate",
    label: "Rotar páginas",
    description: "Gira páginas seleccionadas sin modificar el original.",
    tip: "Selecciona varias páginas con Shift+clic y haz doble clic en cualquiera para revisar el resultado ampliado.",
    icon: Move,
    extensions: pdf,
    multiFile: false,
    fields: [s("angle", "Ángulo", [["90", "90°"], ["180", "180°"], ["270", "270°"]], "90"), p()],
  },
  {
    id: "crop",
    domain: "stirling",
    engine: "stirling_core",
    action: "crop",
    label: "Recortar PDF",
    description: "Aplica una caja de recorte o márgenes en puntos.",
    icon: Crop,
    extensions: pdf,
    multiFile: false,
    fields: [
      t("box", "Caja x0,y0,x1,y1 (pt)"),
      t("margins", "Márgenes pt (10 · 10,20 · sup,der,inf,izq)", "20"),
      p(),
    ],
  },
  {
    id: "delete_pages",
    domain: "stirling",
    engine: "stirling_core",
    action: "delete_pages",
    label: "Eliminar páginas",
    description: "Quita páginas por rango del documento.",
    tip: "Marca páginas en rojo o usa Shift+clic para un rango; haz doble clic para ampliar antes de eliminarlas.",
    icon: Trash2,
    extensions: pdf,
    multiFile: false,
    fields: [p()],
  },
  {
    id: "nup",
    domain: "stirling",
    engine: "stirling_core",
    action: "nup",
    label: "Varias páginas por hoja",
    description: "Imprime 2, 4, 6 o 9 páginas por hoja.",
    icon: Maximize,
    extensions: pdf,
    multiFile: false,
    fields: [
      s("perSheet", "Páginas por hoja", [["2", "2"], ["4", "4"], ["6", "6"], ["9", "9"]], "2"),
      s("pageSize", "Tamaño", [["A4", "A4"], ["Letter", "Letter"]], "A4"),
      b("landscape", "Horizontal"),
    ],
  },
  {
    id: "redact",
    domain: "stirling",
    engine: "stirling_core",
    action: "redact",
    label: "Redactar contenido",
    description: "Borra de forma permanente términos, patrones y áreas sensibles.",
    icon: Eraser,
    extensions: pdf,
    multiFile: false,
    fields: [
      l("terms", "Términos"),
      l("regex", "Expresiones regulares"),
      l("presets", "Preajustes: email, phone, DNI, IBAN, card"),
      l("areas", "Áreas"),
      b("applyRedactions", "Aplicar borrado real", true),
    ],
  },
  {
    id: "sanitize",
    domain: "stirling",
    engine: "stirling_core",
    action: "sanitize",
    label: "Sanitizar PDF",
    description: "Elimina metadatos, JavaScript, adjuntos, enlaces y XMP.",
    icon: ShieldCheck,
    extensions: pdf,
    multiFile: false,
    fields: [
      b("removeMetadata", "Metadatos", true),
      b("removeJs", "JavaScript", true),
      b("removeAttachments", "Adjuntos", true),
      b("removeLinks", "Enlaces"),
      b("removeXmp", "XMP", true),
    ],
  },
  {
    id: "protect",
    domain: "stirling",
    engine: "stirling_core",
    action: "protect_pdf",
    label: "Proteger PDF",
    description: "Cifra el documento con AES-256 y permisos configurables.",
    icon: LockKeyhole,
    extensions: pdf,
    multiFile: false,
    fields: [
      t("userPassword", "Contraseña de usuario", "", "password"),
      t("ownerPassword", "Contraseña de propietario", "", "password"),
      t("permissions", "Permisos", "print,copy"),
      s("encryption", "Cifrado", [["AES-256", "AES-256"]], "AES-256"),
    ],
  },
  {
    id: "unprotect",
    domain: "stirling",
    engine: "stirling_core",
    action: "unlock_pdf",
    label: "Desbloquear PDF",
    description: "Quita la protección con la contraseña del documento.",
    icon: UnlockKeyhole,
    extensions: pdf,
    multiFile: false,
    fields: [t("password", "Contraseña", "", "password")],
  },
  {
    id: "page_numbers",
    domain: "stirling",
    engine: "stirling_core",
    action: "page_numbers",
    label: "Numerar páginas",
    description: "Añade numeración configurable a cada página.",
    icon: Hash,
    extensions: pdf,
    multiFile: false,
    fields: [
      s("position", "Posición", [["bottom-center", "Abajo centro"], ["bottom-right", "Abajo derecha"], ["top-right", "Arriba derecha"]], "bottom-center"),
      t("format", "Formato", "{n}/{total}"),
      t("startAt", "Comenzar en", "1", "number"),
      t("fontSize", "Tamaño", "10", "number"),
    ],
  },
  {
    id: "watermark",
    domain: "stirling",
    engine: "stirling_core",
    action: "watermark",
    label: "Marca de agua",
    description: "Superpone texto o una imagen con opacidad y mosaico.",
    icon: Wand2,
    extensions: pdf,
    multiFile: false,
    fields: [
      t("text", "Texto"),
      t("imagePath", "Ruta de imagen"),
      t("opacity", "Opacidad", "0.35", "number"),
      t("rotation", "Rotación", "45", "number"),
      t("fontSize", "Tamaño", "36", "number"),
      b("tile", "Mosaico"),
    ],
  },
  {
    id: "flatten",
    domain: "stirling",
    engine: "stirling_core",
    action: "flatten",
    label: "Aplanar PDF",
    description: "Convierte formularios y anotaciones en contenido fijo.",
    icon: FileOutput,
    extensions: pdf,
    multiFile: false,
    fields: [],
  },
  {
    id: "pdf_to_images",
    domain: "stirling",
    engine: "stirling_core",
    action: "pdf_to_images",
    label: "PDF a imágenes",
    description: "Renderiza páginas a PNG, JPG o WebP.",
    icon: FileImage,
    extensions: pdf,
    multiFile: false,
    fields: [t("dpi", "DPI", "150", "number"), s("format", "Formato", [["png", "PNG"], ["jpg", "JPG"], ["webp", "WebP"]], "png"), p()],
  },
  {
    id: "extract_images",
    domain: "stirling",
    engine: "stirling_core",
    action: "extract_images",
    label: "Extraer imágenes",
    description: "Extrae imágenes incrustadas por tamaño mínimo.",
    icon: ImagePlus,
    extensions: pdf,
    multiFile: false,
    fields: [t("minSize", "Tamaño mínimo (px)", "64", "number")],
  },
  {
    id: "images_to_pdf",
    domain: "stirling",
    engine: "stirling_core",
    action: "images_to_pdf",
    label: "Imágenes a PDF",
    description: "Crea un PDF a partir de una o varias imágenes.",
    icon: FileImage,
    extensions: ["png", "jpg", "jpeg", "webp", "tiff"],
    multiFile: true,
    fields: [
      s("pageSize", "Página", [["fit", "Ajustar a imagen"], ["A4", "A4"]], "fit"),
      t("margin", "Margen (pt)", "0", "number"),
    ],
  },
  {
    id: "pdf_to_html",
    domain: "stirling",
    engine: "stirling_core",
    action: "pdf_to_html",
    label: "PDF a HTML",
    description: "Exporta el texto y el diseño de cada página como HTML.",
    icon: FileCode2,
    extensions: pdf,
    multiFile: false,
    fields: [],
  },
  {
    id: "docling_parse",
    domain: "docling",
    engine: "docling_core",
    action: "docling_parse",
    label: "Parser Inteligente",
    description: "Extrae Markdown, JSON, HTML o DocTags con OCR y tablas.",
    tip: "Activa OCR para documentos escaneados y revisa el resultado en el visor cuando termine el trabajo.",
    icon: ScanText,
    extensions: ["pdf", "png", "jpg", "jpeg", "webp", "tif", "tiff", "bmp"],
    multiFile: false,
    fields: [
      m("exportFormats", "Formatos", [["md", "MD"], ["json", "JSON"], ["html", "HTML"], ["doctags", "DocTags"]], ["md"]),
      b("ocr", "OCR", true),
      t("ocrLang", "Idioma OCR", "es"),
      s("tableMode", "Tablas", [["fast", "Rápido"], ["accurate", "Preciso"]], "fast"),
      b("formulas", "Fórmulas LaTeX", true),
      s("images", "Imágenes", [["embedded", "Incrustadas"], ["referenced", "Referenciadas"]], "embedded"),
      p(),
    ],
  },
  {
    id: "office_to_pdf",
    domain: "conversor",
    engine: "office_bridge",
    action: "office_to_pdf",
    label: "Office a PDF",
    description: "Convierte documentos, hojas y presentaciones con LibreOffice.",
    icon: FileText,
    extensions: ["docx", "xlsx", "pptx", "odt", "ods", "odp"],
    multiFile: true,
    fields: [t("binaryPath", "Ruta de LibreOffice")],
  },
  {
    id: "pdf_to_docx",
    domain: "conversor",
    engine: "office_bridge",
    action: "pdf_to_docx",
    label: "PDF a DOCX",
    description: "Convierte PDF editable mediante LibreOffice o pdf2docx.",
    icon: FilePenLine,
    extensions: pdf,
    multiFile: false,
    fields: [t("binaryPath", "Ruta de LibreOffice")],
  },
  {
    id: "pdf_to_xlsx",
    domain: "conversor",
    engine: "office_bridge",
    action: "pdf_to_xlsx",
    label: "PDF a XLSX",
    description: "Detecta tablas y las exporta como hoja de cálculo.",
    icon: FileSpreadsheet,
    extensions: pdf,
    multiFile: false,
    fields: [t("binaryPath", "Ruta de LibreOffice")],
  },
  {
    id: "to_audio",
    domain: "multimedia",
    engine: "ffmpeg_bridge",
    action: "to_audio",
    label: "Convertir a audio",
    description: "Extrae audio en MP3, WAV o AAC.",
    icon: AudioLines,
    extensions: ["mp4", "mkv", "webm", "mov", "avi"],
    multiFile: false,
    fields: [
      s("format", "Formato", [["mp3", "MP3"], ["wav", "WAV"], ["aac", "AAC"]], "mp3"),
      t("bitrate", "Bitrate", "192k"),
      t("binaryPath", "Ruta de FFmpeg"),
    ],
  },
  {
    id: "compress_video",
    domain: "multimedia",
    engine: "ffmpeg_bridge",
    action: "compress_video",
    label: "Comprimir vídeo",
    description: "Reduce tamaño con CRF, preset y altura máxima.",
    icon: Film,
    extensions: ["mp4", "mkv", "webm", "mov", "avi"],
    multiFile: false,
    fields: [
      t("crf", "CRF", "23", "number"),
      s("preset", "Preset", [["fast", "Fast"], ["medium", "Medium"], ["slow", "Slow"]], "medium"),
      t("maxHeight", "Altura máxima", "1080", "number"),
      t("binaryPath", "Ruta de FFmpeg"),
    ],
  },
  {
    id: "convert",
    domain: "multimedia",
    engine: "ffmpeg_bridge",
    action: "convert",
    label: "Convertir vídeo",
    description: "Cambia el contenedor entre MP4, MKV y WebM.",
    icon: Workflow,
    extensions: ["mp4", "mkv", "webm", "mov", "avi"],
    multiFile: false,
    fields: [
      s("container", "Contenedor", [["mp4", "MP4"], ["mkv", "MKV"], ["webm", "WebM"]], "mp4"),
      t("binaryPath", "Ruta de FFmpeg"),
    ],
  },
];

export const toolById = (id: string) => tools.find((tool) => tool.id === id);
