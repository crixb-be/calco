import type { Engine } from "@/contracts/task";

/** Universal converter routing: complete Office/PDF/image conversion matrix. */

export type TargetFormat = "pdf" | "docx" | "xlsx" | "html" | "png" | "jpg" | "webp";
export type InputFamily = "office" | "image" | "pdf";

export const TARGETS: { id: TargetFormat; label: string }[] = [
  { id: "pdf", label: "PDF" },
  { id: "docx", label: "DOCX" },
  { id: "xlsx", label: "XLSX" },
  { id: "html", label: "HTML" },
  { id: "png", label: "PNG" },
  { id: "jpg", label: "JPG" },
  { id: "webp", label: "WebP" },
];

const FAMILY_EXTENSIONS: Record<InputFamily, string[]> = {
  office: ["docx", "doc", "xlsx", "xls", "pptx", "ppt", "odt", "ods", "odp", "rtf", "csv"],
  image: ["png", "jpg", "jpeg", "webp", "tiff", "tif", "bmp"],
  pdf: ["pdf"],
};

export const CONVERTER_EXTENSIONS = Object.values(FAMILY_EXTENSIONS).flat();

const FAMILY_LABEL: Record<InputFamily, string> = { office: "documentos de oficina", image: "imágenes", pdf: "PDF" };

/** Targets each family can reach. */
const ROUTES: Record<InputFamily, TargetFormat[]> = {
  office: ["pdf"],
  image: ["pdf", "png", "jpg", "webp"],
  pdf: ["docx", "xlsx", "html", "png", "jpg", "webp"],
};

export const IMAGE_TARGETS = new Set<TargetFormat>(["png", "jpg", "webp"]);

/** Encoder presets sent as `quality` to stirling_core.image_convert. */
export type QualityPreset = "fast" | "balanced" | "max";
export const QUALITY_PRESETS: { id: QualityPreset; label: string; hint: string }[] = [
  { id: "fast", label: "Rápida", hint: "Archivos más pequeños" },
  { id: "balanced", label: "Equilibrada", hint: "Recomendada" },
  { id: "max", label: "Máxima calidad", hint: "Mayor tamaño" },
];

export const extensionOf = (path: string) => path.split(/[\\/]/).pop()?.split(".").slice(1).pop()?.toLowerCase() ?? "";

/** jpeg == jpg and tif == tiff: the format a file is already in, as a target id. */
const sameFormat = (ext: string): string => (ext === "jpeg" ? "jpg" : ext === "tif" ? "tiff" : ext);

export function familyOf(path: string): InputFamily | null {
  const ext = extensionOf(path);
  const family = (Object.keys(FAMILY_EXTENSIONS) as InputFamily[]).find((key) => FAMILY_EXTENSIONS[key].includes(ext));
  return family ?? null;
}

function families(files: string[]): { found: InputFamily[]; unknown: string[] } {
  const found = new Set<InputFamily>();
  const unknown: string[] = [];
  for (const file of files) {
    const family = familyOf(file);
    if (family) found.add(family);
    else unknown.push(file.split(/[\\/]/).pop() ?? file);
  }
  return { found: [...found], unknown };
}

export interface TargetAvailability {
  target: TargetFormat;
  enabled: boolean;
  reason?: string;
}

export function availableTargets(files: string[]): TargetAvailability[] {
  const { found, unknown } = families(files);
  return TARGETS.map(({ id }) => {
    if (!files.length) return { target: id, enabled: false, reason: "Añade archivos primero" };
    if (unknown.length) return { target: id, enabled: false, reason: `Formato no soportado: ${unknown[0]}` };
    if (found.length > 1) return { target: id, enabled: false, reason: "Mezcla de tipos: conviértelos por separado" };
    const family = found[0];
    if (!ROUTES[family].includes(id)) {
      return { target: id, enabled: false, reason: `No disponible para ${FAMILY_LABEL[family]}` };
    }
    if (family === "image" && files.every((file) => sameFormat(extensionOf(file)) === id)) {
      return { target: id, enabled: false, reason: `Los archivos ya son ${id.toUpperCase()}` };
    }
    return { target: id, enabled: true };
  });
}

export interface ConversionOptions {
  dpi?: number;
  mergeImages?: boolean;
  quality?: QualityPreset;
  sofficePath?: string | null;
}

export interface PlannedTask {
  engine: Engine;
  action: string;
  inputFiles: string[];
  options: Record<string, unknown>;
}

export type ConversionPlan = { tasks: PlannedTask[]; summary: string } | { error: string };

const ENGINE_LABEL: Record<string, string> = { office_bridge: "LibreOffice", stirling_core: "Stirling" };

export function planConversion(files: string[], target: TargetFormat, opts: ConversionOptions = {}): ConversionPlan {
  if (!files.length) return { error: "Añade al menos un archivo." };
  const { found, unknown } = families(files);
  if (unknown.length) return { error: `Formato no soportado: ${unknown.join(", ")}` };
  if (found.length > 1) {
    const labels = found.map((family) => FAMILY_LABEL[family]).join(" y ");
    return { error: `Mezcla de ${labels}: conviértelos por separado.` };
  }
  const family = found[0];
  if (!ROUTES[family].includes(target)) {
    return { error: `No se puede convertir ${FAMILY_LABEL[family]} a ${target.toUpperCase()}.` };
  }
  if (family === "image" && files.every((file) => sameFormat(extensionOf(file)) === target)) {
    return { error: `Los archivos ya están en ${target.toUpperCase()}.` };
  }

  const office = opts.sofficePath ? { binaryPath: opts.sofficePath } : {};
  const perFile = (engine: Engine, action: string, options: Record<string, unknown>): PlannedTask[] =>
    files.map((file) => ({ engine, action, inputFiles: [file], options }));

  let tasks: PlannedTask[];
  if (family === "office") {
    tasks = [{ engine: "office_bridge", action: "office_to_pdf", inputFiles: files, options: office }];
  } else if (family === "image" && IMAGE_TARGETS.has(target)) {
    // One batch task: the engine reports progress per image.
    tasks = [{ engine: "stirling_core", action: "image_convert", inputFiles: files, options: { format: target, quality: opts.quality ?? "balanced" } }];
  } else if (family === "image") {
    const options = { pageSize: "fit", margin: 0 };
    tasks = opts.mergeImages === false
      ? perFile("stirling_core", "images_to_pdf", options)
      : [{ engine: "stirling_core", action: "images_to_pdf", inputFiles: files, options }];
  } else if (target === "docx") {
    tasks = perFile("office_bridge", "pdf_to_docx", office);
  } else if (target === "xlsx") {
    tasks = perFile("office_bridge", "pdf_to_xlsx", office);
  } else if (target === "html") {
    tasks = perFile("stirling_core", "pdf_to_html", {});
  } else {
    const dpi = Number.isFinite(opts.dpi) && (opts.dpi ?? 0) > 0 ? opts.dpi : 150;
    tasks = perFile("stirling_core", "pdf_to_images", {
      format: target,
      dpi,
      quality: opts.quality ?? "balanced",
      pages: "",
    });
  }

  const first = tasks[0];
  const count = `${tasks.length} ${tasks.length === 1 ? "tarea" : "tareas"}`;
  const engineLabel = first.action === "image_convert" ? "Pillow" : ENGINE_LABEL[first.engine] ?? first.engine;
  return { tasks, summary: `${engineLabel} · ${first.action} · ${count}` };
}
